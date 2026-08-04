# workflow.py
#
# Approval Workflow Service — single integration point between the pipeline
# and all downstream actions (persistence, Gmail send, audit, timeline).
#
# WorkflowStatus states:
#   PENDING → DRAFT_SAVED | GMAIL_DRAFT_SAVED | APPROVED | REJECTED
#   DRAFT_SAVED → APPROVED | REJECTED | GMAIL_DRAFT_SAVED
#   GMAIL_DRAFT_SAVED → APPROVED | REJECTED
#   APPROVED → SENT (terminal via approve_and_send on success)
#   SENT, REJECTED → terminal

import enum
import logging
from datetime import datetime

from database.db_manager import save_envelope, update_email_status, get_email_by_id
from database.audit_logger import log_action, record_timeline

logger = logging.getLogger(__name__)


# ── WorkflowStatus ────────────────────────────────────────────────────────

class WorkflowStatus(str, enum.Enum):
    """
    Canonical lifecycle states.  Inherits str so members ARE plain strings —
    SQLite, JSON, and DecisionEnvelope.workflow_status (typed str) all
    receive 'PENDING', not an enum repr.
    """
    PENDING           = "PENDING"
    DRAFT_SAVED       = "DRAFT_SAVED"
    GMAIL_DRAFT_SAVED = "GMAIL_DRAFT_SAVED"
    APPROVED          = "APPROVED"
    SENT              = "SENT"
    REJECTED          = "REJECTED"


# ── Transition graph ──────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.PENDING: {
        WorkflowStatus.DRAFT_SAVED,
        WorkflowStatus.GMAIL_DRAFT_SAVED,
        WorkflowStatus.APPROVED,
        WorkflowStatus.REJECTED,
    },
    WorkflowStatus.DRAFT_SAVED: {
        WorkflowStatus.APPROVED,
        WorkflowStatus.REJECTED,
        WorkflowStatus.GMAIL_DRAFT_SAVED,
    },
    WorkflowStatus.GMAIL_DRAFT_SAVED: {
        WorkflowStatus.APPROVED,
        WorkflowStatus.REJECTED,
    },
    WorkflowStatus.APPROVED: {
        WorkflowStatus.SENT,
    },
    WorkflowStatus.SENT:     set(),
    WorkflowStatus.REJECTED: set(),
}


# ── Internal helpers ──────────────────────────────────────────────────────

def _validate_transition(from_status: str, to_status: WorkflowStatus) -> None:
    try:
        current = WorkflowStatus(from_status)
    except ValueError:
        raise ValueError(
            f"'{from_status}' is not a recognised WorkflowStatus. "
            f"Valid: {[s.value for s in WorkflowStatus]}"
        )
    allowed = VALID_TRANSITIONS.get(current, set())
    if to_status not in allowed:
        if not allowed:
            raise PermissionError(f"'{current.value}' is a terminal state.")
        raise PermissionError(
            f"Invalid transition '{current.value}' → '{to_status.value}'. "
            f"Allowed: {sorted(s.value for s in allowed)}"
        )


def _extract_to_email(raw_sender: str) -> str:
    """Strips display name: 'Alice <alice@ex.com>' → 'alice@ex.com'."""
    if "<" in raw_sender:
        return raw_sender.split("<")[-1].replace(">", "").strip()
    return raw_sender.strip()


# ── Public API ────────────────────────────────────────────────────────────

def submit_email(envelope) -> object:
    """
    Persists a new PENDING envelope and records the initial audit events.
    Raises ValueError if envelope.workflow_status is not PENDING.
    """
    if envelope.workflow_status != WorkflowStatus.PENDING.value:
        raise ValueError(
            f"submit_email() expects PENDING, got '{envelope.workflow_status}'."
        )

    logger.info("Workflow: submit email id='%s'.", envelope.email_id)

    save_envelope(envelope)

    log_action(envelope.email_id, "AI", "DRAFT_CREATED",
               {"category": envelope.classification.category,
                "priority_score": envelope.priority.priority_score,
                "risk_level": envelope.priority.risk_level})
    record_timeline(envelope.email_id, "DRAFT_CREATED", "AI")

    logger.info("Workflow: email id='%s' persisted. Awaiting human decision.", envelope.email_id)
    return envelope


def approve_and_send(email_id: str, reply_text: str, from_status: str = "PENDING") -> None:
    """
    Approves the draft and sends it via Gmail.

    Transition: PENDING | DRAFT_SAVED | GMAIL_DRAFT_SAVED → APPROVED → SENT

    If Gmail send succeeds: status transitions to SENT.
    If Gmail send fails: status transitions to APPROVED (recoverable);
    a RuntimeError is raised with the underlying cause.
    """
    _validate_transition(from_status, WorkflowStatus.APPROVED)

    email_row = get_email_by_id(email_id)
    if not email_row:
        raise ValueError(f"Email id='{email_id}' not found in database.")

    to_email = _extract_to_email(email_row.get("sender", ""))
    subject  = email_row.get("subject", "")
    now      = datetime.now().isoformat()

    try:
        from drafts.gmail_sender import send_email as gmail_send
        gmail_send(to_email, subject, reply_text)

        # Send succeeded → go directly to SENT
        update_email_status(
            email_id,
            WorkflowStatus.SENT.value,
            user_edited_reply=reply_text,
            approved_at=now,
            sent_at=now,
        )
        log_action(email_id, "USER", "APPROVED", {"reply_preview": reply_text[:200]})
        log_action(email_id, "USER", "SENT", {"to": to_email})
        record_timeline(email_id, "APPROVED", "USER")
        record_timeline(email_id, "SENT", "USER", f"Reply sent to {to_email}")
        logger.info("Workflow: email id='%s' SENT to '%s'.", email_id, to_email)

    except Exception as exc:
        # Gmail send failed — park at APPROVED so user can retry
        update_email_status(
            email_id,
            WorkflowStatus.APPROVED.value,
            user_edited_reply=reply_text,
            approved_at=now,
        )
        log_action(email_id, "USER", "APPROVED", {"send_failed": str(exc)})
        record_timeline(email_id, "APPROVED", "USER", f"Send failed: {exc}")
        logger.error("Workflow: Gmail send failed for email id='%s': %s", email_id, exc)
        raise RuntimeError(
            f"Email approved and saved, but Gmail send failed: {exc}\n"
            "Open the Approval Center to retry."
        ) from exc


def reject(email_id: str, reason: str = "", from_status: str = "PENDING") -> None:
    """Rejects a pending draft — no email is sent. Transition → REJECTED."""
    _validate_transition(from_status, WorkflowStatus.REJECTED)
    update_email_status(
        email_id,
        WorkflowStatus.REJECTED.value,
        rejection_reason=reason,
        rejected_at=datetime.now().isoformat(),
    )
    log_action(email_id, "USER", "REJECTED", {"reason": reason})
    record_timeline(email_id, "REJECTED", "USER", reason or None)
    logger.info("Workflow: email id='%s' REJECTED. Reason: %s", email_id, reason)


def save_as_draft(email_id: str, from_status: str = "PENDING") -> None:
    """Saves draft for later review. Transition: PENDING → DRAFT_SAVED."""
    _validate_transition(from_status, WorkflowStatus.DRAFT_SAVED)
    update_email_status(
        email_id,
        WorkflowStatus.DRAFT_SAVED.value,
        draft_saved_at=datetime.now().isoformat(),
    )
    log_action(email_id, "USER", "DRAFT_SAVED")
    record_timeline(email_id, "DRAFT_SAVED", "USER")
    logger.info("Workflow: email id='%s' → DRAFT_SAVED.", email_id)


def push_to_gmail_drafts(
    email_id: str,
    to_email: str,
    subject: str,
    reply_text: str,
    from_status: str = "PENDING",
) -> str:
    """
    Creates a Gmail Draft and stores the draft ID.
    Transition: PENDING | DRAFT_SAVED → GMAIL_DRAFT_SAVED
    Returns the Gmail draft ID.
    """
    _validate_transition(from_status, WorkflowStatus.GMAIL_DRAFT_SAVED)

    from drafts.gmail_draft_creator import create_gmail_draft
    draft = create_gmail_draft(to_email, subject, reply_text)
    draft_id = (draft.get("id") or "")

    update_email_status(
        email_id,
        WorkflowStatus.GMAIL_DRAFT_SAVED.value,
        gmail_draft_id=draft_id,
    )
    log_action(email_id, "USER", "GMAIL_DRAFT_SAVED", {"draft_id": draft_id, "to": to_email})
    record_timeline(email_id, "GMAIL_DRAFT_SAVED", "USER", f"Draft ID: {draft_id}")
    logger.info("Workflow: email id='%s' → GMAIL_DRAFT_SAVED (draft_id=%s).", email_id, draft_id)
    return draft_id
