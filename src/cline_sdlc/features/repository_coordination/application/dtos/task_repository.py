"""DTOs for staged repository task inspection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path  # noqa: TC003 - Runtime dataclass annotations intentionally expose Path.

from cline_sdlc.features.repository_coordination.application.dtos.repository import (
    DEFAULT_PROTECTED_BRANCH_PATTERNS,
)


class TaskRepositoryInspectionStatus(StrEnum):
    """Terminal status for staged repository task inspection."""

    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class TaskRepositoryInspectionBlocker:
    """Actionable reason that prevents staged repository task execution."""

    code: str
    summary: str
    path: str | None = None
    evidence: str | None = None


@dataclass(frozen=True)
class StagedChangeSet:
    """Read-only evidence for already staged repository content."""

    repository_root: str
    head_commit: str
    branch: str | None
    staged_paths: tuple[str, ...]
    staged_diff_digest: str
    staged_diff_summary: str
    read_only: bool = True
    operation_states: tuple[str, ...] = ()
    unstaged_paths: tuple[str, ...] = ()

    @property
    def has_staged_changes(self) -> bool:
        """Return whether the change set contains any staged paths."""
        return bool(self.staged_paths)


@dataclass(frozen=True)
class TaskRepositoryInspectionRequest:
    """Application request to inspect staged changes for a repository task."""

    working_directory: Path
    authorized_paths: tuple[Path, ...] = ()
    protected_branch_patterns: tuple[str, ...] = DEFAULT_PROTECTED_BRANCH_PATTERNS


@dataclass(frozen=True)
class TaskRepositoryInspectionResult:
    """Typed staged repository inspection result for repository tasks."""

    status: TaskRepositoryInspectionStatus
    change_set: StagedChangeSet | None = None
    blockers: tuple[TaskRepositoryInspectionBlocker, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        """Return whether staged repository state satisfies task requirements."""
        return self.status is TaskRepositoryInspectionStatus.READY
