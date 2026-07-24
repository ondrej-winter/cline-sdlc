"""DTOs for the rough-idea refinement lifecycle stage."""

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


class IdeaRefinementStatus(StrEnum):
    """Terminal status for one rough-idea refinement transaction."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class IdeaRefinementBlocker:
    """Actionable reason that prevents completing an idea-refinement stage."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "idea-refinement blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "idea-refinement blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class IdeaRefinementRequest:
    """Application request to run one supervised rough-idea refinement stage."""

    invocation: InvocationRequest
    preflight_request: StagePreflightRequest
    output_artifact: ArtifactLocationResult

    def __post_init__(self) -> None:
        if self.invocation.source.kind is not StageInputKind.IDEA:
            message = "idea refinement requires a rough-idea invocation source"
            raise ValueError(message)
        if self.invocation.stage is not LifecycleStage.IDEA_REFINEMENT:
            message = "idea refinement requires the idea-refinement lifecycle stage"
            raise ValueError(message)
        if not str(self.invocation.source.value).strip():
            message = "rough idea must not be empty"
            raise ValueError(message)
        if self.output_artifact.artifact_kind is not ArtifactKind.IDEA_BRIEF:
            message = "idea refinement must target an idea-brief artifact"
            raise ValueError(message)


@dataclass(frozen=True)
class IdeaRefinementResult:
    """Typed outcome of coordinating one rough-idea refinement stage."""

    status: IdeaRefinementStatus
    output_paths: tuple[str, ...] = field(default_factory=tuple)
    blocker: IdeaRefinementBlocker | None = None

    @property
    def completed(self) -> bool:
        """Return whether the idea-refinement stage reached its artifact boundary."""
        return self.status is IdeaRefinementStatus.COMPLETED
