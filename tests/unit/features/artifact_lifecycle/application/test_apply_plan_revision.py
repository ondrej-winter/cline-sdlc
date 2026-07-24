"""Tests for bounded material revision and re-review state transitions."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from cline_sdlc.features.artifact_lifecycle.application.use_cases.apply_plan_revision import (
    apply_subsequent_plan_review,
    validate_plan_revision,
)
from cline_sdlc.features.artifact_lifecycle.domain.findings import (
    Finding,
    FindingSet,
    FindingSeverity,
    FindingStatus,
    PlanReviewReadiness,
)
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase, PlanState, ReviewReadiness

NOW = datetime(2026, 7, 25, tzinfo=UTC)
DIGEST_1 = f"sha256:{'1' * 64}"
DIGEST_2 = f"sha256:{'2' * 64}"
DIGEST_3 = f"sha256:{'3' * 64}"
SECOND_REVIEW_ITERATION = 2
FINAL_REVIEW_ITERATION = 3


def test_accepts_exactly_one_material_revision_without_advancing_review() -> None:
    previous = _state()
    revised = replace(previous, plan_revision=2, material_digest=_digest("2"), updated_at=NOW)

    validate_plan_revision(previous, revised)


@pytest.mark.parametrize(
    ("revision", "digest", "iteration", "specification", "expected"),
    [
        (3, DIGEST_2, 1, "docs/specs/example.md", "increment"),
        (2, DIGEST_1, 1, "docs/specs/example.md", "new material digest"),
        (2, DIGEST_2, 2, "docs/specs/example.md", "must not advance"),
        (2, DIGEST_2, 1, "docs/specs/other.md", "preserve"),
    ],
)
def test_rejects_invalid_material_revision(
    revision: int,
    digest: str,
    iteration: int,
    specification: str,
    expected: str,
) -> None:
    revised = replace(
        _state(),
        plan_revision=revision,
        material_digest=digest,
        review_iteration=iteration,
        specification=specification,
    )
    with pytest.raises(ValueError, match=expected):
        validate_plan_revision(_state(), revised)


def test_ready_re_review_advances_iteration_and_marks_plan_ready() -> None:
    result = apply_subsequent_plan_review(
        replace(_state(), plan_revision=2, material_digest=DIGEST_2),
        findings=FindingSet(),
        readiness=PlanReviewReadiness.READY,
        updated_at=NOW,
    )

    assert result.phase is PlanPhase.READY
    assert result.review_iteration == SECOND_REVIEW_ITERATION
    assert result.review_readiness is ReviewReadiness.READY


def test_final_non_ready_review_blocks_with_unresolved_findings() -> None:
    result = apply_subsequent_plan_review(
        replace(_state(), plan_revision=3, review_iteration=2, material_digest=DIGEST_3),
        findings=FindingSet((_finding(),)),
        readiness=PlanReviewReadiness.CHANGES_REQUIRED,
        updated_at=NOW,
    )

    assert result.phase is PlanPhase.BLOCKED
    assert result.review_iteration == FINAL_REVIEW_ITERATION
    assert result.review_readiness is ReviewReadiness.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "plan_review_limit_exhausted"


def _state() -> PlanState:
    return PlanState(
        work_id="example-work",
        phase=PlanPhase.REVIEWING,
        specification="docs/specs/example.md",
        specification_digest=_digest("1"),
        plan_revision=1,
        review_iteration=1,
        review_readiness=ReviewReadiness.CHANGES_REQUIRED,
        material_digest=_digest("1"),
        created_at=datetime(2026, 7, 24, tzinfo=UTC),
        updated_at=datetime(2026, 7, 24, tzinfo=UTC),
    )


def _finding() -> Finding:
    return Finding(
        id="PLAN-001",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        summary="Validation scope is incomplete.",
        evidence="The broad quality gate is missing.",
        required_correction="Add the broad quality gate.",
    )


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"
