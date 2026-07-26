"""DTOs for the progress-only plan finalization transaction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class FinalizationStatus(StrEnum):
    """Terminal status of plan finalization or complete-plan verification."""

    FINALIZED = "finalized"
    ALREADY_COMPLETE = "already_complete"
    RECOVERY_REQUIRED = "recovery_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class FinalizationBlocker:
    """Actionable reason finalization could not establish completion."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "finalization blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class RepositoryFinalizationRequest:
    """Exact approved plan bytes and repository identity for finalization."""

    repository_root: Path
    plan_path: str
    current_plan_content: bytes
    approval: InvocationApproval
    completed_plan_content: bytes | None = None
    recovery_plan_content: bytes | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_path(self.plan_path)
        if not self.current_plan_content:
            message = "finalization requires current plan content"
            raise ValueError(message)
        supplied = (self.completed_plan_content, self.recovery_plan_content, self.completed_at)
        if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
            message = "new finalization requires completed bytes, recovery bytes, and completion time together"
            raise ValueError(message)


@dataclass(frozen=True)
class GitFinalizationRequest:
    """Exact filesystem and Git effects authorized for finalization."""

    repository_root: Path
    starting_head: str
    plan_path: str
    expected_plan_content: bytes
    completed_plan_content: bytes
    recovery_plan_content: bytes
    message: str


@dataclass(frozen=True)
class GitFinalizationObservation:
    """Observed finalization commit or recoverable adapter failure."""

    committed: bool
    commit: str | None = None
    committed_paths: tuple[str, ...] = ()
    commit_message: str | None = None
    recovery_written: bool = False
    error: str | None = None


@dataclass(frozen=True)
class FinalizationCommitCandidate:
    """Reachable commit claiming ownership of plan finalization."""

    commit: str
    work_id: str
    material_digest: str
    plan_content: bytes
    parent_plan_content: bytes | None


@dataclass(frozen=True)
class FinalizationHistoryRequest:
    """Read-only history request for one completed plan."""

    repository_root: Path
    plan_path: str


@dataclass(frozen=True)
class FinalizationHistoryObservation:
    """Current HEAD, dirtiness, and reachable finalization claims."""

    head_commit: str
    dirty_paths: tuple[str, ...]
    candidates: tuple[FinalizationCommitCandidate, ...] = ()


@dataclass(frozen=True)
class FinalizationResult:
    """Verified finalization, complete no-op, recovery state, or blocker."""

    status: FinalizationStatus
    commit: str | None = None
    blocker: FinalizationBlocker | None = None


def require_commit_hash(value: str) -> None:
    """Require a full lowercase Git object identifier."""
    if _COMMIT_PATTERN.fullmatch(value) is None:
        message = "finalization commit must be a full lowercase Git object identifier"
        raise ValueError(message)


def _require_path(raw_path: str) -> None:
    path = PurePosixPath(raw_path)
    if (
        not raw_path.strip()
        or raw_path.startswith(("/", "../"))
        or "\\" in raw_path
        or ".." in path.parts
        or path.as_posix() != raw_path
    ):
        message = "finalization plan path must be normalized repository-relative POSIX"
        raise ValueError(message)
