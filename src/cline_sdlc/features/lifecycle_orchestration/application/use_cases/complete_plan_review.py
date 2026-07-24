"""Coordinate the bounded plan revision and independent re-review loop."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.artifact_lifecycle.domain.plan_state import MAX_REVIEW_ITERATION
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_review import (
    PlanReviewBlocker,
    PlanReviewRequest,
    PlanReviewResult,
    PlanReviewStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_revision import (
    PlanRevisionRequest,
    PlanRevisionStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_revision import PlanRevisionResult


class ReviewerPort(Protocol):
    """Boundary for one fresh independent review."""

    def execute(self, request: PlanReviewRequest) -> PlanReviewResult:
        """Return reconciled review evidence."""


class ReviserPort(Protocol):
    """Boundary for one fresh material author revision."""

    def execute(self, request: PlanRevisionRequest) -> PlanRevisionResult:
        """Return independently validated revised state."""


class CompletePlanReview:
    """Run the initial review and at most two revision/re-review cycles."""

    def __init__(self, *, reviewer: ReviewerPort, reviser: ReviserPort) -> None:
        self._reviewer = reviewer
        self._reviser = reviser

    def execute(self, request: PlanReviewRequest) -> PlanReviewResult:
        """Return ready or the first terminal blocker without starting later work."""
        review = self._reviewer.execute(request)
        while review.status is PlanReviewStatus.CHANGES_REQUIRED:
            if review.plan_state is None:
                return _blocked("review_state_missing", "review progress did not return reconciled plan state")
            if review.plan_state.review_iteration >= MAX_REVIEW_ITERATION:
                return review
            revision = self._reviser.execute(
                PlanRevisionRequest(review_request=request, prior_state=review.plan_state, findings=review.findings)
            )
            if revision.status is not PlanRevisionStatus.COMPLETED or revision.plan_state is None:
                return PlanReviewResult(
                    status=(
                        PlanReviewStatus.BLOCKED
                        if revision.status is PlanRevisionStatus.BLOCKED
                        else PlanReviewStatus.FAILED
                    ),
                    blocker=PlanReviewBlocker(
                        code=revision.blocker_code or "plan_revision_failed",
                        summary=revision.blocker_summary or "plan revision did not complete",
                    ),
                )
            review = self._reviewer.execute(
                replace(
                    request,
                    previous_plan_state=review.plan_state,
                    prior_findings=review.findings,
                    initial_review=False,
                )
            )
        return review


def _blocked(code: str, summary: str) -> PlanReviewResult:
    return PlanReviewResult(status=PlanReviewStatus.BLOCKED, blocker=PlanReviewBlocker(code=code, summary=summary))
