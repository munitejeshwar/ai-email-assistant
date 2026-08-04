import base64
import logging
from email.mime.text import MIMEText

from auth.gmail_auth import get_gmail_service

logger = logging.getLogger(__name__)


def create_gmail_draft(to_email: str, subject: str, reply_text: str) -> dict:
    """
    Creates a Gmail Draft (does NOT send).

    Args:
        to_email:   Recipient address (bare address, no display name).
        subject:    Original subject — will be prefixed with 'Re: '.
        reply_text: Draft body text (UTF-8 safe).

    Returns:
        The Gmail API draft resource dict (contains 'id', 'message', etc.).

    Raises:
        Exception: re-raises any Gmail API or auth error to the caller.
    """
    service = get_gmail_service()

    message = MIMEText(reply_text, "plain", "utf-8")
    message["to"]      = to_email
    message["subject"] = f"Re: {subject}"

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    try:
        draft = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": encoded}},
        ).execute()
        logger.info("gmail_draft_creator: draft id='%s' created for to='%s'.", draft.get("id"), to_email)
        return draft
    except Exception as exc:
        logger.error("gmail_draft_creator: create failed to='%s': %s", to_email, exc)
        raise