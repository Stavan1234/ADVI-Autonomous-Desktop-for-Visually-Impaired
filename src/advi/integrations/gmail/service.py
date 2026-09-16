# from huggingface_hub.inference._generated.types import zero_shot_image_classification
# from _pytest import assertion
# from huggingface_hub.inference._generated.types import zero_shot_image_classification
from __future__ import annotations

import base64
from email.mime.text import MIMEText

from ...core.pipeline_trace import trace, trace_exception

from .auth import get_gmail_credentials

from .models import (
    GmailDraft,
    GmailMessage,
)

class GmailService:
    """Small wrapper around the Gmail API used by ADVI."""

    def close(self) -> None:
        """Close the underlying HTTP transport when the client exposes one."""
        service = getattr(self, "_service", None)
        http = getattr(service, "_http", None)
        closer = getattr(http, "close", None)
        if callable(closer):
            closer()

    def __init__(self) -> None:
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google API client is not installed."
            ) from exc

        credentials = get_gmail_credentials()

        self._service = build(
            "gmail",
            "v1",
            credentials=credentials,
        )

    def search_messages(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        response = (
            self._service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=limit,
            )
            .execute()
        )

        return response.get(
            "messages",
            [],
        )


    def search_parsed_messages(
        self,
        query: str,
        limit: int = 10,
    ) -> list[GmailMessage]:
        rows = self.search_messages(
            query,
            limit=limit,
        )

        messages: list[GmailMessage] = []

        for row in rows:
            message_id = row.get("id")

            if not message_id:
                continue

            messages.append(
                self.get_parsed_message(
                    message_id
                )
            )

        return messages    

    def get_message(
        self,
        message_id: str,
    ) -> dict:
        return (
            self._service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

    def get_parsed_message(
            self,
            message_id: str,
        ) -> GmailMessage:
            raw = self.get_message(
                message_id
            )

            payload = raw.get(
                "payload",
                {},
            )

            headers = {
                header.get("name", "").lower():
                    header.get("value", "")
                for header in payload.get(
                    "headers",
                    [],
                )
            }

            body = self._extract_body(
                payload
            )

            return GmailMessage(
                id=raw.get(
                    "id",
                    message_id,
                ),
                thread_id=raw.get(
                    "threadId",
                    "",
                ),
                sender=headers.get(
                    "from",
                    "",
                ),
                recipients=headers.get(
                    "to",
                    "",
                ),
                subject=headers.get(
                    "subject",
                    "",
                ),
                date=headers.get(
                    "date",
                    "",
                ),
                body=body,
            )

    @staticmethod
    def _extract_body(
        payload: dict,
    ) -> str:
        mime_type = payload.get(
            "mimeType",
            "",
        )

        body_data = (
            payload.get("body", {})
            .get("data")
        )

        # Prefer plain text.
        if (
            body_data
            and mime_type.startswith(
                "text/plain"
            )
        ):
            return GmailService._decode_body(
                body_data
            )

        # Search nested parts for plain text
        # before considering HTML.
        for part in payload.get(
            "parts",
            [],
        ):
            if (
                part.get("mimeType", "")
                .startswith("text/plain")
            ):
                part_data = (
                    part.get("body", {})
                    .get("data")
                )

                if part_data:
                    return (
                        GmailService._decode_body(
                            part_data
                        )
                    )

        # Recursively search deeper multipart
        # structures for plain text.
        for part in payload.get(
            "parts",
            [],
        ):
            result = GmailService._extract_body(
                part
            )

            if result:
                return result

        # Only fall back to HTML if no plain text
        # was found anywhere.
        if (
            body_data
            and mime_type.startswith(
                "text/html"
            )
        ):
            return GmailService._decode_body(
                body_data
            )

        return ""

    @staticmethod
    def _decode_body(
        data: str,
    ) -> str:
        import base64

        decoded = base64.urlsafe_b64decode(
            data + "=" * (
                -len(data) % 4
            )
        )

        return decoded.decode(
            "utf-8",
            errors="replace",
        )    

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> GmailDraft:
        trace(
            "gmail.create_draft.request",
            source_component="GmailService",
            to=to,
            subject=subject,
            body=body,
        )

        message = MIMEText(
            body,
            _subtype="plain",
            _charset="utf-8",
        )

        message["To"] = to
        message["Subject"] = subject

        encoded = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode(
            "ascii"
        )

        try:
            response = (
                self._service.users()
                .drafts()
                .create(
                    userId="me",
                    body={
                        "message": {
                            "raw": encoded,
                        }
                    },
                )
                .execute()
            )
        except Exception as exc:
            trace_exception(
                "gmail.create_draft.error",
                exc,
                to=to,
                subject=subject,
            )
            raise

        draft = GmailDraft(
            draft_id=response.get(
                "id",
                "",
            ),
            recipient=to,
            subject=subject,
            body=body,
        )

        trace(
            "gmail.create_draft.response",
            success=True,
            draft_id=draft.draft_id,
            recipient=draft.recipient,
            subject=draft.subject,
            message_id=response.get("message", {}).get("id"),
            thread_id=response.get("message", {}).get("threadId"),
        )

        return draft


    def get_draft(
        self,
        draft_id: str,
    ) -> GmailDraft:
        trace(
            "gmail.get_draft.request",
            source_component="GmailService",
            draft_id=draft_id,
        )

        try:
            response = (
                self._service.users()
                .drafts()
                .get(
                    userId="me",
                    id=draft_id,
                    format="full",
                )
                .execute()
            )
        except Exception as exc:
            trace_exception(
                "gmail.get_draft.error",
                exc,
                draft_id=draft_id,
            )
            raise

        message = response.get(
            "message",
            {},
        )

        payload = message.get(
            "payload",
            {},
        )

        headers = {
            header.get("name", "").lower():
            header.get("value", "")
            for header in payload.get(
                "headers",
                [],
            )
        }

        draft = GmailDraft(
            draft_id=response.get(
                "id",
                draft_id,
            ),
            recipient=headers.get(
                "to",
                "",
            ),
            subject=headers.get(
                "subject",
                "",
            ),
            body=self._extract_body(
                payload
            ),
        )

        trace(
            "gmail.get_draft.response",
            success=True,
            draft_id=draft.draft_id,
            recipient=draft.recipient,
            subject=draft.subject,
            body_length=len(draft.body),
        )

        return draft  

    def update_draft(
        self,
        draft_id: str,
        to: str,
        subject: str,
        body: str,
    ) -> GmailDraft:
        trace(
            "gmail.update_draft.request",
            source_component="GmailService",
            draft_id=draft_id,
            to=to,
            subject=subject,
            body=body,
        )

        message = MIMEText(
            body,
            _subtype="plain",
            _charset="utf-8",
        )

        message["To"] = to
        message["Subject"] = subject

        encoded = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode("ascii")

        try:
            response = (
                self._service.users()
                .drafts()
                .update(
                    userId="me",
                    id=draft_id,
                    body={
                        "message": {
                            "raw": encoded,
                        }
                    },
                )
                .execute()
            )
        except Exception as exc:
            trace_exception(
                "gmail.update_draft.error",
                exc,
                draft_id=draft_id,
            )
            raise

        draft = GmailDraft(
            draft_id=response.get(
                "id",
                draft_id,
            ),
            recipient=to,
            subject=subject,
            body=body,
        )

        trace(
            "gmail.update_draft.response",
            success=True,
            draft_id=draft.draft_id,
            recipient=draft.recipient,
            subject=draft.subject,
        )

        return draft    

    def send_draft(
        self,
        draft_id: str,
    ) -> dict:
        trace(
            "gmail.send_draft.request",
            source_component="GmailService",
            draft_id=draft_id,
        )

        try:
            response = (
                self._service.users()
                .drafts()
                .send(
                    userId="me",
                    body={
                        "id": draft_id,
                    },
                )
                .execute()
            )
        except Exception as exc:
            trace_exception(
                "gmail.send_draft.error",
                exc,
                draft_id=draft_id,
            )
            raise

        trace(
            "gmail.send_draft.response",
            success=True,
            draft_id=draft_id,
            message_id=response.get("id"),
            thread_id=response.get("threadId"),
            label_ids=response.get("labelIds"),
        )

        return response