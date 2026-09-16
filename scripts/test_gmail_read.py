import os
import pytest
from advi.integrations.gmail import GmailService

CREDENTIALS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "credentials", "gmail_credentials.json"
)

@pytest.mark.skipif(
    not os.path.exists(CREDENTIALS_PATH),
    reason="Gmail credentials not configured, skipping Gmail integration test.",
)
def test_gmail_read():
    """Test basic Gmail read functionality."""
    gmail = GmailService()

    messages = gmail.search_messages("in:anywhere", limit=1)

    if not messages:
        pytest.fail("No Gmail messages found.")

    message = gmail.get_parsed_message(messages[0]["id"])

    # Print basic fields for debugging (optional)
    print()
    print("ID       :", message.id)
    print("From     :", message.sender)
    print("To       :", message.recipients)
    print("Subject  :", message.subject)
    print("Date     :", message.date)
    print()
    print("BODY")
    print("-----")
    print(message.body[:3000])
