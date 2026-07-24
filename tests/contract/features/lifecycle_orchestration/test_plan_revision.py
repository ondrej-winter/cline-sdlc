"""Contract tests for bounded plan revision and re-review coordination."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from cline_sdlc.features.artifact_lifecycle.domain.findings import (
    Finding,
    FindingSeverity,
    FindingStatus,
    PlanReviewReadiness,
)
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import (
    PlanBlocker,
    PlanPhase,
    PlanState,
    ReviewReadiness,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_review import (
    PlanReviewRequest,
    PlanReviewResult,
    PlanReviewStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_revision import (
    PlanRevisionRequest,
    PlanRevisionResult,
    PlanRevisionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.complete_plan_review import CompletePlanReview
from tests.contract.features.lifecycle_orchestration.test_plan_review import plan_review_request

NOW = datetime(2026, 7, 25, tzinfo=UTC)
SECOND_REVIEW_ITERATION = 2
FINAL_REVIEW_ITERATION = 3


@dataclass
class SequencedReviewer:
    results: list[PlanReviewResult]
    requests: list[PlanReviewRequest]

    def execute(self, request: PlanReviewRequest) -> PlanReviewResult:
        self.requests.append(request)
        return self.results.pop(0)


@dataclass
class SequencedReviser:
    results: list[PlanRevisionResult]
    requests: list[PlanRevisionRequest]

    def execute(self, request: PlanRevisionRequest) -> PlanRevisionResult:
        self.requests.append(request)
        return self.results.pop(0)


def test_one_revision_uses_fresh_re_review_and_returns_ready() -> None:
    first_state = _state(iteration=1, revision=1)
    revised_state = replace(first_state, plan_revision=2, material_digest=_digest("2"))
    ready_state = replace(
        revised_state,
        phase=PlanPhase.READY,
        review_iteration=2,
        review_readiness=ReviewReadiness.READY,
    )
    reviewer = SequencedReviewer(
        [_changes_required(first_state), PlanReviewResult(status=PlanReviewStatus.READY, plan_state=ready_state)],
        [],
    )
    reviser = SequencedReviser(
        [PlanRevisionResult(status=PlanRevisionStatus.COMPLETED, plan_state=revised_state)],
        [],
    )

    result = CompletePlanReview(reviewer=reviewer, reviser=reviser).execute(plan_review_request())

    assert result.status is PlanReviewStatus.READY
    assert len(reviser.requests) == 1
    assert len(reviewer.requests) == SECOND_REVIEW_ITERATION
    assert reviewer.requests[1].initial_review is False
    assert reviewer.requests[1].previous_plan_state == first_state
    assert reviewer.requests[1].prior_findings == (_finding(),)
    assert reviser.requests[0].findings == (_finding(),)


def test_two_failed_revisions_end_blocked_without_later_session() -> None:
    state_1 = _state(iteration=1, revision=1)
    state_2 = _state(iteration=2, revision=2)
    blocked_state = replace(
        _state(iteration=3, revision=3),
        phase=PlanPhase.BLOCKED,
        review_readiness=ReviewReadiness.BLOCKED,
        blocker=PlanBlocker(code="plan_review_limit_exhausted", summary="Review limit exhausted."),
    )
    reviewer = SequencedReviewer(
        [
            _changes_required(state_1),
            _changes_required(state_2),
            PlanReviewResult(status=PlanReviewStatus.BLOCKED, findings=(_finding(),), plan_state=blocked_state),
        ],
        [],
    )
    reviser = SequencedReviser(
        [
            PlanRevisionResult(status=PlanRevisionStatus.COMPLETED, plan_state=replace(state_1, plan_revision=2)),
            PlanRevisionResult(status=PlanRevisionStatus.COMPLETED, plan_state=replace(state_2, plan_revision=3)),
        ],
        [],
    )

    result = CompletePlanReview(reviewer=reviewer, reviser=reviser).execute(plan_review_request())

    assert result.status is PlanReviewStatus.BLOCKED
    assert len(reviewer.requests) == FINAL_REVIEW_ITERATION
    assert len(reviser.requests) == SECOND_REVIEW_ITERATION


def test_revision_failure_starts_no_re_review() -> None:
    reviewer = SequencedReviewer([_changes_required(_state(iteration=1, revision=1))], [])
    reviser = SequencedReviser(
        [
            PlanRevisionResult(
                status=PlanRevisionStatus.BLOCKED,
                blocker_code="finding_traceability_mismatch",
                blocker_summary="Prior finding IDs were not preserved.",
            )
        ],
        [],
    )

    result = CompletePlanReview(reviewer=reviewer, reviser=reviser).execute(plan_review_request())

    assert result.status is PlanReviewStatus.BLOCKED
    assert result.blocker is not None
    assert result.blocker.code == "finding_traceability_mismatch"
    assert len(reviewer.requests) == 1


def _changes_required(state: PlanState) -> PlanReviewResult:
    return PlanReviewResult(
        status=PlanReviewStatus.CHANGES_REQUIRED,
        readiness=PlanReviewReadiness.CHANGES_REQUIRED,
        findings=(_finding(),),
        plan_state=state,
    )


def _state(*, iteration: int, revision: int) -> PlanState:
    return PlanState(
        work_id="example-work",
        phase=PlanPhase.REVIEWING,
        specification="docs/specs/example-spec.md",
        specification_digest=_digest("1"),
        plan_revision=revision,
        review_iteration=iteration,
        review_readiness=ReviewReadiness.CHANGES_REQUIRED,
        material_digest=_digest(str(revision)),
        created_at=NOW,
        updated_at=NOW,
    )


def _finding() -> Finding:
    return Finding(
        id="PLAN-001",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        summary="Validation scope is incomplete.",
        evidence="The plan omits the broad quality gate.",
        required_correction="Add the broad quality gate.",
    )


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"
