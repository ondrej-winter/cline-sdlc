"""DTOs for the initial independent implementation-plan review."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage, StageInputKind

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.domain.findings import Finding, PlanReviewReadiness
    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanState
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import StagePreflightRequest


class PlanReviewStatus(StrEnum):
    """Terminal status for the initial independent plan review."""

    READY = "ready"
    CHANGES_REQUIRED = "changes_required"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class PlanReviewBlocker:
    """Actionable reason the initial plan review could not be applied."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "plan-review blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class PlanReviewRequest:
    """Application request for one fresh read-only initial review session."""

    invocation: InvocationRequest
    preflight_request: StagePreflightRequest
    plan_path: str
    previous_plan_state: PlanState | None = None
    prior_findings: tuple[Finding, ...] = field(default_factory=tuple)
    initial_review: bool = True

    def __post_init__(self) -> None:
        if self.invocation.source.kind is not StageInputKind.SPEC_FILE:
            message = "initial plan review requires a specification-file invocation source"
            raise ValueError(message)
        if self.invocation.stage is not LifecycleStage.PLAN_CREATION_AND_REVIEW:
            message = "initial plan review requires the plan-creation-and-review stage"
            raise ValueError(message)
        if not self.plan_path.strip():
            message = "initial plan review requires a plan path"
            raise ValueError(message)
        if self.initial_review and self.prior_findings:
            message = "initial plan review must not include prior findings"
            raise ValueError(message)
        if not self.initial_review and self.previous_plan_state is None:
            message = "plan re-review requires the previous reviewed plan state"
            raise ValueError(message)


@dataclass(frozen=True)
class PlanReviewResult:
    """Typed result of the initial independent plan review."""

    status: PlanReviewStatus
    readiness: PlanReviewReadiness | None = None
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    output_paths: tuple[str, ...] = field(default_factory=tuple)
    material_digest: str | None = None
    plan_state: PlanState | None = None
    blocker: PlanReviewBlocker | None = None

    @property
    def ready(self) -> bool:
        """Return whether the first independent review marked the plan ready."""
        return self.status is PlanReviewStatus.READY
