import base64
from bs4 import BeautifulSoup


def parse_email(raw_message):

    headers = raw_message["payload"]["headers"]

    header_map = {
        h["name"]: h["value"]
        for h in headers
    }

    subject = header_map.get("Subject", "(No Subject)")
    sender = header_map.get("From", "(Unknown Sender)")
    date = header_map.get("Date", "(Unknown Date)")

    body = extract_body(raw_message["payload"])

    return {
        "id": raw_message["id"],
        "subject": subject,
        "sender": sender,
        "date": date,
        "body": body,
        "snippet": raw_message.get("snippet", "")
    }


def extract_body(payload):

    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return decode_base64(data)

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        html = decode_base64(data)
        return strip_html(html)

    if "multipart" in mime_type:

        parts = payload.get("parts", [])

        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                return decode_base64(data)

        for part in parts:
            result = extract_body(part)

            if result:
                return result

    return "(No readable body found)"


def decode_base64(data):

    if not data:
        return ""

    decoded_bytes = base64.urlsafe_b64decode(data + "==")

    return decoded_bytes.decode(
        "utf-8",
        errors="replace"
    )


def strip_html(html_content):

    soup = BeautifulSoup(
        html_content,
        "html.parser"
    )

    return soup.get_text(
        separator="\n"
    ).strip()