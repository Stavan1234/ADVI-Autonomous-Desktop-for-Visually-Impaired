from advi.core.action_contracts import validate_and_normalize_action
from advi.core.action_plan import Action


def test_alias_is_normalized():
    action, errors = validate_and_normalize_action(Action(action="type_text", parameters={"value": "hello"}))
    assert not errors
    assert action.parameters["text"] == "hello"


def test_target_can_fill_required_parameter_when_allowed():
    action, errors = validate_and_normalize_action(Action(action="navigate", target="example.com"))
    assert not errors
    assert action.parameters["url"] == "example.com"


def test_missing_required_parameter_is_rejected():
    action, errors = validate_and_normalize_action(Action(action="save_file", parameters={"path": "x.txt"}))
    assert action is None
    assert any("content" in e for e in errors)


def test_wrong_integer_type_is_rejected():
    action, errors = validate_and_normalize_action(Action(action="scroll", parameters={"amount": "many"}))
    assert action is None
    assert any("amount" in e for e in errors)


def test_unknown_action_is_left_for_registry_validation():
    action, errors = validate_and_normalize_action(Action(action="future_action", parameters={"anything": 1}))
    assert not errors
    assert action is not None
