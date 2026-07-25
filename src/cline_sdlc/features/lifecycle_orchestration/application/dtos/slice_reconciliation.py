"""DTOs for independently reconciling one executed implementation slice."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import SliceExecutionResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SelectedSlice
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import ValidationEvidence
    from cline_sdlc.features.operation_policy.domain.policy import OperationDecision
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
    from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class SliceReconciliationStatus(StrEnum):
    """Terminal status for independent slice reconciliation."""

    COMMIT_CANDIDATE = "commit_candidate"
    RECOVERY_REQUIRED = "recovery_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SliceReconciliationBlocker:
    """Actionable reason a slice is not eligible for commit."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "slice-reconciliation blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SliceCommitCandidate:
    """Exact verified paths and evidence eligible for the later commit transaction."""

    work_id: str
    task_id: str
    slice_id: str
    starting_head: str
    material_digest: str
    paths: tuple[str, ...]
    validation_evidence: tuple[ValidationEvidence, ...]
    operation_decisions: tuple[OperationDecision, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PartialSliceRecovery:
    """Attributable uncommitted state retained for safe recovery."""

    task_id: str
    slice_id: str
    slice_start_commit: str
    paths: tuple[str, ...]
    blocker: SliceReconciliationBlocker


@dataclass(frozen=True)
class SliceReconciliationRequest:
    """Approved execution evidence and repository boundary for one slice."""

    work_id: str
    approval: InvocationApproval
    selection: SelectedSlice
    slice_start_commit: str
    specification_digest: str
    material_digest: str
    plan_path: str
    expected_paths: tuple[str, ...]
    execution: SliceExecutionResult
    repository_request: RepositoryInspectionRequest

    def __post_init__(self) -> None:
        if not self.work_id.strip():
            message = "slice reconciliation work_id must not be empty"
            raise ValueError(message)
        if _COMMIT_PATTERN.fullmatch(self.slice_start_commit) is None:
            message = "slice reconciliation starting HEAD must be a full lowercase Git commit hash"
            raise ValueError(message)
        for digest in (self.specification_digest, self.material_digest):
            if _DIGEST_PATTERN.fullmatch(digest) is None:
                message = "slice reconciliation digests must use sha256:<lowercase hexadecimal>"
                raise ValueError(message)
        _require_normalized_path(self.plan_path)
        if not self.expected_paths:
            message = "slice reconciliation requires an explicit expected path scope"
            raise ValueError(message)
        if len(set(self.expected_paths)) != len(self.expected_paths):
            message = "slice reconciliation expected paths must be unique"
            raise ValueError(message)
        for path in self.expected_paths:
            _require_normalized_path(path)
        if self.plan_path not in self.expected_paths:
            message = "slice reconciliation expected paths must include the progress plan"
            raise ValueError(message)


@dataclass(frozen=True)
class SliceReconciliationResult:
    """Verified commit candidate, attributable recovery, or pre-write blocker."""

    status: SliceReconciliationStatus
    commit_candidate: SliceCommitCandidate | None = None
    recovery: PartialSliceRecovery | None = None
    blocker: SliceReconciliationBlocker | None = None


def _require_normalized_path(raw_path: str) -> None:
    path = PurePosixPath(raw_path)
    if (
        not raw_path.strip()
        or raw_path.startswith(("/", "../"))
        or "\\" in raw_path
        or ".." in path.parts
        or path.as_posix() != raw_path
    ):
        message = "slice reconciliation paths must be normalized repository-relative POSIX paths"
        raise ValueError(message)
