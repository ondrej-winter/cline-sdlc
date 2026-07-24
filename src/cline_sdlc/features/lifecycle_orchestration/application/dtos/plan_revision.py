"""DTOs for bounded material plan revision sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.domain.findings import Finding
    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanState
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_review import PlanReviewRequest


class PlanRevisionStatus(StrEnum):
    """Terminal status for one bounded material plan revision."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class PlanRevisionRequest:
    """Inputs for one fresh author correction of reviewed findings."""

    review_request: PlanReviewRequest
    prior_state: PlanState
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class PlanRevisionResult:
    """Independently validated result of one material revision."""

    status: PlanRevisionStatus
    plan_state: PlanState | None = None
    output_paths: tuple[str, ...] = field(default_factory=tuple)
    blocker_code: str | None = None
    blocker_summary: str | None = None

    @property
    def completed(self) -> bool:
        """Return whether the revised plan passed independent validation."""
        return self.status is PlanRevisionStatus.COMPLETED
