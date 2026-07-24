"""Validate material plan revisions and subsequent review transitions."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from cline_sdlc.features.artifact_lifecycle.domain.findings import FindingSet, PlanReviewReadiness
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import (
    MAX_REVIEW_ITERATION,
    PlanBlocker,
    PlanPhase,
    PlanState,
    ReviewReadiness,
)


def validate_plan_revision(previous: PlanState, revised: PlanState) -> None:
    """Validate one material author revision against its reviewed predecessor."""
    if previous.phase is not PlanPhase.REVIEWING or previous.review_readiness is not ReviewReadiness.CHANGES_REQUIRED:
        message = "plan revision requires reviewing and changes_required state"
        raise ValueError(message)
    if revised.phase is not PlanPhase.REVIEWING or revised.review_readiness is not ReviewReadiness.CHANGES_REQUIRED:
        message = "revised plan must remain reviewing and changes_required until re-review"
        raise ValueError(message)
    if revised.plan_revision != previous.plan_revision + 1:
        message = "material plan revision must increment plan_revision exactly once"
        raise ValueError(message)
    if revised.review_iteration != previous.review_iteration:
        message = "author revision must not advance review_iteration"
        raise ValueError(message)
    if (revised.specification, revised.specification_digest) != (
        previous.specification,
        previous.specification_digest,
    ):
        message = "material revision must preserve specification identity and digest"
        raise ValueError(message)
    if revised.material_digest == previous.material_digest:
        message = "material revision must produce a new material digest"
        raise ValueError(message)


def apply_subsequent_plan_review(
    state: PlanState,
    *,
    findings: FindingSet,
    readiness: PlanReviewReadiness,
    updated_at: datetime,
) -> PlanState:
    """Apply a fresh re-review and block when the review limit is exhausted."""
    if state.phase is not PlanPhase.REVIEWING or state.review_readiness is not ReviewReadiness.CHANGES_REQUIRED:
        message = "subsequent plan review requires reviewing and changes_required state"
        raise ValueError(message)
    if state.review_iteration >= MAX_REVIEW_ITERATION:
        message = "plan review iteration limit is already exhausted"
        raise ValueError(message)
    if updated_at.tzinfo is None or updated_at.utcoffset() != UTC.utcoffset(updated_at):
        message = "subsequent plan review timestamp must be timezone-aware UTC"
        raise ValueError(message)
    if findings.readiness() is not readiness:
        message = "subsequent plan review readiness must agree with validated findings"
        raise ValueError(message)

    review_iteration = state.review_iteration + 1
    if readiness is PlanReviewReadiness.READY:
        state.transition_to(PlanPhase.READY)
        return replace(
            state,
            phase=PlanPhase.READY,
            review_iteration=review_iteration,
            review_readiness=ReviewReadiness.READY,
            updated_at=updated_at,
        )
    if review_iteration < MAX_REVIEW_ITERATION:
        return replace(state, review_iteration=review_iteration, updated_at=updated_at)

    state.transition_to(PlanPhase.BLOCKED)
    return replace(
        state,
        phase=PlanPhase.BLOCKED,
        review_iteration=review_iteration,
        review_readiness=ReviewReadiness.BLOCKED,
        blocker=PlanBlocker(
            code="plan_review_limit_exhausted",
            summary="The plan still has unresolved blocking or major findings after the final review.",
        ),
        updated_at=updated_at,
    )
