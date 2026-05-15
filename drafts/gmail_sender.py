import base64

from email.mime.text import MIMEText

from auth.gmail_auth import get_gmail_service


def send_email(to_email, subject, reply_text):

    service = get_gmail_service()

    message = MIMEText(reply_text)

    message["to"] = to_email
    message["subject"] = f"Re: {subject}"

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    body = {"raw": raw_message}

    sent_message = service.users().messages().send(userId="me", body=body).execute()

    return sent_message
