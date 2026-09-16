from __future__ import annotations

import logging
from typing import Any

from advi.core.action_plan import Action, ExecutionResult
from advi.integrations.gmail import GmailService

logger = logging.getLogger(__name__)


class GmailCapability:
    """
    Gmail Integration Capability.
    Provides email drafting, reading, updating, and sending via GmailService.
    """

    SUPPORTED_ACTIONS = {
        "email_draft_create",
        "email_draft_read",
        "email_draft_update",
        "email_send",
        "email_read",
    }

    def __init__(self, service: GmailService | None = None) -> None:
        self.service = service

    def is_available(self) -> bool:
        return self.service is not None

    def execute(self, action: Action) -> ExecutionResult:
        if not self.service:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Gmail service is not configured or authenticated.",
            )

        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Unsupported Gmail action: {action.action}",
            )

        try:
            return handler(action)
        except Exception as exc:
            logger.exception("Gmail action failed: %s", action.action)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=str(exc),
            )

    def _execute_email_draft_create(self, action: Action) -> ExecutionResult:
        to = action.parameters.get("to") or action.parameters.get("recipient", "")
        subject = action.parameters.get("subject", "")
        body = action.parameters.get("body") or action.parameters.get("content", "")

        draft = self.service.create_draft(to=to, subject=subject, body=body)
        # GmailDraft is a dataclass with .draft_id, .recipient, .subject, .body
        draft_id = draft.draft_id if hasattr(draft, "draft_id") else (draft.get("id", "") if isinstance(draft, dict) else "")
        return ExecutionResult(
            action=action.action,
            success=True,
            data={"draft_id": draft_id, "to": to, "subject": subject},
            human_readable=f"Created email draft to '{to}' with subject '{subject}'.",
            verified=bool(draft_id),
            verification_details={"draft_id": draft_id},
            metadata={"draft_id": draft_id, "to": to, "subject": subject},
        )

    def _execute_email_draft_read(self, action: Action) -> ExecutionResult:
        draft_id = action.parameters.get("draft_id") or action.target or ""
        draft = self.service.get_draft(draft_id) if hasattr(self.service, "get_draft") else None
        if draft:
            return ExecutionResult(
                action=action.action,
                success=True,
                data=draft,
                human_readable=f"Retrieved email draft {draft_id}.",
            )
        return ExecutionResult(
            action=action.action,
            success=False,
            error=f"Could not retrieve draft {draft_id}.",
        )

    def _execute_email_draft_update(self, action: Action) -> ExecutionResult:
        draft_id = action.parameters.get("draft_id") or action.target or ""
        to = action.parameters.get("to") or action.parameters.get("recipient", "")
        subject = action.parameters.get("subject", "")
        body = action.parameters.get("body") or action.parameters.get("content", "")

        if hasattr(self.service, "update_draft"):
            res = self.service.update_draft(draft_id=draft_id, to=to, subject=subject, body=body)
            updated_id = (
                res.draft_id if hasattr(res, "draft_id")
                else (res.get("id", draft_id) if isinstance(res, dict) else draft_id)
            )
            return ExecutionResult(
                action=action.action,
                success=True,
                data=res,
                human_readable=f"Updated draft {draft_id}.",
                verified=bool(updated_id),
                verification_details={"draft_id": updated_id},
                metadata={"draft_id": updated_id},
            )
        # Fallback: create updated draft
        return self._execute_email_draft_create(action)

    def _execute_email_send(self, action: Action) -> ExecutionResult:
        to = action.parameters.get("to") or action.parameters.get("recipient", "")
        subject = action.parameters.get("subject", "")
        body = action.parameters.get("body") or action.parameters.get("content", "")
        draft_id = action.parameters.get("draft_id")

        if draft_id and hasattr(self.service, "send_draft"):
            res = self.service.send_draft(draft_id)
        else:
            res = self.service.send_email(to=to, subject=subject, body=body)

        msg_id = res.get("id", "") if isinstance(res, dict) else str(res)
        return ExecutionResult(
            action=action.action,
            success=True,
            data=res,
            human_readable=f"Sent email to '{to}' with subject '{subject}'.",
            verified=bool(msg_id),
            verification_details={"message_id": msg_id},
            metadata={"message_id": msg_id, "recipient": to},
        )

    def _execute_email_read(self, action: Action) -> ExecutionResult:
        query = action.parameters.get("query", "is:inbox")
        max_results = int(action.parameters.get("limit", 5))

        messages = self.service.list_messages(query=query, max_results=max_results)
        return ExecutionResult(
            action=action.action,
            success=True,
            data=messages,
            human_readable=f"Retrieved {len(messages)} emails matching query '{query}'.",
            verified=True,
            verification_details={"count": len(messages), "query": query},
            metadata={"count": len(messages), "query": query},
        )
