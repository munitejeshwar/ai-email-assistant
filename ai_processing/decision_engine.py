# ai_processing/decision_engine.py
#
# Orchestrates all AI analysis functions and assembles the canonical
# DecisionEnvelope for a single email.
#
# ── Architectural contract ────────────────────────────────────────────────
# This module is ORCHESTRATION ONLY.
# It MUST NOT:
#   - write to or read from the database
#   - send emails
#   - send Telegram notifications
#   - interact with the dashboard
#   - perform any external side effects beyond the four AI function calls
#
# Its sole responsibility is:
#   1. Call the four *_detailed() AI functions.
#   2. Map their dict outputs into typed result dataclasses.
#   3. Assemble and return a DecisionEnvelope.
#
# Consumers (email_engine/processor.py, dashboard/app.py) are responsible
# for all downstream persistence and communication.
#
# ── Typed model hierarchy ─────────────────────────────────────────────────
#   DecisionEnvelope
#   ├── SummaryResult        ← summarize_email_detailed()
#   ├── ClassificationResult ← classify_email_detailed()
#   ├── PriorityResult       ← analyze_priority_detailed()
#   └── ReplyResult          ← generate_reply_detailed()
#
# ── Design notes ──────────────────────────────────────────────────────────
# - Python dataclasses (stdlib, no new dependencies) are used in preference
#   to Pydantic to keep the dependency footprint minimal. Each *_detailed()
#   function already validates and normalises its own output, so a second
#   validation layer here would be redundant.
# - All dataclasses carry a raw_response field so the full LLM output is
#   always reachable for diagnostics and the audit log.
# - to_database_record() on DecisionEnvelope is the SINGLE point of
#   flattening: it maps nested dataclass fields to SQL column names.
#   db_manager.py calls this method and persists the result without
#   ever importing or inspecting the nested result types.
# - to_dict() (recursive asdict) is retained for JSON export and debugging.

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone

from ai_processing.summarizer import summarize_email_detailed
from ai_processing.classifier import classify_email_detailed
from ai_processing.priority_analyzer import analyze_priority_detailed
from drafts.reply_generator import generate_reply_detailed

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Typed result models
# ═════════════════════════════════════════════════════════════════════════════

@dataclasses.dataclass
class SummaryResult:
    """
    Output of summarize_email_detailed().

    quality_score:
        The model's self-assessed estimate of how well the email could be
        summarised. This is an explainability aid and should not be
        interpreted as an objective or statistically validated measure of
        summary quality. Range: 0.0 (very hard to summarise) – 1.0 (clear
        and easy to summarise).
    """
    summary: str
    quality_score: float        # 0.0 – 1.0; see docstring above
    raw_response: str


@dataclasses.dataclass
class ClassificationResult:
    """
    Output of classify_email_detailed().

    ai_confidence_estimate:
        The model's self-reported estimate of how certain it is about this
        classification. This is an explainability aid and should not be
        interpreted as a calibrated probability or statistically validated
        confidence measure. Range: 0.0 – 1.0.
    """
    category: str               # one of: IMPORTANT|PROMOTION|SOCIAL|SPAM|UPDATES|UNKNOWN
    ai_confidence_estimate: float   # 0.0 – 1.0; see docstring above
    raw_response: str


@dataclasses.dataclass
class PriorityResult:
    """
    Output of analyze_priority_detailed().

    ai_confidence_estimate:
        The model's self-reported estimate of how confident it is in this
        priority assessment. This is an explainability aid and should not
        be interpreted as a calibrated probability. Range: 0.0 – 1.0.
    """
    priority: str               # legacy format: "PRIORITY: X/10\nURGENCY: ...\nACTION: ..."
    priority_score: int         # 1–10 (0 on failure)
    urgency: str                # LOW | MEDIUM | HIGH | UNKNOWN
    action_required: bool
    risk_level: str             # LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN
    reasoning: str              # one-sentence AI rationale
    ai_confidence_estimate: float   # 0.0 – 1.0; see docstring above
    raw_response: str


@dataclasses.dataclass
class ReplyResult:
    """
    Output of generate_reply_detailed().

    ai_confidence_estimate:
        The model's self-reported estimate of how appropriate the generated
        reply is for the given email context. This is an explainability aid
        and should not be interpreted as a calibrated probability or
        objective measure of reply quality. Human review and approval
        remains mandatory regardless of this score. Range: 0.0 – 1.0.
    """
    draft_reply: str
    suggested_tone: str         # e.g. "Casual", "Professional", "Empathetic"
    reply_rationale: str        # one-sentence generation rationale
    ai_confidence_estimate: float   # 0.0 – 1.0; see docstring above
    raw_response: str


@dataclasses.dataclass
class DecisionEnvelope:
    """
    Canonical XAI envelope for a single email, produced by the Decision Engine.

    Aggregates the typed outputs of all four AI analysis functions alongside
    the email's identity fields. This is the single object that flows from
    the Decision Engine to the pipeline processor, the database layer, and
    the Streamlit Approval Center.

    assembled_at:
        UTC ISO-8601 timestamp of when this envelope was assembled. Used as
        the basis for the DRAFT_CREATED event in the decision_timeline table.

    workflow_status:
        Current lifecycle state of this email in the HITL approval workflow.
        Default is "PENDING" (AI processed; awaiting human decision).
        Valid values: PENDING | DRAFT_SAVED | APPROVED | REJECTED | SENT |
        GMAIL_DRAFT_SAVED
        The dashboard and audit logger update this field via db_manager;
        the Decision Engine always initialises it to PENDING.

    to_dict():
        Recursive asdict() — use for JSON serialisation and debugging.

    to_database_record():
        Returns the flat SQL-ready dict. This is the SINGLE point of
        flattening. db_manager.save_envelope() calls this and persists
        the result without ever inspecting nested dataclass types.
    """
    # ── Email identity ────────────────────────────────────────────────────
    email_id: str
    sender: str
    subject: str
    body: str
    date: str

    # ── AI analysis results ───────────────────────────────────────────────
    summary: SummaryResult
    classification: ClassificationResult
    priority: PriorityResult
    reply: ReplyResult

    # ── Assembly metadata ─────────────────────────────────────────────────
    assembled_at: str           # UTC ISO-8601; set by analyse()

    # ── Workflow state ────────────────────────────────────────────────────
    # Default PENDING: AI processed; human decision required in dashboard.
    # The Decision Engine always initialises this to PENDING.
    # Only the dashboard and audit logger may transition it to other states.
    # Valid states: PENDING | DRAFT_SAVED | APPROVED | REJECTED | SENT |
    #               GMAIL_DRAFT_SAVED
    workflow_status: str = "PENDING"

    def to_dict(self) -> dict:
        """
        Recursively converts this envelope and all nested dataclasses to a
        plain dict using dataclasses.asdict().

        Use this for JSON serialisation, logging, and debugging.
        For SQL persistence, use to_database_record() instead.
        """
        return dataclasses.asdict(self)

    def to_database_record(self) -> dict:
        """
        Returns a flat dict of SQL-ready column values for this envelope.

        This is the SINGLE point of flattening in the codebase.
        db_manager.save_envelope() calls this method and persists the
        result without ever importing or inspecting the nested result types
        (SummaryResult, ClassificationResult, PriorityResult, ReplyResult).

        Column mapping:
          id                    ← email_id
          sender                ← sender
          subject               ← subject
          summary               ← summary.summary
          category              ← classification.category
          priority              ← priority.priority  (legacy format string)
          ai_confidence_estimate← classification.ai_confidence_estimate
                                  (primary confidence shown in the dashboard;
                                  represents the model's self-reported certainty
                                  about the email classification. It is an
                                  explainability aid and must not be interpreted
                                  as a calibrated probability.)
          risk_level            ← priority.risk_level
          suggested_tone        ← reply.suggested_tone
          reasoning             ← priority.reasoning
          draft_reply           ← reply.draft_reply
          reply_rationale       ← reply.reply_rationale
          status                ← workflow_status  (domain field; default "PENDING")

        Fields NOT included (set by later workflow events):
          processed_at          — set by db_manager to datetime.now()
          user_edited_reply     — set when user edits in dashboard
          rejection_reason      — set when user rejects in dashboard
          gmail_draft_id        — set when Gmail draft is created
          approved_at           — set on approval
          rejected_at           — set on rejection
          sent_at               — set on send
          draft_saved_at        — set on DRAFT_SAVED
        """
        return {
            "id":                     self.email_id,
            "sender":                 self.sender,
            "subject":                self.subject,
            "summary":                self.summary.summary,
            "category":               self.classification.category,
            "priority":               self.priority.priority,
            "ai_confidence_estimate": self.classification.ai_confidence_estimate,
            "risk_level":             self.priority.risk_level,
            "suggested_tone":         self.reply.suggested_tone,
            "reasoning":              self.priority.reasoning,
            "draft_reply":            self.reply.draft_reply,
            "reply_rationale":        self.reply.reply_rationale,
            "status":                 self.workflow_status,  # reads domain field; never hardcoded
        }


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════

def _build_summary_result(raw: dict) -> SummaryResult:
    """Maps the dict returned by summarize_email_detailed() to SummaryResult."""
    return SummaryResult(
        summary=raw.get("summary", ""),
        quality_score=raw.get("quality_score", 0.0),
        raw_response=raw.get("raw_response", ""),
    )


def _build_classification_result(raw: dict) -> ClassificationResult:
    """Maps the dict returned by classify_email_detailed() to ClassificationResult."""
    return ClassificationResult(
        category=raw.get("category", "UNKNOWN"),
        ai_confidence_estimate=raw.get("ai_confidence_estimate", 0.0),
        raw_response=raw.get("raw_response", ""),
    )


def _build_priority_result(raw: dict) -> PriorityResult:
    """Maps the dict returned by analyze_priority_detailed() to PriorityResult."""
    return PriorityResult(
        priority=raw.get("priority", "PRIORITY: 0/10\nURGENCY: UNKNOWN\nACTION: NO"),
        priority_score=raw.get("priority_score", 0),
        urgency=raw.get("urgency", "UNKNOWN"),
        action_required=raw.get("action_required", False),
        risk_level=raw.get("risk_level", "UNKNOWN"),
        reasoning=raw.get("reasoning", ""),
        ai_confidence_estimate=raw.get("ai_confidence_estimate", 0.0),
        raw_response=raw.get("raw_response", ""),
    )


def _build_reply_result(raw: dict) -> ReplyResult:
    """Maps the dict returned by generate_reply_detailed() to ReplyResult."""
    return ReplyResult(
        draft_reply=raw.get("draft_reply", ""),
        suggested_tone=raw.get("suggested_tone", "Unknown"),
        reply_rationale=raw.get("reply_rationale", ""),
        ai_confidence_estimate=raw.get("ai_confidence_estimate", 0.0),
        raw_response=raw.get("raw_response", ""),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════

def analyse(parsed_email: dict) -> DecisionEnvelope:
    """
    Orchestrates all four AI analysis functions for a single parsed email
    and assembles the results into a typed DecisionEnvelope.

    This function is PURE ORCHESTRATION — it has no side effects beyond the
    four AI API calls it delegates to. The caller (email_engine/processor.py)
    is responsible for all database writes, Telegram notifications, and any
    other downstream actions.

    Args:
        parsed_email: The dict produced by email_engine/parser.py, containing
                      at minimum: id, sender, subject, body, date.

    Returns:
        A fully populated DecisionEnvelope. On individual AI function failure,
        the corresponding nested result contains safe fallback values (e.g.
        category="UNKNOWN", ai_confidence_estimate=0.0) — the envelope is
        always returned; it is never None and never raises.

    Example::

        from email_engine.parser import parse_email
        from ai_processing.decision_engine import analyse

        parsed = parse_email(raw_gmail_message)
        envelope = analyse(parsed)

        print(envelope.classification.category)
        print(envelope.priority.risk_level)
        print(envelope.reply.draft_reply)
        record = envelope.to_database_record()  # flat dict for save_envelope()
    """
    email_id = parsed_email.get("id", "")
    sender   = parsed_email.get("sender", "")
    subject  = parsed_email.get("subject", "")
    body     = parsed_email.get("body", "")
    date     = parsed_email.get("date", "")

    logger.info("Decision Engine: analysing email id='%s' subject='%s'", email_id, subject)

    # ── Step 1: Summarise ─────────────────────────────────────────────────
    # summarize_email_detailed() accepts the full parsed dict directly.
    logger.debug("Decision Engine: calling summariser.")
    summary_result = _build_summary_result(
        summarize_email_detailed(parsed_email)
    )

    # ── Step 2: Classify ──────────────────────────────────────────────────
    logger.debug("Decision Engine: calling classifier.")
    classification_result = _build_classification_result(
        classify_email_detailed(subject, body)
    )

    # ── Step 3: Priority analysis ─────────────────────────────────────────
    logger.debug("Decision Engine: calling priority analyser.")
    priority_result = _build_priority_result(
        analyze_priority_detailed(subject, body)
    )

    # ── Step 4: Generate draft reply ──────────────────────────────────────
    logger.debug("Decision Engine: calling reply generator.")
    reply_result = _build_reply_result(
        generate_reply_detailed(sender, subject, body)
    )

    # ── Assemble envelope ─────────────────────────────────────────────────
    envelope = DecisionEnvelope(
        email_id=email_id,
        sender=sender,
        subject=subject,
        body=body,
        date=date,
        summary=summary_result,
        classification=classification_result,
        priority=priority_result,
        reply=reply_result,
        assembled_at=datetime.now(timezone.utc).isoformat(),
    )

    logger.info(
        "Decision Engine: envelope assembled for email id='%s' "
        "category='%s' priority_score=%d risk='%s'",
        email_id,
        envelope.classification.category,
        envelope.priority.priority_score,
        envelope.priority.risk_level,
    )

    return envelope
