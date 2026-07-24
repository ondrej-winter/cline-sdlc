"""DTOs for the idea-to-specification lifecycle stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationResult,
)
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage, StageInputKind

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import StagePreflightRequest


class SpecificationCreationStatus(StrEnum):
    """Terminal status for one idea-to-specification transaction."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class SpecificationCreationBlocker:
    """Actionable reason that prevents completing a specification-creation stage."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "specification-creation blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "specification-creation blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SpecificationCreationRequest:
    """Application request to run one supervised idea-to-specification stage."""

    invocation: InvocationRequest
    preflight_request: StagePreflightRequest
    output_artifact: ArtifactLocationResult

    def __post_init__(self) -> None:
        if self.invocation.source.kind is not StageInputKind.IDEA_FILE:
            message = "specification creation requires an idea-file invocation source"
            raise ValueError(message)
        if self.invocation.stage is not LifecycleStage.SPECIFICATION_CREATION:
            message = "specification creation requires the specification-creation lifecycle stage"
            raise ValueError(message)
        if self.output_artifact.artifact_kind is not ArtifactKind.SPECIFICATION:
            message = "specification creation must target a specification artifact"
            raise ValueError(message)


@dataclass(frozen=True)
class SpecificationCreationResult:
    """Typed outcome of coordinating one specification-creation stage."""

    status: SpecificationCreationStatus
    output_paths: tuple[str, ...] = field(default_factory=tuple)
    blocker: SpecificationCreationBlocker | None = None

    @property
    def completed(self) -> bool:
        """Return whether the specification-creation stage reached its artifact boundary."""
        return self.status is SpecificationCreationStatus.COMPLETED
