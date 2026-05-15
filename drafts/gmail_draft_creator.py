import base64

from auth.gmail_auth import get_gmail_service


def create_gmail_draft(to_email, subject, reply_text):

    service = get_gmail_service()

    message = f"""To: {to_email}
Subject: Re: {subject}

{reply_text}
"""

    encoded_message = base64.urlsafe_b64encode(
        message.encode("utf-8")
    ).decode("utf-8")

    draft_body = {
        "message": {
            "raw": encoded_message
        }
    }

    draft = service.users().drafts().create(
        userId="me",
        body=draft_body
    ).execute()

    return draft