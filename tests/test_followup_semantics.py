from advi.brain.context import AgentContext
from advi.brain.followup_semantics import FollowUpSemantics


def ctx(active=True, refs=None):
    return AgentContext(
        current_message="",
        active_task={"task_id": "t1", "goal": "draft an email", "status": "completed"} if active else None,
        resolved_references=refs or [],
    )


def test_explicit_field_change_is_structured():
    d = FollowUpSemantics().interpret("change the recipient to Daniel", ctx())
    assert d.kind == "modify"
    assert d.field == "recipient"
    assert d.value == "Daniel"


def test_style_edit_becomes_task_modification():
    d = FollowUpSemantics().interpret("make it more formal", ctx())
    assert d.kind == "modify"
    assert d.task_update == "make it more formal"


def test_resume_is_distinct_from_modify():
    d = FollowUpSemantics().interpret("continue with that", ctx())
    assert d.kind == "resume"


def test_reference_action_requires_resolved_reference():
    d = FollowUpSemantics().interpret("send that", ctx(refs=[{"kind": "entity", "value": "draft"}]))
    assert d.kind == "reference_action"
    assert d.action == "email_send"


def test_reference_action_does_not_guess_without_reference():
    d = FollowUpSemantics().interpret("send that", ctx(refs=[]))
    assert d.kind == "none"


def test_plain_message_is_untouched():
    d = FollowUpSemantics().interpret("hello there", ctx())
    assert d.kind == "none"
