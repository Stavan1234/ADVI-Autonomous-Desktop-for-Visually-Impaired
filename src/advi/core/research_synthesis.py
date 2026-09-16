from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from advi.providers import LLMProvider
from .structured_output import parse_structured_output
from .research_evidence import ResearchEvidenceStore, StoredResearch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResearchSource:
    index: int
    title: str
    url: str
    domain: str
    content: str
    readable: bool = True
    quality_score: float | None = None
    quality_flags: tuple[str, ...] = ()
    freshness_timestamp: float | None = None


@dataclass(frozen=True)
class ResearchSynthesis:
    answer: str
    source_claims: list[dict[str, Any]] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)


class ResearchSynthesizer:
    """Turn bounded browser evidence into a traceable, uncertainty-aware answer."""

    SCHEMA = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "source_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_index": {"type": "integer"},
                        "claim": {"type": "string"},
                    },
                    "required": ["source_index", "claim"],
                },
            },
            "uncertainty": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer", "source_claims", "uncertainty"],
    }

    def __init__(self, provider: LLMProvider, evidence_store: ResearchEvidenceStore | None = None) -> None:
        self.provider = provider
        self.evidence_store = evidence_store

    def synthesize(self, question: str, evidence: dict[str, Any] | list[dict[str, Any]]) -> ResearchSynthesis:
        sources = self._sources(evidence)
        if not sources:
            return ResearchSynthesis(
                answer="I could not produce a grounded answer because no readable sources were available.",
                uncertainty=["No readable source evidence was available."],
            )

        prompt = self._build_prompt(question, sources)
        try:
            raw = self.provider.structured([{"role": "user", "content": prompt}], self.SCHEMA)
            parsed = parse_structured_output(
                raw.text if hasattr(raw, "text") else str(raw), self.SCHEMA
            )
            result = self._normalize(question, parsed.data, sources)
            return result
        except Exception as exc:
            logger.warning("Research synthesis failed: %s", exc)
            return self._deterministic_fallback(question, sources)

    def _build_prompt(self, question: str, sources: list[ResearchSource]) -> str:
        evidence = "\n\n".join(
            f"SOURCE [{s.index}]\nTitle: {s.title}\nURL: {s.url}\nDomain: {s.domain}\n"
            f"QUALITY_SCORE: {s.quality_score}\nQUALITY_FLAGS: {', '.join(s.quality_flags) or 'none'}\n"
            f"FRESHNESS_TIMESTAMP: {s.freshness_timestamp}\n"
            f"CONTENT:\n{s.content[:6000]}"
            for s in sources
        )
        time_sensitive = self._is_time_sensitive(question)
        return f"""You are ADVI's grounded research synthesizer.

User question:
{question!r}

Use ONLY the supplied source evidence. Do not add outside facts.
Every substantive factual claim in the answer MUST include one or more source markers like [S1] or [S2].
Do not invent source numbers, URLs, quotations, or facts.
When sources disagree, say so explicitly and identify the disagreement by source marker.
When evidence is insufficient, state what is uncertain instead of guessing.
Prefer higher-quality sources and, for time-sensitive questions, fresher sources. Treat stale or freshness-unknown evidence cautiously rather than presenting it as current.
Do not treat conflicting sources as if they agree. Preserve meaningful disagreement in the answer or uncertainty field.
Time-sensitive request: {time_sensitive}
Keep the answer concise but useful.

Return JSON matching the schema with:
- answer: the grounded answer with inline [S#] markers
- source_claims: each supported claim mapped to a real source_index
- uncertainty: unresolved limitations, stale/freshness-unknown evidence, or conflicts

SUPPLIED EVIDENCE:
{evidence}
"""

    def _normalize(self, question: str, data: dict[str, Any], sources: list[ResearchSource]) -> ResearchSynthesis:
        valid = {s.index for s in sources}
        claims: list[dict[str, Any]] = []
        for item in data.get("source_claims") or []:
            try:
                idx = int(item.get("source_index"))
            except (TypeError, ValueError):
                continue
            claim = str(item.get("claim") or "").strip()
            if idx in valid and claim:
                claims.append({"source_index": idx, "claim": claim})
        answer = str(data.get("answer") or "").strip()
        if not answer:
            return self._deterministic_fallback("", sources)
        uncertainty = [str(x) for x in (data.get("uncertainty") or []) if str(x).strip()]
        if self._is_time_sensitive(question):
            unknown = [s.index for s in sources if s.freshness_timestamp is None]
            stale = [s.index for s in sources if "stale" in s.quality_flags]
            if unknown:
                uncertainty.append(f"Freshness is unknown for source(s): {', '.join(f'[S{i}]' for i in unknown)}.")
            if stale:
                uncertainty.append(f"Source(s) may be stale for a time-sensitive question: {', '.join(f'[S{i}]' for i in stale)}.")
        low_quality = [s.index for s in sources if "thin_content" in s.quality_flags]
        if low_quality:
            uncertainty.append(f"Source(s) had thin content: {', '.join(f'[S{i}]' for i in low_quality)}.")
        if not claims:
            uncertainty.append("The synthesis did not produce any valid source-claim mappings.")
        return ResearchSynthesis(
            answer=answer,
            source_claims=claims,
            uncertainty=list(dict.fromkeys(uncertainty)),
        )

    @staticmethod
    def _is_time_sensitive(question: str) -> bool:
        text = str(question or "").lower()
        markers = (
            "today", "latest", "current", "now", "recent", "this week",
            "this month", "as of", "price", "weather", "score", "status",
            "2026", "2025",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _sources(evidence: dict[str, Any] | list[dict[str, Any]]) -> list[ResearchSource]:
        if isinstance(evidence, dict):
            raw_sources = evidence.get("sources") or []
        else:
            raw_sources = evidence
        sources: list[ResearchSource] = []
        for idx, item in enumerate(raw_sources, start=1):
            if not isinstance(item, dict) or not item.get("readable"):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            sources.append(
                ResearchSource(
                    index=idx,
                    title=str(item.get("title") or item.get("text") or f"Source {idx}"),
                    url=str(item.get("url") or item.get("href") or ""),
                    domain=str(item.get("domain") or ""),
                    content=content,
                    quality_score=(float(item.get("quality_score")) if item.get("quality_score") is not None else None),
                    quality_flags=tuple(str(x) for x in (item.get("quality_flags") or [])),
                    freshness_timestamp=(float(item.get("freshness_timestamp")) if item.get("freshness_timestamp") is not None else None),
                )
            )
        return sources

    @staticmethod
    def _deterministic_fallback(question: str, sources: list[ResearchSource]) -> ResearchSynthesis:
        snippets = []
        claims = []
        for source in sources[:3]:
            snippet = " ".join(source.content.split())[:700]
            snippets.append(f"[S{source.index}] {snippet}")
            claims.append({"source_index": source.index, "claim": snippet})
        return ResearchSynthesis(
            answer="I could not produce a model synthesis, so here is the source-grounded evidence:\n\n" + "\n\n".join(snippets),
            source_claims=claims,
            uncertainty=["The evidence is presented as source excerpts rather than a synthesized conclusion."],
        )


__all__ = ["ResearchSource", "ResearchSynthesis", "ResearchSynthesizer"]
