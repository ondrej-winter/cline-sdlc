"""DTOs for supervised lifecycle invocation selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage, StageInputKind

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class InvocationSource:
    """One explicit user-selected lifecycle input."""

    kind: StageInputKind
    value: str | Path

    @classmethod
    def from_idea(cls, idea: str) -> InvocationSource:
        """Create a rough-idea invocation source."""
        return cls(kind=StageInputKind.IDEA, value=idea)

    @classmethod
    def from_idea_file(cls, path: Path) -> InvocationSource:
        """Create an idea-file invocation source."""
        return cls(kind=StageInputKind.IDEA_FILE, value=path)

    @classmethod
    def from_spec_file(cls, path: Path) -> InvocationSource:
        """Create a specification-file invocation source."""
        return cls(kind=StageInputKind.SPEC_FILE, value=path)

    @classmethod
    def from_plan_file(cls, path: Path) -> InvocationSource:
        """Create a plan-file invocation source."""
        return cls(kind=StageInputKind.PLAN_FILE, value=path)


@dataclass(frozen=True)
class InvocationRequest:
    """Application request for one bounded supervised lifecycle stage."""

    source: InvocationSource
    timeout_seconds: float
    cline_command: str
    emit_json: bool = False
    verbose: bool = False
    dry_run: bool = False
    stage: LifecycleStage | None = None


@dataclass(frozen=True)
class InvocationParseError:
    """Usage-level parsing error that must not start Cline."""

    message: str
