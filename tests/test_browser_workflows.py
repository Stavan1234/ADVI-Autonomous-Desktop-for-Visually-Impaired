from advi.capabilities.browser.executor import BrowserCapability
from advi.capabilities.desktop.context import DesktopContext
from advi.core.action_plan import Action


class WorkflowCDP:
    def __init__(self):
        self.url = "https://example.com"
        self.title = "Example"
        self.calls = []

    def list_tabs(self):
        return [{"id": "tab-1", "type": "page", "url": self.url, "title": self.title}]

    def get_tab_info(self, tab_id):
        assert tab_id == "tab-1"
        return {"id": tab_id, "type": "page", "url": self.url, "title": self.title}

    def navigate_tab(self, tab_id, url):
        self.calls.append(("navigate", tab_id, url))
        self.url = url
        self.title = "Navigated"
        return True

    def evaluate_script(self, tab_id, script):
        self.calls.append(("evaluate", tab_id, script))
        if "document.querySelector" in script:
            return {"value": {"success": True, "before": {"url": self.url, "title": self.title}}}
        if "innerText" in script:
            return {"value": "Example page body"}
        return {"value": True}


def make_cap():
    cap = BrowserCapability(context=DesktopContext())
    cap.context.set_target_tab("tab-1", url="https://example.com", title="Example")
    cdp = WorkflowCDP()
    cap.cdp = cdp
    return cap, cdp


def test_navigate_tracks_actual_tab_state(monkeypatch):
    cap, cdp = make_cap()
    monkeypatch.setattr(cap, "_ensure_chrome_running", lambda: True)
    result = cap.execute(Action(action="navigate", parameters={"url": "https://example.com/docs"}))
    assert result.success
    assert result.data == "https://example.com/docs"
    assert result.metadata["tab_id"] == "tab-1"
    assert result.metadata["current_url"] == "https://example.com/docs"
    assert cap.context.target_tab_url == "https://example.com/docs"


def test_click_records_before_and_after_state(monkeypatch):
    cap, _ = make_cap()
    monkeypatch.setattr(cap, "_ensure_chrome_running", lambda: True)
    result = cap.execute(Action(action="click_web_element", parameters={"selector": "#submit"}))
    assert result.success
    assert result.metadata["before_url"] == "https://example.com"
    assert result.metadata["tab_id"] == "tab-1"


def test_read_page_returns_page_identity(monkeypatch):
    cap, _ = make_cap()
    monkeypatch.setattr(cap, "_ensure_chrome_running", lambda: True)
    result = cap.execute(Action(action="read_web_page"))
    assert result.success
    assert result.data == "Example page body"
    assert result.metadata["current_url"] == "https://example.com"
    assert result.metadata["tab_title"] == "Example"


def test_cdp_real_class_exposes_executor_aliases():
    from advi.capabilities.browser.cdp import CDPBrowser
    assert hasattr(CDPBrowser, "evaluate_script")
    assert hasattr(CDPBrowser, "navigate_tab")
