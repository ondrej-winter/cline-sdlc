"""DTOs for authorizing repository plan finalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import FinalReviewResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import FinalValidationResult
    from cline_sdlc.features.repository_coordination.application.dtos.finalization import (
        FinalizationResult,
        RepositoryFinalizationRequest,
    )
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval


@dataclass(frozen=True)
class PlanFinalizationRequest:
    """Clean final evidence and exact repository finalization transaction."""

    approval: InvocationApproval
    final_validation: FinalValidationResult
    final_review: FinalReviewResult
    repository_request: RepositoryFinalizationRequest


@dataclass(frozen=True)
class PlanFinalizationResult:
    """Repository finalization result after lifecycle evidence authorization."""

    repository_result: FinalizationResult
