from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResearchConflict:
    source_indices: tuple[int, ...]
    topic: str
    excerpts: tuple[str, ...]


@dataclass(frozen=True)
class StoredResearch:
    research_id: str
    question: str
    created_at: float
    sources: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    source_claims: list[dict[str, Any]] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    conflicts: list[ResearchConflict] = field(default_factory=list)


class ResearchEvidenceStore:
    """Durable, bounded store for source evidence used by research follow-ups."""

    def __init__(self, database_path: Path, max_content_chars: int = 10000) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_content_chars = max(1000, int(max_content_chars))
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_sessions (
                    research_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_created "
                "ON research_sessions(created_at DESC)"
            )

    @staticmethod
    def _clean_source(source: dict[str, Any], index: int, max_chars: int) -> dict[str, Any]:
        return {
            "index": index,
            "title": str(source.get("title") or source.get("text") or f"Source {index}"),
            "url": str(source.get("url") or source.get("href") or ""),
            "domain": str(source.get("domain") or ""),
            "readable": bool(source.get("readable")),
            "content": str(source.get("content") or "")[:max_chars],
        }

    def save(
        self,
        research_id: str,
        question: str,
        evidence: dict[str, Any],
        answer: str = "",
        source_claims: list[dict[str, Any]] | None = None,
        uncertainty: list[str] | None = None,
    ) -> StoredResearch:
        raw_sources = evidence.get("sources") if isinstance(evidence, dict) else []
        sources = [
            self._clean_source(item, idx, self.max_content_chars)
            for idx, item in enumerate(raw_sources or [], start=1)
            if isinstance(item, dict)
        ]
        conflicts = self.detect_conflicts(sources)
        payload = {
            "research_id": research_id,
            "question": question,
            "sources": sources,
            "answer": answer,
            "source_claims": source_claims or [],
            "uncertainty": uncertainty or [],
            "conflicts": [c.__dict__ for c in conflicts],
        }
        created_at = time.time()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO research_sessions(research_id, question, payload, created_at) VALUES (?, ?, ?, ?)",
                (research_id, question, json.dumps(payload, ensure_ascii=False), created_at),
            )
        return self._from_payload(payload, created_at)

    def get(self, research_id: str) -> StoredResearch | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload, created_at FROM research_sessions WHERE research_id = ?",
                (research_id,),
            ).fetchone()
        if not row:
            return None
        return self._from_payload(json.loads(row["payload"]), float(row["created_at"]))

    def latest(self, limit: int = 3) -> list[StoredResearch]:
        limit = max(1, int(limit))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload, created_at FROM research_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._from_payload(json.loads(row["payload"]), float(row["created_at"])) for row in rows]

    def find_by_question(self, query: str, limit: int = 3) -> list[StoredResearch]:
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 3]
        if not terms:
            return self.latest(limit)
        pattern = "%" + "%".join(terms[:5]) + "%"
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload, created_at FROM research_sessions WHERE lower(question) LIKE ? ORDER BY created_at DESC LIMIT ?",
                (pattern, max(1, int(limit))),
            ).fetchall()
        return [self._from_payload(json.loads(row["payload"]), float(row["created_at"])) for row in rows]

    @staticmethod
    def detect_conflicts(sources: list[dict[str, Any]]) -> list[ResearchConflict]:
        """Detect simple explicit polarity/value conflicts without requiring another LLM."""
        candidates: list[tuple[int, str, bool, set[str]]] = []
        for source in sources:
            text = " ".join(str(source.get("content") or "").split())
            lower = text.lower()
            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                tokens = set(re.findall(r"[a-z0-9]+", sentence.lower()))
                numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", sentence))
                polarity_negative = bool(re.search(r"\b(?:not|no|never|cannot|can't|false|without)\b", sentence.lower()))
                if numbers or polarity_negative or re.search(r"\b(?:yes|true|supports|uses|has|is)\b", lower):
                    candidates.append((int(source.get("index") or 0), sentence.strip(), polarity_negative, tokens | numbers))

        conflicts: list[ResearchConflict] = []
        seen: set[tuple[int, int, str]] = set()
        for i, left in enumerate(candidates):
            for right in candidates[i + 1 :]:
                if left[0] == right[0]:
                    continue
                overlap = left[3] & right[3]
                topic_tokens = {t for t in overlap if len(t) >= 4 and not t.isdigit()}
                same_value = bool(left[3] & right[3] & {t for t in left[3] if t.replace('.', '', 1).isdigit()})
                opposite_polarity = left[2] != right[2]
                if len(topic_tokens) >= 1 and (opposite_polarity or same_value is False and len(overlap) >= 3):
                    topic = " ".join(sorted(topic_tokens)[:4])
                    key = (min(left[0], right[0]), max(left[0], right[0]), topic)
                    if key not in seen:
                        seen.add(key)
                        conflicts.append(
                            ResearchConflict(
                                source_indices=(left[0], right[0]),
                                topic=topic,
                                excerpts=(left[1], right[1]),
                            )
                        )
        return conflicts[:10]

    @staticmethod
    def _from_payload(payload: dict[str, Any], created_at: float) -> StoredResearch:
        conflicts = [
            ResearchConflict(
                source_indices=tuple(item.get("source_indices") or ()),
                topic=str(item.get("topic") or ""),
                excerpts=tuple(item.get("excerpts") or ()),
            )
            for item in payload.get("conflicts") or []
        ]
        return StoredResearch(
            research_id=str(payload.get("research_id") or ""),
            question=str(payload.get("question") or ""),
            created_at=created_at,
            sources=list(payload.get("sources") or []),
            answer=str(payload.get("answer") or ""),
            source_claims=list(payload.get("source_claims") or []),
            uncertainty=list(payload.get("uncertainty") or []),
            conflicts=conflicts,
        )


__all__ = ["ResearchConflict", "ResearchEvidenceStore", "StoredResearch"]
