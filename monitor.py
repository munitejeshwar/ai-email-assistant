# monitor.py
# Continuous email polling loop. Delegates all AI analysis and persistence
# to the pipeline (process_email) and workflow layer (workflow.submit_email).

import time
import logging

from email_engine.fetcher import fetch_emails
from email_engine.parser import parse_email
from email_engine.processor import process_email as run_pipeline

from database.db_manager import init_db, email_exists

import workflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # seconds


def _handle_email(raw: dict) -> None:
    parsed = parse_email(raw)

    if email_exists(parsed["id"]):
        print(f"⏭️  Already processed: {parsed['subject']}")
        return

    print("\n" + "=" * 70)
    print(f"📧 FROM:    {parsed['sender']}")
    print(f"📝 SUBJECT: {parsed['subject']}")
    print("⏳ Running AI pipeline...")

    try:
        envelope = run_pipeline(raw)
    except Exception as exc:
        logger.error("Pipeline error for email id='%s': %s", parsed["id"], exc)
        print(f"❌ Pipeline error: {exc}")
        return

    print(f"📂 {envelope.classification.category}  "
          f"| ⚡ {envelope.priority.priority_score}/10  "
          f"| ⚠️  {envelope.priority.risk_level}")
    print(f"💬 {envelope.summary.summary[:200]}")

    try:
        workflow.submit_email(envelope)
        print("💾 Saved — status=PENDING. Awaiting approval in dashboard.")
    except Exception as exc:
        logger.error("Workflow error for email id='%s': %s", envelope.email_id, exc)
        print(f"❌ Workflow error: {exc}")


def monitor_loop() -> None:
    print("\n🚀 HITL Email Workflow Monitor started.")
    print(f"⏱️  Polling every {CHECK_INTERVAL}s for unread emails.\n")

    init_db()

    while True:
        try:
            raw_emails = fetch_emails(max_results=5, query="is:unread")
            for raw in raw_emails:
                _handle_email(raw)
        except Exception as exc:
            logger.error("Monitor loop error: %s", exc)
            print(f"❌ Monitor error: {exc}")

        print(f"\n😴 Sleeping {CHECK_INTERVAL}s...\n")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor_loop()