# main.py
#
# Entry point for the Human-Centric Intelligent Email Workflow Framework.
#
# Pipeline (per email):
#   1. fetch_emails()          — retrieve recent emails from Gmail API
#   2. parse_email(raw)        — extract id, sender, subject, body, date
#   3. email_exists(id)        — skip if already processed (deduplication)
#   4. process_email(raw)      — run all AI analysis; return DecisionEnvelope
#   5. workflow.submit_email() — persist with status=PENDING; future: audit + Telegram
#   6. send_telegram_message() — notify user of new pending email
#
# Human decision (approve / reject / save draft) happens in:
#   dashboard/app.py  — Streamlit Approval Center (Phase 4)
#
# Removed (Phase 2 HITL refactor):
#   Auto-send: main.py previously called send_email() unconditionally
#   with an `if True:` bypass. This violated the Human-in-the-Loop principle.
#   Replies are now drafted by the AI, persisted with status=PENDING, and
#   sent ONLY after explicit human approval in the Approval Center.
#   See workflow.approve_and_send() — implemented in Phase 4.

import logging

from email_engine.fetcher import fetch_emails
from email_engine.parser import parse_email
from email_engine.processor import process_email

from notifications.telegram_service import send_telegram_message

from database.db_manager import init_db, email_exists

import workflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():

    print("\n=== Human-Centric Intelligent Email Workflow Framework ===\n")

    # Initialise database — creates schema + runs all migrations.
    init_db()

    # Fetch recent emails from Gmail.
    raw_emails = fetch_emails(max_results=5)

    for raw in raw_emails:

        # Parse early to get the ID for deduplication.
        # parse_email() is a pure data transformation — no I/O cost.
        parsed = parse_email(raw)

        # ── Deduplication ─────────────────────────────────────────────────
        if email_exists(parsed["id"]):
            print(f"⏭️  Skipping already processed email: {parsed['subject']}")
            continue

        print("\n" + "=" * 70)
        print(f"FROM:    {parsed['sender']}")
        print(f"SUBJECT: {parsed['subject']}")
        print("⏳ Running AI analysis pipeline...")

        # ── AI Pipeline ───────────────────────────────────────────────────
        # process_email() calls parse_email() internally and runs all four
        # AI functions (summarise, classify, prioritise, generate reply).
        # It returns a fully typed DecisionEnvelope with no side effects.
        #
        # Note: parse_email() is called twice (once above for deduplication,
        # once inside process_email). It is a pure/cheap function and this
        # avoids coupling the deduplication check to process_email's internals.
        try:
            envelope = process_email(raw)
        except Exception as exc:
            logger.error(
                "Pipeline failed for email id='%s': %s", parsed["id"], exc
            )
            print(f"\n❌ Pipeline error — skipping: {exc}")
            continue

        # ── Print AI analysis to console ──────────────────────────────────
        print(f"\n🤖 SUMMARY:\n{envelope.summary.summary}")
        print(f"\n📂 CATEGORY:  {envelope.classification.category}"
              f"  (AI Confidence: {envelope.classification.ai_confidence_estimate:.0%})")
        print(f"\n⚡ PRIORITY:  {envelope.priority.priority_score}/10"
              f"  |  URGENCY: {envelope.priority.urgency}"
              f"  |  RISK: {envelope.priority.risk_level}")
        print(f"\n💬 REASONING: {envelope.priority.reasoning}")
        print(f"\n✍️  DRAFT REPLY TONE: {envelope.reply.suggested_tone}")
        print(f"\n📝 DRAFT REPLY:\n{envelope.reply.draft_reply}")

        # ── HITL Workflow Submission ───────────────────────────────────────
        # Persists the envelope with status=PENDING.
        # No email is sent here. The human must approve in the dashboard.
        try:
            workflow.submit_email(envelope)
            print("\n💾 Saved to database with status=PENDING.")
            print("➡️  Open the Approval Center to review and approve.")
        except Exception as exc:
            logger.error(
                "Workflow submission failed for email id='%s': %s",
                envelope.email_id, exc,
            )
            print(f"\n❌ Workflow error: {exc}")
            continue

        # ── Telegram Notification ─────────────────────────────────────────
        # Alerts the user that a new email is awaiting review.
        # This is a notification only — no reply is sent automatically.
        try:
            telegram_message = (
                f"📩 NEW EMAIL — PENDING REVIEW\n\n"
                f"👤 FROM:\n{envelope.sender}\n\n"
                f"📝 SUBJECT:\n{envelope.subject}\n\n"
                f"📂 CATEGORY: {envelope.classification.category}\n"
                f"⚡ PRIORITY: {envelope.priority.priority_score}/10  "
                f"URGENCY: {envelope.priority.urgency}\n"
                f"⚠️  RISK: {envelope.priority.risk_level}\n\n"
                f"💬 AI SUMMARY:\n{envelope.summary.summary[:400]}\n\n"
                f"🔍 REASONING: {envelope.priority.reasoning}\n\n"
                f"➡️  Open the Approval Center to review, edit, and approve."
            )

            send_telegram_message(telegram_message)
            print("\n📲 Telegram notification sent.")

        except Exception as exc:
            # Telegram failure is non-fatal — the email is already persisted.
            logger.warning("Telegram notification failed: %s", exc)
            print(f"\n⚠️  Telegram notification failed (non-fatal): {exc}")

        print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
