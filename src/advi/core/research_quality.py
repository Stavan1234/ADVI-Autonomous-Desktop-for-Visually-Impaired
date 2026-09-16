from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src",
}


@dataclass(frozen=True)
class SourceQuality:
    score: float
    canonical_url: str
    domain: str
    freshness_timestamp: float | None = None
    content_fingerprint: str = ""
    quality_flags: tuple[str, ...] = ()


def canonicalize_url(url: str) -> str:
    """Normalize URLs for research deduplication without changing their destination."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS]
        path = re.sub(r"/{2,}", "/", parts.path or "/")
        if path != "/":
            path = path.rstrip("/")
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query), ""))
    except Exception:
        return raw


def content_fingerprint(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(t) >= 3}


def token_similarity(left: str, right: str) -> float:
    a, b = _token_set(left), _token_set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def parse_freshness(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    candidates = [text, text.replace("Z", "+00:00")]
    for item in candidates:
        try:
            parsed = datetime.fromisoformat(item)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            pass
    for pattern in (r"\b\d{4}-\d{2}-\d{2}\b", r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}\b"):
        match = re.search(pattern, text, re.I)
        if match:
            for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
                try:
                    return datetime.strptime(match.group(0), fmt).replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    continue
    return None


def score_source(source: dict[str, Any], query: str = "", now: float | None = None) -> SourceQuality:
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    title = str(source.get("title") or source.get("text") or "")
    url = str(source.get("url") or source.get("href") or "")
    domain = str(source.get("domain") or urlsplit(url).netloc).lower()
    content = str(source.get("content") or "")
    score = float(source.get("score") or 0)
    flags: list[str] = []
    q_tokens = _token_set(query)
    matched = len(q_tokens & _token_set(title + " " + url + " " + content[:2000]))
    score += min(6.0, matched * 0.75)
    length = len(content.strip())
    if length >= 1000:
        score += 3
        flags.append("substantive_content")
    elif length >= 300:
        score += 1
        flags.append("adequate_content")
    else:
        flags.append("thin_content")
        score -= 3
    if title.strip():
        flags.append("has_title")
        score += 0.5
    freshness = parse_freshness(source.get("published_at") or source.get("date") or source.get("modified_at"))
    if freshness is not None:
        age_days = max(0.0, (now - freshness) / 86400)
        if age_days <= 30:
            score += 2.5
            flags.append("fresh")
        elif age_days <= 365:
            score += 1.0
            flags.append("recent")
        elif age_days > 3650:
            flags.append("stale")
    else:
        flags.append("freshness_unknown")
    return SourceQuality(
        score=score,
        canonical_url=canonicalize_url(url),
        domain=domain.split(":", 1)[0],
        freshness_timestamp=freshness,
        content_fingerprint=content_fingerprint(content),
        quality_flags=tuple(flags),
    )


def rank_and_dedupe_sources(
    sources: Iterable[dict[str, Any]],
    query: str = "",
    max_sources: int = 5,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Rank usable evidence, remove URL/content duplicates, and prefer domain diversity."""
    enriched: list[tuple[dict[str, Any], SourceQuality]] = []
    for item in sources:
        if not isinstance(item, dict) or not item.get("readable"):
            continue
        quality = score_source(item, query=query, now=now)
        if quality.score < -1:
            continue
        enriched.append((dict(item), quality))

    enriched.sort(key=lambda pair: pair[1].score, reverse=True)
    chosen: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_fingerprints: list[str] = []
    seen_domains: set[str] = set()

    for item, quality in enriched:
        if quality.canonical_url and quality.canonical_url in seen_urls:
            continue
        if quality.content_fingerprint and any(quality.content_fingerprint == fp for fp in seen_fingerprints):
            continue
        # Near-duplicate pages often differ only by navigation/boilerplate. Keep the stronger one.
        normalized_content = str(item.get("content") or "")
        if any(token_similarity(normalized_content, str(existing.get("content") or "")) >= 0.92 for existing in chosen):
            continue
        # Prefer domain diversity, but allow a second source from a strong domain if needed.
        if quality.domain and quality.domain in seen_domains and len(chosen) < min(2, max_sources):
            continue
        item.update({
            "canonical_url": quality.canonical_url,
            "quality_score": round(quality.score, 3),
            "quality_flags": list(quality.quality_flags),
            "freshness_timestamp": quality.freshness_timestamp,
        })
        chosen.append(item)
        if quality.canonical_url:
            seen_urls.add(quality.canonical_url)
        if quality.content_fingerprint:
            seen_fingerprints.append(quality.content_fingerprint)
        if quality.domain:
            seen_domains.add(quality.domain)
        if len(chosen) >= max_sources:
            break

    return chosen


__all__ = [
    "SourceQuality",
    "canonicalize_url",
    "content_fingerprint",
    "parse_freshness",
    "rank_and_dedupe_sources",
    "score_source",
    "token_similarity",
]
