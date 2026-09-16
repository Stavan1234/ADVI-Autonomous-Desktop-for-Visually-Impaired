from __future__ import annotations

from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus
from advi.core.action_plan import Action
from advi.core.capability_policy import CapabilityPolicy, PolicyDisposition
from advi.core.capabilities import capability_for_registry_prompt


class Handler:
    def execute(self, action):
        return None


def make_registry():
    r = CapabilityRegistry()
    r.register(Capability(
        name="files", description="files", supported_actions={"read_file", "delete_file"},
        status=CapabilityStatus.AVAILABLE, handler=Handler(),
    ))
    return r


def test_registry_exposes_canonical_action_spec():
    spec = make_registry().get_action_spec("delete_file")
    assert spec is not None
    assert spec.action == "delete_file"
    assert spec.capability == "files"
    assert spec.requires_confirmation is True
    assert spec.verification == "file_absence"
    assert "path" in spec.parameters


def test_actions_for_prompt_is_generated_from_specs():
    text = make_registry().actions_for_prompt()
    assert "delete_file:" in text
    assert "confirmation=true" in text
    assert "required_parameters=path" in text


def test_policy_uses_canonical_spec_not_duplicated_metadata():
    policy = CapabilityPolicy(make_registry())
    decision = policy.evaluate_action(Action(action="delete_file", target="/tmp/x"))
    assert decision.disposition == PolicyDisposition.CONFIRM


def test_registry_prompt_adapter_uses_runtime_state():
    text = capability_for_registry_prompt(make_registry())
    assert "files" in text
    assert "delete_file" not in text  # summary is capability-level; action prompt owns action semantics
