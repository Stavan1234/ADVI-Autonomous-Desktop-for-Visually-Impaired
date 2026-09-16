def test_gmail_message_model():
    from advi.integrations.gmail import GmailMessage

    message = GmailMessage(
        id="123",
        thread_id="456",
        sender="David <david@example.com>",
        recipients="stavan@example.com",
        subject="Project update",
        date="Mon, 24 Aug 2026 10:00:00 +0000",
        body="The project is ready.",
    )

    assert message.id == "123"
    assert message.thread_id == "456"
    assert message.sender == (
        "David <david@example.com>"
    )
    assert message.subject == (
        "Project update"
    )
    assert message.body == (
        "The project is ready."
    )


def test_gmail_service_extracts_plain_text_body():
    from advi.integrations.gmail.service import (
        GmailService,
    )

    payload = {
        "mimeType": "text/plain",
        "body": {
            "data": (
                "VGhlIHByb2plY3QgaXMgcmVhZHku"
            )
        },
    }

    body = GmailService._extract_body(
        payload
    )

    assert body == (
        "The project is ready."
    )


def test_gmail_service_extracts_nested_plain_text_body():
    from advi.integrations.gmail.service import (
        GmailService,
    )

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {
                    "data": (
                        "PGI+SGVsbG88L2I+"
                    )
                },
            },
            {
                "mimeType": "text/plain",
                "body": {
                    "data": (
                        "SGVsbG8="
                    )
                },
            },
        ],
    }

    body = GmailService._extract_body(
        payload
    )

    assert body == "Hello"

def test_search_parsed_messages():
    from advi.integrations.gmail.service import GmailService

    service = GmailService.__new__(
        GmailService
    )

    service.search_messages = lambda query, limit=10: [
        {"id": "1"},
        {"id": "2"},
    ]

    service.get_parsed_message = (
        lambda message_id: {
            "1": "message-one",
            "2": "message-two",
        }[message_id]
    )

    result = service.search_parsed_messages(
        "from:david@example.com",
        limit=2,
    )

    assert result == [
        "message-one",
        "message-two",
    ]

def test_gmail_draft_operations_build_request():
    from advi.integrations.gmail.service import GmailService

    class FakeDrafts:
        def create(
            self,
            userId,
            body,
        ):
            assert userId == "me"
            assert "message" in body
            assert "raw" in body["message"]

            class Request:
                def execute(self):
                    return {
                        "id": "draft-1"
                    }

            return Request()

    class FakeUsers:
        def drafts(self):
            return FakeDrafts()

    class FakeService:
        def users(self):
            return FakeUsers()

    service = GmailService.__new__(
        GmailService
    )

    service._service = FakeService()

    result = service.create_draft(
        to="david@example.com",
        subject="Project update",
        body="The project is ready.",
    )

    assert result.draft_id == "draft-1"
    assert result.recipient == "david@example.com"
    assert result.subject == "Project update"
    assert result.body == "The project is ready."  


def test_gmail_draft_model():
    from advi.integrations.gmail import GmailDraft

    draft = GmailDraft(
        draft_id="draft-1",
        recipient="david@example.com",
        subject="Project update",
        body="The project is ready.",
    )

    assert draft.draft_id == "draft-1"
    assert draft.recipient == "david@example.com"
    assert draft.subject == "Project update"
    assert draft.body == "The project is ready."     


def test_gmail_draft_model_fields_are_stable():
    from advi.integrations.gmail import GmailDraft

    draft = GmailDraft(
        draft_id="draft-1",
        recipient="david@example.com",
        subject="Project update",
        body="The project is ready.",
    )

    assert draft.draft_id == "draft-1"
    assert draft.recipient == "david@example.com"
    assert draft.subject == "Project update"
    assert draft.body == "The project is ready."

def test_gmail_get_draft_returns_normalized_draft():
    from advi.integrations.gmail.service import GmailService

    class FakeRequest:
        def execute(self):
            return {
                "id": "draft-1",
                "message": {
                    "id": "msg-1",
                    "threadId": "thread-1",
                    "payload": {
                        "headers": [
                            {
                                "name": "To",
                                "value": "david@example.com",
                            },
                            {
                                "name": "Subject",
                                "value": "Project update",
                            },
                        ],
                        "mimeType": "text/plain",
                        "body": {
                            "data": (
                                "VGhlIHByb2plY3QgaXMgcmVhZHku"
                            )
                        },
                    },
                },
            }

    class FakeDrafts:
        def get(
            self,
            userId,
            id,
            format,
        ):
            return FakeRequest()

    class FakeUsers:
        def drafts(self):
            return FakeDrafts()

    class FakeService:
        def users(self):
            return FakeUsers()

    service = GmailService.__new__(
        GmailService
    )

    service._service = FakeService()

    draft = service.get_draft(
        "draft-1"
    )

    assert draft.draft_id == "draft-1"
    assert draft.recipient == "david@example.com"
    assert draft.subject == "Project update"
    assert draft.body == "The project is ready."  

def test_gmail_update_draft_returns_normalized_draft():
    from advi.integrations.gmail.service import GmailService

    class FakeRequest:
        def execute(self):
            return {
                "id": "draft-1"
            }

    class FakeDrafts:
        def update(
            self,
            userId,
            id,
            body,
        ):
            assert userId == "me"
            assert id == "draft-1"
            assert "message" in body
            assert "raw" in body["message"]

            return FakeRequest()

    class FakeUsers:
        def drafts(self):
            return FakeDrafts()

    class FakeService:
        def users(self):
            return FakeUsers()

    service = GmailService.__new__(
        GmailService
    )

    service._service = FakeService()

    draft = service.update_draft(
        draft_id="draft-1",
        to="daniel@example.com",
        subject="Updated project update",
        body="The project is now ready.",
    )

    assert draft.draft_id == "draft-1"
    assert draft.recipient == "daniel@example.com"
    assert draft.subject == (
        "Updated project update"
    )
    assert draft.body == (
        "The project is now ready."
    )
    
        
