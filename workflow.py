# workflow.py
#
# Approval Workflow Service for the Human-Centric Intelligent Email
# Workflow Framework.
#
# ── Responsibility ────────────────────────────────────────────────────────
# This module is the single integration point between the pipeline and all
# downstream actions for an email. Entry points (main.py, monitor.py,
# dashboard/app.py) call this module instead of calling save_envelope(),
# gmail_sender, or audit_logger directly.
#
# ── WorkflowStatus ────────────────────────────────────────────────────────
# WorkflowStatus(str, Enum) is the canonical type for all status values.
# Inheriting from str means every member IS a plain Python string —
# database drivers and JSON serialisers receive "PENDING", not an enum repr.
#
#   PENDING          — AI analysed; awaiting human decision in dashboard.
#   DRAFT_SAVED      — Human saved the draft for later review; not sent.
#   GMAIL_DRAFT_SAVED— Draft pushed to Gmail's Drafts folder; not sent.
#   APPROVED         — Human approved the reply; send is in progress.
#   SENT             — Reply sent successfully. Terminal state.
#   REJECTED         — Human rejected the reply; no email sent. Terminal state.
#
# ── Valid state-transition graph ─────────────────────────────────────────
#
#   PENDING ──────────────────────────────────────┐
#      │                                          │
#      ├──→ DRAFT_SAVED ─────────────────────┐   │
#      │        │                            │   │
#      ├──→ GMAIL_DRAFT_SAVED ───────────┐   │   │
#      │                                 │   │   │
#      └──→ APPROVED ─→ SENT (terminal)  │   │   │
#                ↑───────────────────────┘───┘   │
#   REJECTED (terminal) ←──────────────────────── ┘
#
# ── Layering rules ────────────────────────────────────────────────────────
# MAY import from: database/, notifications/, drafts/, database/audit_logger
# MUST NOT import from: ai_processing/, email_engine/, dashboard/

import enum
import logging

from database.db_manager import save_envelope

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# WorkflowStatus — canonical status enum
# ═════════════════════════════════════════════════════════════════════════════

class WorkflowStatus(str, enum.Enum):
    """
    Canonical lifecycle states for an email in the HITL approval workflow.

    Inherits from str so that every member is a plain Python string
    (e.g. WorkflowStatus.PENDING == "PENDING" is True). This means:
      - SQLite stores the raw string value, not an enum repr.
      - JSON serialisation works without .value calls.
      - DecisionEnvelope.workflow_status (typed as str) is directly
        comparable with WorkflowStatus members.
    """
    PENDING           = "PENDING"
    DRAFT_SAVED       = "DRAFT_SAVED"
    GMAIL_DRAFT_SAVED = "GMAIL_DRAFT_SAVED"
    APPROVED          = "APPROVED"
    SENT              = "SENT"
    REJECTED          = "REJECTED"


# ═════════════════════════════════════════════════════════════════════════════
# Transition graph — authoritative definition of allowed state changes
# ═════════════════════════════════════════════════════════════════════════════

# Maps each state to the set of states it may legally transition INTO.
# Terminal states (SENT, REJECTED) map to empty sets.
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
    WorkflowStatus.SENT:     set(),   # terminal — no further transitions allowed
    WorkflowStatus.REJECTED: set(),   # terminal — no further transitions allowed
}


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════

def _validate_transition(from_status: str, to_status: WorkflowStatus) -> None:
    """
    Validates that the requested workflow state transition is legal.

    Args:
        from_status: Current status string on the DecisionEnvelope or DB record.
        to_status:   The WorkflowStatus being requested.

    Raises:
        ValueError: if from_status is not a recognised WorkflowStatus value.
        PermissionError: if the transition is not in VALID_TRANSITIONS, giving
                         a clear message listing the allowed destinations.
    """
    try:
        current = WorkflowStatus(from_status)
    except ValueError:
        raise ValueError(
            f"'{from_status}' is not a recognised WorkflowStatus value. "
            f"Valid values: {[s.value for s in WorkflowStatus]}"
        )

    allowed = VALID_TRANSITIONS.get(current, set())

    if to_status not in allowed:
        if not allowed:
            raise PermissionError(
                f"'{current.value}' is a terminal state. "
                "No further workflow transitions are permitted."
            )
        raise PermissionError(
            f"Invalid workflow transition: '{current.value}' → '{to_status.value}'. "
            f"Allowed destinations: {sorted(s.value for s in allowed)}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════

def submit_email(envelope) -> object:
    """
    Submits a new email to the HITL approval workflow.

    Called by the pipeline (main.py / monitor.py) immediately after
    process_email() produces a DecisionEnvelope.

    Guards:
      - Validates that the envelope's workflow_status is PENDING.
        A non-PENDING envelope indicates a programming error in the caller
        (e.g. re-submitting an already-persisted email).

    Current behaviour:
        1. Validates workflow_status == PENDING.
        2. Persists the envelope via save_envelope() (status = PENDING).
        3. Returns the envelope unchanged.

    Future behaviour (Phase 3):
        4. Log DRAFT_CREATED to audit_log table.
        5. Record DRAFT_CREATED in decision_timeline table.
        6. Send Telegram notification with summary, priority, and
           AI Confidence Estimate.

    Args:
        envelope: A DecisionEnvelope with workflow_status == "PENDING".

    Returns:
        The same envelope, unchanged.

    Raises:
        ValueError: if the envelope's workflow_status is not PENDING.
    """
    if envelope.workflow_status != WorkflowStatus.PENDING.value:
        raise ValueError(
            f"submit_email() expects a PENDING envelope, "
            f"got '{envelope.workflow_status}'. "
            "Use the appropriate workflow function for this status."
        )

    logger.info(
        "Workflow: submitting email id='%s' subject='%s' status='%s'.",
        envelope.email_id,
        envelope.subject,
        envelope.workflow_status,
    )

    save_envelope(envelope)

    logger.info(
        "Workflow: email id='%s' persisted. Awaiting human decision in dashboard.",
        envelope.email_id,
    )

    # ── Future expansion points ───────────────────────────────────────────
    # Phase 3: audit_logger.log_action(envelope.email_id, "AI", "DRAFT_CREATED")
    # Phase 3: decision_timeline.record(envelope.email_id, "DRAFT_CREATED", "AI")
    # Phase 5: notifications.send_new_email_alert(envelope)

    return envelope


def approve_and_send(email_id: str, reply_text: str, from_status: str = "PENDING") -> None:
    """
    Approves a pending draft reply and sends it via Gmail.

    Transition: PENDING | DRAFT_SAVED | GMAIL_DRAFT_SAVED → APPROVED → SENT

    Planned behaviour:
        1. _validate_transition(from_status, WorkflowStatus.APPROVED)
        2. Update status to APPROVED; set approved_at timestamp.
        3. Call drafts/gmail_sender.send_email() with reply_text.
        4. Update status to SENT; set sent_at timestamp.
        5. Log APPROVED and SENT to audit_log and decision_timeline.
        6. Send Telegram confirmation.

    Raises:
        NotImplementedError: until Phase 4 dashboard implementation.
        PermissionError: if from_status cannot transition to APPROVED.
    """
    _validate_transition(from_status, WorkflowStatus.APPROVED)   # guard runs now
    raise NotImplementedError(
        "approve_and_send() is not yet implemented. "
        "Will be wired in Phase 4 (Streamlit Approval Center)."
    )


def reject(email_id: str, reason: str = "", from_status: str = "PENDING") -> None:
    """
    Rejects a pending draft — no email is sent.

    Transition: PENDING | DRAFT_SAVED | GMAIL_DRAFT_SAVED → REJECTED

    Planned behaviour:
        1. _validate_transition(from_status, WorkflowStatus.REJECTED)
        2. Update status to REJECTED; set rejected_at; store rejection_reason.
        3. Log REJECTED to audit_log and decision_timeline.
        4. Optionally send Telegram rejection confirmation.

    Raises:
        NotImplementedError: until Phase 4 dashboard implementation.
        PermissionError: if from_status cannot transition to REJECTED.
    """
    _validate_transition(from_status, WorkflowStatus.REJECTED)   # guard runs now
    raise NotImplementedError(
        "reject() is not yet implemented. "
        "Will be wired in Phase 4 (Streamlit Approval Center)."
    )


def save_as_draft(email_id: str, from_status: str = "PENDING") -> None:
    """
    Saves the AI-generated draft for later review without sending.

    Transition: PENDING → DRAFT_SAVED

    Planned behaviour:
        1. _validate_transition(from_status, WorkflowStatus.DRAFT_SAVED)
        2. Update status to DRAFT_SAVED; set draft_saved_at timestamp.
        3. Log DRAFT_SAVED to audit_log and decision_timeline.

    Raises:
        NotImplementedError: until Phase 4 dashboard implementation.
        PermissionError: if from_status cannot transition to DRAFT_SAVED.
    """
    _validate_transition(from_status, WorkflowStatus.DRAFT_SAVED)  # guard runs now
    raise NotImplementedError(
        "save_as_draft() is not yet implemented. "
        "Will be wired in Phase 4 (Streamlit Approval Center)."
    )


def push_to_gmail_drafts(
    email_id: str,
    to_email: str,
    subject: str,
    reply_text: str,
    from_status: str = "PENDING",
) -> None:
    """
    Creates a Gmail Draft from the AI-generated reply (does not send).

    Transition: PENDING | DRAFT_SAVED → GMAIL_DRAFT_SAVED

    Planned behaviour:
        1. _validate_transition(from_status, WorkflowStatus.GMAIL_DRAFT_SAVED)
        2. Call drafts/gmail_draft_creator.create_gmail_draft().
        3. Store gmail_draft_id; update status to GMAIL_DRAFT_SAVED.
        4. Log event to audit_log and decision_timeline.

    Raises:
        NotImplementedError: until Phase 4 dashboard implementation.
        PermissionError: if from_status cannot transition to GMAIL_DRAFT_SAVED.
    """
    _validate_transition(from_status, WorkflowStatus.GMAIL_DRAFT_SAVED)  # guard runs now
    raise NotImplementedError(
        "push_to_gmail_drafts() is not yet implemented. "
        "Will be wired in Phase 4 (Streamlit Approval Center)."
    )
