"""Validate the initial plan-review state transition without performing I/O."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from cline_sdlc.features.artifact_lifecycle.domain.findings import FindingSet, PlanReviewReadiness
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase, PlanState, ReviewReadiness


def apply_initial_plan_review(
    state: PlanState,
    *,
    findings: FindingSet,
    readiness: PlanReviewReadiness,
    updated_at: datetime,
) -> PlanState:
    """Return the legal progress-only state produced by the first review."""
    if state.phase is not PlanPhase.DRAFTING or state.review_readiness is not ReviewReadiness.NOT_REVIEWED:
        message = "initial plan review requires drafting and not_reviewed state"
        raise ValueError(message)
    if updated_at.tzinfo is None or updated_at.utcoffset() != UTC.utcoffset(updated_at):
        message = "initial plan review timestamp must be timezone-aware UTC"
        raise ValueError(message)
    if findings.readiness() is not readiness:
        message = "initial plan review readiness must agree with validated findings"
        raise ValueError(message)

    phase = PlanPhase.READY if readiness is PlanReviewReadiness.READY else PlanPhase.REVIEWING
    review_readiness = (
        ReviewReadiness.READY if readiness is PlanReviewReadiness.READY else ReviewReadiness.CHANGES_REQUIRED
    )
    state.transition_to(PlanPhase.REVIEWING)
    if phase is PlanPhase.READY:
        reviewing_state = replace(state, phase=PlanPhase.REVIEWING, review_readiness=review_readiness)
        reviewing_state.transition_to(PlanPhase.READY)
    return replace(
        state,
        phase=phase,
        review_iteration=1,
        review_readiness=review_readiness,
        updated_at=updated_at,
    )
