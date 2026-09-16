from advi.core.research_quality import canonicalize_url, rank_and_dedupe_sources, score_source


def test_canonicalize_url_removes_tracking_and_fragment():
    assert canonicalize_url("https://www.example.com/a/?utm_source=x&b=1#section") == "https://example.com/a?b=1"


def test_rank_prefers_substantive_and_fresh_source():
    sources = [
        {"readable": True, "title": "Old", "url": "https://old.example/a", "content": "tiny", "published_at": "2010-01-01"},
        {"readable": True, "title": "Fresh Guide", "url": "https://fresh.example/a", "content": "ADVI architecture " * 80, "published_at": "2026-09-01"},
    ]
    result = rank_and_dedupe_sources(sources, query="ADVI architecture", max_sources=1, now=1789500000)
    assert result[0]["domain"] if "domain" in result[0] else True
    assert "substantive_content" in result[0]["quality_flags"]
    assert "fresh" in result[0]["quality_flags"]


def test_rank_removes_duplicate_content_and_urls():
    sources = [
        {"readable": True, "title": "One", "url": "https://www.example.com/a?utm_campaign=x", "domain": "example.com", "content": "Same evidence " * 50},
        {"readable": True, "title": "One mirror", "url": "https://example.com/a#top", "domain": "example.com", "content": "Same evidence " * 50},
        {"readable": True, "title": "Two", "url": "https://two.example/b", "domain": "two.example", "content": "Different evidence " * 50},
    ]
    result = rank_and_dedupe_sources(sources, query="evidence", max_sources=3)
    assert len(result) == 2
    assert len({x["canonical_url"] for x in result}) == 2


def test_thin_source_is_penalized():
    quality = score_source({"readable": True, "title": "Thin", "url": "https://x.example", "content": "tiny"})
    assert "thin_content" in quality.quality_flags
    assert quality.score < 0
