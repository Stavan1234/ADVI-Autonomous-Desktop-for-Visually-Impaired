from advi.capabilities.browser.executor import BrowserCapability
from advi.capabilities.desktop.context import DesktopContext
from advi.core.action_plan import Action
from advi.core.action_contracts import validate_and_normalize_action
from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus


class MultiResearchCDP:
    def __init__(self):
        self.url = "about:blank"
        self.title = ""
        self.current_source = None

    def list_tabs(self):
        return [{"id": "tab-1", "type": "page", "url": self.url, "title": self.title}]

    def get_tab_info(self, tab_id):
        return {"id": tab_id, "type": "page", "url": self.url, "title": self.title}

    def navigate_tab(self, tab_id, url):
        self.url = url
        if "google.com/search" in url:
            self.title = "Google"
            self.current_source = None
        elif "one.example" in url:
            self.title = "Source One"
            self.current_source = "one"
        elif "two.example" in url:
            self.title = "Source Two"
            self.current_source = "two"
        else:
            self.title = "Other"
            self.current_source = "other"
        return True

    def evaluate_script(self, tab_id, script):
        if "querySelectorAll('a[href]')" in script:
            return {"value": {"candidates": [
                {"text": "Source One", "href": "https://one.example/article", "score": 10},
                {"text": "Source Two", "href": "https://two.example/article", "score": 9},
                {"text": "Another One", "href": "https://one.example/other", "score": 8},
            ]}}
        if "document.body ? document.body.innerText" in script:
            content = {
                "one": "Evidence from source one.",
                "two": "Evidence from source two.",
                "other": "Other evidence.",
            }.get(self.current_source, "")
            return {"value": content}
        return {"value": True}


def make_cap():
    cap = BrowserCapability(context=DesktopContext())
    cap.context.set_target_tab("tab-1", url="about:blank", title="")
    cap.cdp = MultiResearchCDP()
    return cap


def test_multi_source_research_collects_distinct_sources(monkeypatch):
    cap = make_cap()
    monkeypatch.setattr(cap, "_ensure_chrome_running", lambda: True)
    result = cap.execute(Action(action="research_web_multi", parameters={"query": "ADVI architecture", "max_sources": 2}))

    assert result.success
    assert result.metadata["readable_source_count"] == 2
    assert len(result.metadata["sources"]) == 2
    assert "Evidence from source one." in result.data
    assert "Evidence from source two." in result.data
    assert len({s["domain"] for s in result.metadata["sources"]}) == 2


def test_multi_source_research_is_bounded_by_source_count(monkeypatch):
    cap = make_cap()
    monkeypatch.setattr(cap, "_ensure_chrome_running", lambda: True)
    result = cap.execute(Action(action="research_web_multi", parameters={"query": "ADVI", "max_sources": 1, "pages": 2}))

    assert result.success
    assert result.metadata["source_count"] == 1
    assert len(result.metadata["search_pages"]) == 1


def test_multi_source_research_fails_when_no_readable_source(monkeypatch):
    cap = make_cap()
    monkeypatch.setattr(cap, "_ensure_chrome_running", lambda: True)
    original = cap.cdp.evaluate_script
    def unreadable(tab_id, script):
        if "document.body ? document.body.innerText" in script:
            return {"value": ""}
        return original(tab_id, script)
    cap.cdp.evaluate_script = unreadable

    result = cap.execute(Action(action="research_web_multi", parameters={"query": "ADVI"}))
    assert not result.success
    assert result.metadata["readable_source_count"] == 0


def test_multi_source_contract_normalizes_aliases():
    action = Action(action="research_web_multi", parameters={
        "query": "python", "site": "docs", "max_sources": "3", "pages": "2", "limit": "1200"
    })
    normalized, errors = validate_and_normalize_action(action)
    assert not errors
    assert normalized is not None
    assert normalized.parameters["target"] == "docs"
    assert normalized.parameters["max_sources"] == "3"
    assert normalized.parameters["pages"] == "2"
    assert normalized.parameters["max_chars"] == "1200"


def test_registry_exposes_multi_source_research():
    registry = CapabilityRegistry()
    registry.register(Capability(
        name="browser_control",
        description="Browser",
        supported_actions={"research_web_multi"},
        status=CapabilityStatus.AVAILABLE,
    ))
    spec = registry.get_action_spec("research_web_multi")
    assert spec is not None
    assert spec.verification == "multi_source_page_content"
    assert "max_sources" in spec.parameters
