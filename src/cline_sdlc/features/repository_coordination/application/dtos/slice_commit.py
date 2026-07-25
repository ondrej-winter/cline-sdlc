"""DTOs for one explicit atomic implementation-slice commit."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_reconciliation import (
        SliceCommitCandidate,
    )

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_COMMIT_TYPES = frozenset({"build", "chore", "docs", "feat", "fix", "refactor", "test"})


class SliceCommitStatus(StrEnum):
    """Terminal status for one slice commit transaction."""

    COMMITTED = "committed"
    RECOVERY_REQUIRED = "recovery_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SliceCommitBlocker:
    """Actionable reason an atomic slice commit did not complete."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "slice commit blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SliceCommitRequest:
    """Verified candidate and progress-only plan bytes for one local commit."""

    repository_root: Path
    plan_path: str
    current_plan_content: bytes
    updated_plan_content: bytes
    candidate: SliceCommitCandidate
    short_description: str
    commit_type: str = "feat"

    def __post_init__(self) -> None:
        _require_path(self.plan_path)
        if self.plan_path not in self.candidate.paths:
            message = "slice commit candidate paths must include the progress plan"
            raise ValueError(message)
        if not self.current_plan_content or not self.updated_plan_content:
            message = "slice commit requires current and updated plan content"
            raise ValueError(message)
        if self.current_plan_content == self.updated_plan_content:
            message = "slice commit progress update must change the plan"
            raise ValueError(message)
        if self.commit_type not in _ALLOWED_COMMIT_TYPES:
            message = "slice commit type is not allowed"
            raise ValueError(message)
        if not self.short_description.strip() or "\n" in self.short_description:
            message = "slice commit short description must be one non-empty line"
            raise ValueError(message)


@dataclass(frozen=True)
class GitSliceCommitRequest:
    """Exact filesystem and Git effects authorized by the application use case."""

    repository_root: Path
    starting_head: str
    paths: tuple[str, ...]
    plan_path: str
    expected_plan_content: bytes
    updated_plan_content: bytes
    message: str


@dataclass(frozen=True)
class GitSliceCommitObservation:
    """Observed result of the adapter-owned Git transaction."""

    committed: bool
    commit: str | None = None
    committed_paths: tuple[str, ...] = ()
    commit_message: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SliceCommitRecovery:
    """Attributable working-tree state retained after commit failure."""

    task_id: str
    slice_id: str
    slice_start_commit: str
    paths: tuple[str, ...]
    blocker: SliceCommitBlocker


@dataclass(frozen=True)
class SliceCommitResult:
    """Verified commit, attributable recovery, or pre-write blocker."""

    status: SliceCommitStatus
    commit: str | None = None
    recovery: SliceCommitRecovery | None = None
    blocker: SliceCommitBlocker | None = None


def _require_path(raw_path: str) -> None:
    path = PurePosixPath(raw_path)
    if (
        not raw_path.strip()
        or raw_path.startswith(("/", "../"))
        or "\\" in raw_path
        or ".." in path.parts
        or path.as_posix() != raw_path
    ):
        message = "slice commit paths must be normalized repository-relative POSIX paths"
        raise ValueError(message)


def require_commit_hash(value: str) -> None:
    """Require a full lowercase Git object identifier."""
    if _COMMIT_PATTERN.fullmatch(value) is None:
        message = "slice commit hash must be a full lowercase Git object identifier"
        raise ValueError(message)
