# email_engine/processor.py
#
# Pipeline orchestrator — transforms a raw Gmail API message into a
# fully analysed, typed DecisionEnvelope.
#
# ── Architectural contract ────────────────────────────────────────────────
# This module is ORCHESTRATION ONLY.
# It MUST NOT:
#   - write to or read from the database
#   - send emails
#   - send Telegram notifications
#   - interact with the dashboard or any UI layer
#   - flatten or serialise the DecisionEnvelope
#
# Its sole responsibility is:
#   parse_email(raw) → analyse(parsed) → DecisionEnvelope
#
# ── Caller responsibilities ───────────────────────────────────────────────
# The caller (main.py, monitor.py) is responsible for:
#   1. Deduplication — checking email_exists(raw["id"]) before calling
#      process_email(). The Gmail API raw message exposes "id" directly
#      so no pre-parsing is required for this check.
#   2. Persistence — calling save_envelope(envelope) from database/db_manager.
#   3. Notifications — calling send_email_alert(envelope) from notifications/.
#   4. Gmail draft creation — calling create_gmail_draft() from drafts/ if
#      the user has enabled that option.
#
# ── Deduplication note ────────────────────────────────────────────────────
# process_email() always processes the message it receives. It does not
# consult the database. This keeps the processor decoupled from SQLite and
# makes it trivially testable without any database fixture.
# The caller owns the deduplication gate.
#
# ── Data flow ─────────────────────────────────────────────────────────────
#   raw Gmail API dict
#       └── parse_email()            [email_engine/parser.py]
#             └── analyse()          [ai_processing/decision_engine.py]
#                   ├── summarize_email_detailed()
#                   ├── classify_email_detailed()
#                   ├── analyze_priority_detailed()
#                   └── generate_reply_detailed()
#                    → DecisionEnvelope  (returned to caller, intact)

import logging

from email_engine.parser import parse_email
from ai_processing.decision_engine import analyse, DecisionEnvelope

logger = logging.getLogger(__name__)


def process_email(raw_message: dict) -> DecisionEnvelope:
    """
    Transforms a raw Gmail API message into a fully analysed DecisionEnvelope.

    Pipeline steps:
        1. parse_email(raw_message)  — extracts id, sender, subject, body, date
        2. analyse(parsed)           — runs all four AI functions and assembles
                                       the typed DecisionEnvelope

    This function is pure orchestration. It has no side effects:
        - No database reads or writes
        - No Telegram messages
        - No email sends
        - No dashboard interactions

    The returned DecisionEnvelope is always fully populated. If an individual
    AI function fails internally, its corresponding nested result will contain
    safe fallback values (e.g. category="UNKNOWN", ai_confidence_estimate=0.0).
    The envelope is never None and this function never raises on AI failures.

    Args:
        raw_message: A raw Gmail API message dict as returned by
                     email_engine/fetcher.py (format="full"). Must contain
                     at minimum a "payload" key for parsing and an "id" key.

    Returns:
        DecisionEnvelope: the canonical typed XAI result for this email.

    Caller contract:
        Before calling this function, the caller must:
        1. Check email_exists(raw_message["id"]) and skip if True.
           (raw_message["id"] is available directly — no pre-parsing needed.)
        2. After receiving the envelope, call save_envelope(envelope) from
           database/db_manager to persist it.
        3. Optionally call send_email_alert(envelope) from notifications/.

    Example::

        from email_engine.fetcher import fetch_emails
        from email_engine.processor import process_email
        from database.db_manager import email_exists, save_envelope

        for raw in fetch_emails(max_results=5):
            if email_exists(raw["id"]):
                logger.info("Skipping already processed: %s", raw["id"])
                continue

            envelope = process_email(raw)
            save_envelope(envelope)
    """
    email_id = raw_message.get("id", "<unknown>")
    logger.info("Processor: starting pipeline for email id='%s'.", email_id)

    # ── Step 1: Parse ─────────────────────────────────────────────────────
    # parse_email is a pure data transformation with no I/O. It extracts
    # id, sender, subject, body, date, and snippet from the Gmail payload.
    parsed_email = parse_email(raw_message)

    logger.info(
        "Processor: parsed email id='%s' subject='%s' from='%s'.",
        parsed_email.get("id"),
        parsed_email.get("subject"),
        parsed_email.get("sender"),
    )

    # ── Step 2: Analyse ───────────────────────────────────────────────────
    # analyse() is also pure orchestration (see ai_processing/decision_engine).
    # It calls all four *_detailed() AI functions and returns the typed
    # DecisionEnvelope. The envelope is returned intact — not flattened here.
    envelope = analyse(parsed_email)

    logger.info(
        "Processor: pipeline complete for email id='%s'. "
        "category='%s' priority_score=%d risk='%s' "
        "reply_tone='%s'.",
        envelope.email_id,
        envelope.classification.category,
        envelope.priority.priority_score,
        envelope.priority.risk_level,
        envelope.reply.suggested_tone,
    )

    return envelope
