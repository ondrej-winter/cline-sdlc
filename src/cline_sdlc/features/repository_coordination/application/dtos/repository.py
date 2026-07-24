"""DTOs for repository inspection preflight."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path  # noqa: TC003 - Runtime dataclass annotations intentionally expose Path.


class RepositoryInspectionStatus(StrEnum):
    """Terminal status for repository inspection."""

    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class RepositoryInspectionBlocker:
    """Actionable reason that prevents repository-backed stage execution."""

    code: str
    summary: str
    path: str | None = None
    evidence: str | None = None


@dataclass(frozen=True)
class RepositoryFileObservation:
    """Git and filesystem observations for one lifecycle input file."""

    path: str
    is_regular_file: bool
    is_tracked: bool
    is_committed_at_head: bool
    matches_head: bool


@dataclass(frozen=True)
class RepositorySnapshot:
    """Repository state observed before a lifecycle stage starts."""

    repository_root: str
    head_commit: str
    branch: str | None
    dirty_paths: tuple[str, ...] = ()
    input_files: tuple[RepositoryFileObservation, ...] = ()

    @property
    def is_clean(self) -> bool:
        """Return whether Git status reported no changed paths."""
        return not self.dirty_paths


@dataclass(frozen=True)
class RepositoryInspectionRequest:
    """Application request to inspect repository state for selected inputs."""

    working_directory: Path
    input_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class RepositoryInspectionResult:
    """Typed repository inspection result for orchestration preflight."""

    status: RepositoryInspectionStatus
    snapshot: RepositorySnapshot | None = None
    blockers: tuple[RepositoryInspectionBlocker, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        """Return whether repository state satisfies this inspection slice."""
        return self.status is RepositoryInspectionStatus.READY
