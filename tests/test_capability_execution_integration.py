from pathlib import Path

from advi.capabilities.files.executor import FileCapability
from advi.capabilities.gmail.executor import GmailCapability
from advi.capabilities.browser.executor import BrowserCapability
from advi.capabilities.desktop.executor import DesktopCapability
from advi.capabilities.memory.executor import MemoryCapability
from advi.capabilities.desktop.context import DesktopContext
from advi.core.action_plan import Action


def test_file_capability_round_trip(tmp_path):
    cap = FileCapability()
    cap.desktop_dir = tmp_path

    created = cap.execute(Action(action="create_file", parameters={"path": "note.txt", "content": "hello"}))
    assert created.success and created.verified

    read = cap.execute(Action(action="read_file", parameters={"path": "note.txt"}))
    assert read.success
    assert read.data == "hello"

    listing = cap.execute(Action(action="list_files", parameters={"directory": str(tmp_path)}))
    assert listing.success and "note.txt" in listing.data

    deleted = cap.execute(Action(action="delete_file", parameters={"path": "note.txt"}))
    assert deleted.success and deleted.verified


def test_browser_capability_real_executor_with_fake_cdp(monkeypatch):
    cap = BrowserCapability(context=DesktopContext())
    cap.context.set_target_tab("tab-1", url="https://example.com", title="Example")

    class FakeCDP:
        def list_tabs(self):
            return [{"id": "tab-1", "type": "page", "url": "https://example.com"}]

        def evaluate_script(self, tab_id, script):
            assert tab_id == "tab-1"
            if "innerText" in script:
                return {"value": "Example page"}
            if "document.querySelector" in script:
                return {"value": True}
            return {"value": True}

        def navigate_tab(self, tab_id, url):
            assert tab_id == "tab-1"
            return True

    cap.cdp = FakeCDP()
    monkeypatch.setattr(cap, "_ensure_chrome_running", lambda: True)

    nav = cap.execute(Action(action="navigate", parameters={"url": "https://example.com/test"}))
    assert nav.success and nav.data == "https://example.com/test"

    page = cap.execute(Action(action="read_web_page"))
    assert page.success and page.data == "Example page"
    assert page.metadata["tab_id"] == "tab-1"

    click = cap.execute(Action(action="click_web_element", parameters={"selector": "#ok"}))
    assert click.success


def test_gmail_capability_actions_with_fake_service():
    class FakeService:
        def create_draft(self, **kwargs):
            return type("Draft", (), {"draft_id": "d1"})()

        def get_draft(self, draft_id):
            return {"draft_id": draft_id, "subject": "Test"}

        def update_draft(self, **kwargs):
            return {"id": kwargs["draft_id"]}

        def send_email(self, **kwargs):
            return {"id": "m1"}

        def send_draft(self, draft_id):
            return {"id": "m2"}

        def list_messages(self, query, max_results):
            return [{"id": "1"}]

    cap = GmailCapability(FakeService())
    assert cap.execute(Action(action="email_draft_create", parameters={"to": "a@b.com", "subject": "T", "body": "B"})).verified
    assert cap.execute(Action(action="email_draft_read", parameters={"draft_id": "d1"})).success
    assert cap.execute(Action(action="email_draft_update", parameters={"draft_id": "d1", "body": "B2"})).verified
    assert cap.execute(Action(action="email_send", parameters={"to": "a@b.com", "subject": "T", "body": "B"})).verified
    assert cap.execute(Action(action="email_send", parameters={"draft_id": "d1"})).verified
    assert cap.execute(Action(action="email_read", parameters={"query": "is:inbox", "limit": 1})).verified


def test_desktop_capability_real_executor_wait_only(monkeypatch):
    cap = DesktopCapability(context=DesktopContext())
    monkeypatch.setattr("advi.capabilities.desktop.executor.time.sleep", lambda _seconds: None)
    result = cap.execute(Action(action="wait", parameters={"duration": 0.1}))
    assert result.success
    assert result.data == 0.1


def test_memory_capability_retrieval_with_fake_retriever():
    class FakeRetriever:
        def retrieve(self, query, limit=5):
            return [f"fact:{query}"]

    cap = MemoryCapability(retriever=FakeRetriever())
    result = cap.execute(Action(action="memory_retrieval", parameters={"query": "favorite editor"}))
    assert result.success and result.verified
    assert result.data == ["fact:favorite editor"]
