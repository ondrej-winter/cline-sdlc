"""Tests for Cline session outcome schema values."""

import pytest

from cline_sdlc.features.cline_execution.domain.outcome import (
    SessionBlocker,
    SessionOutcome,
    SessionRole,
    SessionStatus,
    SessionValidationEvidence,
    SessionValidationResult,
)


def test_implementation_outcome_normalizes_safe_repository_paths() -> None:
    outcome = SessionOutcome(
        session_role=SessionRole.IMPLEMENTATION,
        status=SessionStatus.COMPLETED,
        reason="slice_verified",
        changed_paths=("src/example.py", "tests/test_example.py"),
        validation=(
            SessionValidationEvidence(
                command="uv run pytest tests/test_example.py",
                result=SessionValidationResult.PASSED,
                exit_code=0,
            ),
        ),
    )

    assert outcome.changed_paths == ("src/example.py", "tests/test_example.py")
    assert outcome.validation[0].result is SessionValidationResult.PASSED


def test_outcome_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValueError, match="schema version"):
        SessionOutcome(
            schema_version=2,
            session_role=SessionRole.IMPLEMENTATION,
            status=SessionStatus.COMPLETED,
            reason="slice_verified",
        )


@pytest.mark.parametrize("path", ["/absolute/file", "../escape.md", "docs/../secret.md", "docs\\secret.md", ""])
def test_outcome_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError, match="paths"):
        SessionOutcome(
            session_role=SessionRole.IMPLEMENTATION,
            status=SessionStatus.COMPLETED,
            reason="slice_verified",
            changed_paths=(path,),
        )


def test_reviewer_outcome_rejects_changed_paths() -> None:
    with pytest.raises(ValueError, match="reviewer"):
        SessionOutcome(
            session_role=SessionRole.PLAN_REVIEWER,
            status=SessionStatus.COMPLETED,
            reason="review_ready",
            changed_paths=("docs/plans/example.md",),
        )


def test_approval_required_outcome_requires_proposed_operation() -> None:
    with pytest.raises(ValueError, match="proposed operation"):
        SessionOutcome(
            session_role=SessionRole.IMPLEMENTATION,
            status=SessionStatus.APPROVAL_REQUIRED,
            reason="operation_needs_approval",
            blocker=SessionBlocker(code="approval_required", summary="Network command requested."),
        )


def test_validation_evidence_matches_not_run_exit_code_contract() -> None:
    with pytest.raises(ValueError, match="not-run"):
        SessionValidationEvidence(command="uv run pytest", result=SessionValidationResult.NOT_RUN, exit_code=0)
