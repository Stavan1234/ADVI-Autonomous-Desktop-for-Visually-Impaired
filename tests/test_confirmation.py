from advi.brain.task_state import ActiveTask, TaskStatus
from advi.core.action_plan import Action, ActionPlan
from advi.core.confirmation import ConfirmationManager


def make_plan(recipient="a@example.com"):
    return ActionPlan(
        goal="send an email",
        actions=[Action(action="email_send", parameters={"to": recipient, "body": "hello"})],
    )


def test_confirmation_is_bound_to_exact_plan():
    manager = ConfirmationManager()
    plan = make_plan()
    record = manager.issue(plan)

    assert manager.validate(plan, record.fingerprint)

    changed = make_plan("b@example.com")
    assert not manager.validate(changed, record.fingerprint)


def test_confirmation_changes_when_plan_parameters_change():
    manager = ConfirmationManager()
    first = make_plan()
    second = make_plan()
    second.actions[0].parameters["body"] = "different"

    assert manager.fingerprint_plan(first) != manager.fingerprint_plan(second)


def test_task_modification_invalidates_confirmation():
    task = ActiveTask(goal="send an email")
    task.confirmation_fingerprint = "approved-plan"
    task.status = TaskStatus.AWAITING_CONFIRMATION

    task.apply_modification("change recipient")

    assert task.confirmation_fingerprint is None


def test_missing_input_cannot_retain_old_confirmation():
    task = ActiveTask(goal="send an email")
    task.confirmation_fingerprint = "approved-plan"
    task.set_awaiting_input("recipient")

    assert task.confirmation_fingerprint is None


def test_confirmation_is_single_use():
    manager = ConfirmationManager()
    plan = make_plan()
    record = manager.issue(plan)

    assert manager.validate(plan, record.fingerprint, expires_at=record.expires_at)
    assert manager.consume(record.fingerprint)
    assert not manager.validate(plan, record.fingerprint, expires_at=record.expires_at)
    assert not manager.consume(record.fingerprint)


def test_confirmation_expiration_invalidates_approval():
    manager = ConfirmationManager()
    plan = make_plan()
    record = manager.issue(plan)

    assert not manager.validate(
        plan,
        record.fingerprint,
        issued_at=record.issued_at,
        expires_at=record.issued_at - 1,
    )


def test_confirmation_ttl_is_bounded():
    manager = ConfirmationManager(ttl_seconds=30)
    record = manager.issue(make_plan())
    assert 29 <= record.expires_at - record.issued_at <= 30.5
