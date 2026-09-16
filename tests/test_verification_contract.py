from advi.core.action_plan import Action, ExecutionResult, VerificationStatus
from advi.core.verification import ActionVerifier


class NoopVerifier(ActionVerifier):
    pass


def test_no_verifier_is_explicitly_uncertain():
    result = NoopVerifier().verify(
        Action(action="wait", parameters={"seconds": 1}),
        ExecutionResult(action="wait", success=True),
    )
    assert result.success is True
    assert result.verified is False
    assert result.verification_status == VerificationStatus.UNCERTAIN


def test_verifier_summary_distinguishes_failed_uncertain_and_verified():
    results = [
        ExecutionResult(action="open_application", success=True, verified=True, verification_status=VerificationStatus.VERIFIED),
        ExecutionResult(action="wait", success=True, verification_status=VerificationStatus.UNCERTAIN),
    ]
    summary = ActionVerifier.summarize(results)
    assert summary == {"status": "uncertain", "verified": 1, "uncertain": 1, "failed": 0}


def test_definitive_verification_failure_is_failed_not_uncertain():
    verifier = ActionVerifier()
    result = verifier.verify(
        Action(action="save_file", parameters={"path": "Desktop/__advi_missing_for_test__.txt"}),
        ExecutionResult(action="save_file", success=True),
    )
    assert result.success is False
    assert result.verified is False
    assert result.verification_status == VerificationStatus.FAILED
