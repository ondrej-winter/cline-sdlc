"""Authorize plan finalization from clean final evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import FinalReviewStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import FinalValidationStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.finalization import PlanFinalizationResult
from cline_sdlc.features.repository_coordination.application.dtos.finalization import (
    FinalizationBlocker,
    FinalizationResult,
    FinalizationStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.finalization import PlanFinalizationRequest
    from cline_sdlc.features.repository_coordination.application.dtos.finalization import RepositoryFinalizationRequest


class RepositoryFinalizationPort(Protocol):
    """Boundary for the progress-only repository transaction."""

    def execute(self, request: RepositoryFinalizationRequest) -> FinalizationResult:
        """Create or verify the unique finalization commit."""


class FinalizeImplementationPlan:
    """Permit finalization only after current passing evidence and clean review."""

    def __init__(self, repository_finalization: RepositoryFinalizationPort) -> None:
        self._repository_finalization = repository_finalization

    def execute(self, request: PlanFinalizationRequest) -> PlanFinalizationResult:
        """Return a repository result without starting any further Cline session."""
        blocker = _evidence_blocker(request)
        if blocker is not None:
            return PlanFinalizationResult(
                repository_result=FinalizationResult(status=FinalizationStatus.BLOCKED, blocker=blocker)
            )
        return PlanFinalizationResult(
            repository_result=self._repository_finalization.execute(request.repository_request)
        )


def _evidence_blocker(request: PlanFinalizationRequest) -> FinalizationBlocker | None:
    if request.repository_request.approval != request.approval:
        return FinalizationBlocker(
            "finalization_approval_mismatch",
            "repository finalization must use the immutable invocation approval",
        )
    validation = request.final_validation
    if validation.status is not FinalValidationStatus.COMPLETED or validation.run_id != request.approval.run_id:
        return FinalizationBlocker(
            "final_validation_incomplete",
            "finalization requires completed broad validation for this invocation",
        )
    review = request.final_review
    if review.status is not FinalReviewStatus.CLEAN or review.findings or review.remediation_records:
        return FinalizationBlocker(
            "final_review_not_clean",
            "finalization requires the latest final review to be clean",
        )
    return None
