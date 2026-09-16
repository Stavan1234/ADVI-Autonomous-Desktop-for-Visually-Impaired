from advi.core.action_plan import ActionPlan, ExecutionResult, VerificationStatus
from advi.core.goal_verification import GoalVerificationStatus, GoalVerifier


def test_verified_goal_requires_definitive_evidence():
    plan = ActionPlan(goal="create a file", actions=[])
    result = ExecutionResult(
        action="save_file",
        success=True,
        verified=True,
        verification_status=VerificationStatus.VERIFIED,
        verification_details={"exists": True},
        metadata={"state_after": {"files": {"x": {"exists": True}}}},
    )
    outcome = GoalVerifier().verify(plan, [result])
    assert outcome.status == GoalVerificationStatus.VERIFIED
    assert outcome.verified is True


def test_goal_is_uncertain_when_action_success_is_uncertain():
    plan = ActionPlan(goal="open the app", actions=[])
    result = ExecutionResult(
        action="open_application",
        success=True,
        verification_status=VerificationStatus.UNCERTAIN,
    )
    outcome = GoalVerifier().verify(plan, [result])
    assert outcome.status == GoalVerificationStatus.UNCERTAIN
    assert outcome.verified is False


def test_failed_goal_wins_over_other_successes():
    plan = ActionPlan(goal="do two things", actions=[])
    results = [
        ExecutionResult(action="save_file", success=True, verification_status=VerificationStatus.VERIFIED),
        ExecutionResult(action="email_send", success=False, error="network down"),
    ]
    outcome = GoalVerifier().verify(plan, results)
    assert outcome.status == GoalVerificationStatus.FAILED
    assert "network down" in outcome.reason
