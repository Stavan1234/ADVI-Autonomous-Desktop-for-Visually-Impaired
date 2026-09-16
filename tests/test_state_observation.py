from pathlib import Path

from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus
from advi.core.action_plan import Action
from advi.core.execution_engine import ExecutionEngine
from advi.core.state_observation import FileStateSource, ObservedState, StateObserver


def test_observed_state_is_json_friendly(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("hello")
    observed = StateObserver(files=FileStateSource()).observe(
        type("Ctx", (), {"current_application": "Test", "target_hwnd": None,
                          "target_tab_url": None, "target_tab_title": None,
                          "target_tab_id": None})(),
        paths=[target],
    )
    data = observed.to_dict()
    assert data["application"] == "Test"
    assert data["files"][str(target.resolve())]["exists"] is True
    assert data["files"][str(target.resolve())]["size_bytes"] == 5


def test_execution_result_contains_before_and_after_state(tmp_path):
    class Handler:
        context = None
        def execute(self, action):
            target_file = Path(action.parameters["path"])
            target_file.write_text(action.parameters.get("content", ""), encoding="utf-8")
            return __import__("advi.core.action_plan", fromlist=["ExecutionResult"]).ExecutionResult(
                action=action.action, success=True, data=str(target_file)
            )

    registry = CapabilityRegistry()
    registry.register(Capability(
        name="fake_files", description="fake", supported_actions={"create_file"},
        status=CapabilityStatus.AVAILABLE, handler=Handler(),
    ))
    engine = ExecutionEngine(registry=registry)
    target = tmp_path / "advi_observe.txt"

    # Execute through a real plan to exercise state capture around the action.
    from advi.core.action_plan import ActionPlan
    plan_result = engine.execute_plan(ActionPlan(
        goal="create observed file",
        actions=[Action(action="create_file", parameters={"path": str(target), "content": "abc"})],
    ))
    final = plan_result[-1]
    assert "state_before" in final.metadata
    assert "state_after" in final.metadata
    assert final.metadata["state_after"]["files"][str(target.resolve())]["exists"] is True
