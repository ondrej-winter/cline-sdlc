"""DTOs for the initial implementation-plan authoring stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import ArtifactKind
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage, StageInputKind

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import ArtifactLocationResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import StagePreflightRequest
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import ValidationDiscoveryRequest


class PlanAuthoringStatus(StrEnum):
    """Terminal status for initial plan authoring."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class PlanAuthoringBlocker:
    """Actionable reason that initial plan authoring did not complete."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "plan-authoring blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "plan-authoring blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class PlanAuthoringRequest:
    """Application request for one bounded initial plan-author session."""

    invocation: InvocationRequest
    preflight_request: StagePreflightRequest
    validation_discovery_request: ValidationDiscoveryRequest
    output_artifact: ArtifactLocationResult

    def __post_init__(self) -> None:
        if self.invocation.source.kind is not StageInputKind.SPEC_FILE:
            message = "plan authoring requires a specification-file invocation source"
            raise ValueError(message)
        if self.invocation.stage is not LifecycleStage.PLAN_CREATION_AND_REVIEW:
            message = "plan authoring requires the plan-creation-and-review lifecycle stage"
            raise ValueError(message)
        if self.output_artifact.artifact_kind is not ArtifactKind.PLAN:
            message = "plan authoring must target a plan artifact"
            raise ValueError(message)


@dataclass(frozen=True)
class PlanAuthoringResult:
    """Typed outcome of coordinating initial plan authoring."""

    status: PlanAuthoringStatus
    output_paths: tuple[str, ...] = field(default_factory=tuple)
    specification_digest: str | None = None
    material_digest: str | None = None
    blocker: PlanAuthoringBlocker | None = None

    @property
    def completed(self) -> bool:
        """Return whether the initial authored plan passed independent validation."""
        return self.status is PlanAuthoringStatus.COMPLETED
