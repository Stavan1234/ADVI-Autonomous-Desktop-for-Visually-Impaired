from pathlib import Path

from advi.capabilities.files.executor import FileCapability
from advi.capabilities.registry import Capability, CapabilityRegistry
from advi.core.action_contracts import validate_and_normalize_action
from advi.core.action_plan import Action
from advi.core.capability_policy import CapabilityPolicy, PolicyDisposition
from advi.core.verification import ActionVerifier


def test_append_file_workflow(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    cap = FileCapability()
    cap.desktop_dir = tmp_path

    result = cap.execute(Action(action="append_file", parameters={"path": "notes.txt", "content": " world"}))
    assert result.success
    assert target.read_text(encoding="utf-8") == "hello world"
    verified = ActionVerifier().verify(Action(action="append_file", parameters={"path": "notes.txt", "content": " world"}), result)
    assert verified.verified is True


def test_replace_file_text_is_exact_and_single_occurrence(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hello\nhello", encoding="utf-8")
    cap = FileCapability()
    cap.desktop_dir = tmp_path
    result = cap.execute(Action(action="replace_file_text", parameters={"path": "notes.txt", "old_text": "hello", "new_text": "hi"}))
    assert result.success
    assert target.read_text(encoding="utf-8") == "hi\nhello"


def test_replace_file_text_requires_existing_match(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    cap = FileCapability()
    cap.desktop_dir = tmp_path
    result = cap.execute(Action(action="replace_file_text", parameters={"path": "notes.txt", "old_text": "missing", "new_text": "hi"}))
    assert not result.success


def test_file_workflow_parameter_aliases_normalize():
    action, errors = validate_and_normalize_action(
        Action(action="replace_file_text", parameters={"filename": "x.txt", "old": "a", "replace": "b"})
    )
    assert not errors
    assert action is not None
    assert action.parameters["path"] == "x.txt"
    assert action.parameters["old_text"] == "a"
    assert action.parameters["new_text"] == "b"


def test_replace_file_is_not_critical_confirmation():
    registry = CapabilityRegistry()
    registry.register(Capability(name="files", description="files", supported_actions={"replace_file_text"}, handler=object()))
    policy = CapabilityPolicy(registry)
    decision = policy.evaluate_action(Action(action="replace_file_text", parameters={"path": "x", "old_text": "a", "new_text": "b"}))
    assert decision.disposition == PolicyDisposition.ALLOW
