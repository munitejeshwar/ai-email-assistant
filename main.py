from email_engine.fetcher import fetch_emails
from email_engine.parser import parse_email

from ai_processing.summarizer import summarize_email
from ai_processing.classifier import classify_email
from ai_processing.priority_analyzer import analyze_priority

from notifications.telegram_service import send_telegram_message

from database.db_manager import init_db, email_exists, save_email

from drafts.reply_generator import generate_reply
from drafts.gmail_sender import send_email


def main():

    print("\n=== AI EMAIL ASSISTANT ===\n")

    # Initialize database
    init_db()

    # Fetch emails
    raw_emails = fetch_emails(max_results=5)

    for raw in raw_emails:

        parsed = parse_email(raw)

        # Skip already processed emails
        if email_exists(parsed["id"]):

            print(f"⏭️ Skipping already processed email: " f"{parsed['subject']}")

            continue

        print("\n" + "=" * 70)

        print(f"FROM: {parsed['sender']}")
        print(f"SUBJECT: {parsed['subject']}")

        # ==========================================================
        # AI SUMMARY
        # ==========================================================

        print("\n🤖 AI SUMMARY:\n")

        try:

            summary = summarize_email(parsed)

            print(summary)

        except Exception as e:

            summary = f"SUMMARY ERROR: {e}"

            print(summary)

        # ==========================================================
        # AI CATEGORY
        # ==========================================================

        print("\n📂 CATEGORY:")

        try:

            category = classify_email(parsed["subject"], parsed["body"])

            print(category)

        except Exception as e:

            category = "UNKNOWN"

            print("CATEGORY ERROR:", e)

        # ==========================================================
        # AI PRIORITY ANALYSIS
        # ==========================================================

        print("\n⚡ PRIORITY:")

        try:

            priority = analyze_priority(parsed["subject"], parsed["body"])

            print(priority)

        except Exception as e:

            priority = f"PRIORITY ERROR: {e}"

            print(priority)

        # ==========================================================
        # TELEGRAM ALERTS
        # ==========================================================

        try:

            telegram_message = f"""
📩 NEW EMAIL RECEIVED

👤 FROM:
{parsed['sender']}

📝 SUBJECT:
{parsed['subject']}

📨 MESSAGE:
{parsed['body'][:500]}

📂 CATEGORY:
{category}

⚡ PRIORITY:
{priority}
"""

            send_telegram_message(telegram_message)

            print("\n📲 Telegram alert sent.")

        except Exception as e:

            print("\nTELEGRAM ERROR:", e)

        # ==========================================================
        # AUTO REPLY SEND
        # ==========================================================

        try:

            # if category in ["CASUAL", "PERSONAL"]:
             if True:
                print("\n🤖 Generating AI reply...\n")

                reply = generate_reply(
                    parsed["sender"], parsed["subject"], parsed["body"]
                )

                print(reply)

                sender_email = parsed["sender"]

                if "<" in sender_email:

                    sender_email = sender_email.split("<")[1].replace(">", "").strip()

                send_email(sender_email, parsed["subject"], reply)

                print("\n📨 AI auto-reply sent.")

                telegram_reply_message = f"""
🤖 AI AUTO-REPLY SENT

👤 TO:
{sender_email}

📝 SUBJECT:
Re: {parsed['subject']}

📨 ORIGINAL MESSAGE:
{parsed['body'][:500]}

✉️ AI REPLY:
{reply}
"""

                send_telegram_message(telegram_reply_message)

                print("\n📲 Reply notification sent to Telegram.")

        except Exception as e:

            print("\nAUTO-REPLY ERROR:", e)

        # ==========================================================
        # SAVE TO DATABASE
        # ==========================================================

        try:

            save_email(
                {
                    "id": parsed["id"],
                    "sender": parsed["sender"],
                    "subject": parsed["subject"],
                    "summary": summary,
                    "category": category,
                    "priority": priority,
                }
            )

            print("\n💾 Saved to database.")

        except Exception as e:

            print("\nDATABASE ERROR:", e)

        print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
