from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus
from advi.core.action_plan import Action
from advi.core.capability_policy import CapabilityPolicy, PolicyDisposition


def registry_with(*actions):
    r = CapabilityRegistry()
    r.register(Capability(name='test', description='test', supported_actions=set(actions), status=CapabilityStatus.AVAILABLE))
    return r


def test_policy_requires_confirmation_from_registry_semantics():
    policy = CapabilityPolicy(registry_with('email_send'))
    decision = policy.evaluate_action(Action(action='email_send'))
    assert decision.disposition == PolicyDisposition.CONFIRM


def test_policy_allows_low_side_effect_action():
    policy = CapabilityPolicy(registry_with('read_file'))
    decision = policy.evaluate_action(Action(action='read_file', parameters={'path': 'x.txt'}))
    assert decision.disposition == PolicyDisposition.ALLOW


def test_policy_denies_unavailable_action():
    policy = CapabilityPolicy(registry_with('read_file'))
    decision = policy.evaluate_action(Action(action='delete_file'))
    assert decision.disposition == PolicyDisposition.DENY


def test_policy_evaluates_whole_plan():
    policy = CapabilityPolicy(registry_with('read_file', 'email_send'))
    decisions = policy.evaluate_plan([
        Action(action='read_file'),
        Action(action='email_send'),
    ])
    assert [d.disposition for d in decisions] == [PolicyDisposition.ALLOW, PolicyDisposition.CONFIRM]
