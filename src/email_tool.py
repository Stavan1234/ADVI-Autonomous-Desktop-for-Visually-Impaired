# src/email_tool.py
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64, os
from email.mime.text import MIMEText

SCOPES = ["https://www.googleapis.com/auth/gmail.send",
          "https://www.googleapis.com/auth/gmail.readonly"]

# Resolve auth files relative to the project (not the process cwd) and keep
# them under data/. Fall back to the old project-root locations so existing
# setups keep working until the files are moved.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
TOKEN_PATH = os.path.join(_DATA_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(_DATA_DIR, "credentials.json")


def _first_existing(*paths: str) -> str:
    """Return the first path that exists, or the first candidate otherwise."""
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]


def get_gmail_service():
    """Return an authorized Gmail service, opening the OAuth browser only once.

    Persistence pattern:
      1. Load data/token.json (or a legacy root token.json) if present.
      2. If it's expired but has a refresh token, refresh silently — no browser.
      3. Otherwise run the local-server flow exactly once.
      4. Always save the fresh/refreshed token to data/token.json so future
         runs are fully silent.
    """
    creds = None
    token_path = _first_existing(TOKEN_PATH, os.path.join(_PROJECT_ROOT, "token.json"))
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Silent refresh — no browser popup.
            creds.refresh(Request())
        else:
            # First-time only: open the browser.
            creds_path = _first_existing(
                CREDENTIALS_PATH, os.path.join(_PROJECT_ROOT, "credentials.json")
            )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the token so the browser never opens again.
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_email(recipient, subject, body) -> dict:
    """Defensive by design: a crash here previously took down the entire assistant
    process (see the 'dict has no attribute encode' traceback) because a malformed
    recipient value reached MIMEText unguarded. Every step below can now only ever
    return a result dict, never raise."""
    if not isinstance(recipient, str) or not recipient.strip():
        return {"success": False, "error": f"Recipient must be a plain email string, got: {recipient!r}"}
    if not isinstance(subject, str):
        subject = str(subject)
    if not isinstance(body, str):
        body = str(body)

    try:
        service = get_gmail_service()
        message = MIMEText(body)
        message["to"] = recipient
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"success": True, "message_id": result["id"]}
    except HttpError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Anything unexpected (bad encoding, malformed header, auth hiccup) is
        # reported back, never allowed to propagate and kill the process.
        return {"success": False, "error": f"Unexpected error building/sending email: {e}"}


def verify_sent(message_id: str) -> bool:
    """The actual 'did it really send' check — query Gmail directly, don't assume."""
    service = get_gmail_service()
    try:
        msg = service.users().messages().get(userId="me", id=message_id).execute()
        return "SENT" in msg.get("labelIds", [])
    except HttpError:
        return False