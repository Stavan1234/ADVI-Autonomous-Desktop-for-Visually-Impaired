from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GmailMessage:
    id: str
    thread_id: str

    sender: str = ""
    recipients: str = ""
    subject: str = ""
    date: str = ""
    body: str = ""

@dataclass(frozen=True)
class GmailDraft:
    draft_id: str
    recipient: str
    subject: str
    body: str