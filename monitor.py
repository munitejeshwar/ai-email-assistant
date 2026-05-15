# monitor.py

import time

from email_engine.fetcher import fetch_emails
from email_engine.parser import parse_email

from ai_processing.summarizer import summarize_email
from ai_processing.classifier import classify_email
from ai_processing.priority import analyze_priority

from database.db_manager import (
    init_db,
    save_email,
    email_exists
)


CHECK_INTERVAL = 60  # seconds


def process_email(raw):

    parsed = parse_email(raw)

    # Skip duplicates
    if email_exists(parsed["id"]):
        print(f"⏭️ Already processed: {parsed['subject']}")
        return

    print("\n" + "=" * 70)
    print(f"📧 FROM: {parsed['sender']}")
    print(f"📝 SUBJECT: {parsed['subject']}")

    # Summary
    try:
        summary = summarize_email(parsed)
    except Exception as e:
        summary = f"SUMMARY ERROR: {e}"

    print("\n🤖 SUMMARY:")
    print(summary)

    # Category
    try:
        category = classify_email(
            parsed["subject"],
            parsed["body"]
        )
    except Exception as e:
        category = f"CLASSIFICATION ERROR: {e}"

    print(f"\n📂 CATEGORY: {category}")

    # Priority
    try:
        priority = analyze_priority(
            parsed["subject"],
            parsed["body"]
        )
    except Exception as e:
        priority = f"PRIORITY ERROR: {e}"

    print(f"\n⚡ PRIORITY:\n{priority}")

    # Save
    save_email({
        "id": parsed["id"],
        "sender": parsed["sender"],
        "subject": parsed["subject"],
        "summary": summary,
        "category": category,
        "priority": priority
    })

    print("\n💾 Saved to database.")


def monitor_loop():

    print("\n🚀 AI EMAIL AGENT STARTED")
    print(f"⏱️ Checking every {CHECK_INTERVAL} seconds...\n")

    init_db()

    while True:

        try:

            raw_emails = fetch_emails(
                max_results=5,
                query="is:unread"
            )

            for raw in raw_emails:
                process_email(raw)

        except Exception as e:
            print(f"\n❌ MONITOR ERROR: {e}")

        print(f"\n😴 Sleeping for {CHECK_INTERVAL} seconds...\n")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor_loop()