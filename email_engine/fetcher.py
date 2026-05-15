from auth.gmail_auth import get_gmail_service


def fetch_emails(max_results=5, query="is:unread"):
    service = get_gmail_service()

    result = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        q=query
    ).execute()

    messages = result.get("messages", [])

    if not messages:
        print("No unread emails found.")
        return []

    full_messages = []

    for msg in messages:
        full_msg = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"
        ).execute()

        full_messages.append(full_msg)

    return full_messages


if __name__ == "__main__":
    emails = fetch_emails()

    for email in emails:
        print(email["id"])