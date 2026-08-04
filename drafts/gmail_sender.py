import base64
import logging
from email.mime.text import MIMEText

from auth.gmail_auth import get_gmail_service

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, reply_text: str) -> dict:
    """
    Sends a plain-text reply via the Gmail API.

    Args:
        to_email:   Recipient address (bare address, no display name).
        subject:    Original subject — will be prefixed with 'Re: '.
        reply_text: Body text (UTF-8; non-ASCII characters are safe).

    Returns:
        The Gmail API message resource dict (contains 'id', 'threadId', etc.).

    Raises:
        Exception: re-raises any Gmail API or auth error to the caller.
                   The caller (workflow.approve_and_send) handles fallback.
    """
    service = get_gmail_service()

    # MIMEText with explicit utf-8 charset handles non-ASCII content safely.
    message = MIMEText(reply_text, "plain", "utf-8")
    message["to"]      = to_email
    message["subject"] = f"Re: {subject}"

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    try:
        sent = service.users().messages().send(
            userId="me", body={"raw": raw_message}
        ).execute()
        logger.info("gmail_sender: sent message id='%s' to='%s'.", sent.get("id"), to_email)
        return sent
    except Exception as exc:
        logger.error("gmail_sender: send failed to='%s': %s", to_email, exc)
        raise
