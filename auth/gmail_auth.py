# auth/gmail_auth.py

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ── SCOPES ──────────────────────────────────────────────────────────────
# These MUST match exactly what you declared in Google Cloud Console.
# If they don't match, Google will reject the auth request.
# We define them once here so every part of the app references
# this single source of truth — never hardcode scopes elsewhere.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# ── FILE PATHS ───────────────────────────────────────────────────────────
# We define paths relative to this file's location.
# Never hardcode absolute paths like /home/yourname/project/...
# That breaks on every other machine.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_gmail_service():
    """
    Authenticates with Gmail API using OAuth 2.0.
    
    Returns a Gmail API service object ready to make API calls.
    
    On first run: opens browser for user authorization.
    On subsequent runs: loads saved token, refreshes if expired.
    """
    creds = None

    # ── STEP 1: Try to load existing token ──────────────────────────────
    # If token.json exists, we've authenticated before.
    # Load those credentials instead of making user log in again.
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # ── STEP 2: Handle missing or expired credentials ────────────────────
    # creds is None  → first run, no token file yet
    # not creds.valid → token exists but is expired or revoked
    if not creds or not creds.valid:
        
        if creds and creds.expired and creds.refresh_token:
            # Token expired but we have a refresh token → silent refresh.
            # No browser needed. This is what happens on run #2, #3, etc.
            creds.refresh(Request())
        else:
            # No token at all → full OAuth flow → opens browser.
            # InstalledAppFlow handles the local server that catches
            # Google's redirect and extracts the authorization code.
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
            # port=0 means: pick any available port automatically.
            # This avoids conflicts if something else uses port 8080.

        # ── STEP 3: Save the new/refreshed token ────────────────────────
        # Always persist credentials after any change so next run
        # doesn't need to re-authenticate.
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())

    # ── STEP 4: Build and return the Gmail API service object ────────────
    # 'build' creates a client object for a specific Google API.
    # "gmail" = which API, "v1" = which version.
    # This service object is what you'll use for every Gmail operation.
    service = build("gmail", "v1", credentials=creds)
    return service


# ── QUICK CONNECTION TEST ─────────────────────────────────────────────────
# This block only runs when you execute this file directly:
#   python auth/gmail_auth.py
# It does NOT run when this module is imported elsewhere.
# This is a standard Python pattern for testable modules.
if __name__ == "__main__":
    print("Authenticating with Gmail...")
    service = get_gmail_service()
    
    # Call the Gmail API to get your own profile — simplest possible test.
    # If this works, authentication is fully functional.
    profile = service.users().getProfile(userId="me").execute()
    
    print(f"✅ Connected successfully!")
    print(f"📧 Email: {profile['emailAddress']}")
    print(f"📨 Total messages: {profile['messagesTotal']}")