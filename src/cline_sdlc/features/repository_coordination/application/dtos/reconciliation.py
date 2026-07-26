"""DTOs for implementation-plan Git reconciliation and invocation approval."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path  # noqa: TC003 - Runtime dataclass boundary intentionally exposes Path.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import (
        PlanBlocker,
        PlanPhase,
        RemediationRecord,
        ValidationEvidence,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
        SelectedSlice,
        SliceSelectionRequest,
    )

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class PlanReconciliationStatus(StrEnum):
    """Terminal status for implementation-plan reconciliation."""

    AUTHORIZED = "authorized"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class InvocationApproval:
    """Immutable approval for one exact plan implementation invocation."""

    run_id: str
    profile: str
    starting_head: str
    approved_at: datetime
    specification_digest: str
    material_digest: str
    remediation_envelope_applicable: bool

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            message = "invocation approval run_id must not be empty"
            raise ValueError(message)
        if self.profile != "balanced":
            message = "invocation approval profile must be balanced"
            raise ValueError(message)
        if _COMMIT_PATTERN.fullmatch(self.starting_head) is None:
            message = "invocation approval starting_head must be a full lowercase Git commit hash"
            raise ValueError(message)
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() != UTC.utcoffset(self.approved_at):
            message = "invocation approval approved_at must be UTC"
            raise ValueError(message)
        for value in (self.specification_digest, self.material_digest):
            if _DIGEST_PATTERN.fullmatch(value) is None:
                message = "invocation approval digests must use sha256:<lowercase hexadecimal>"
                raise ValueError(message)


@dataclass(frozen=True)
class PlanArtifactEvidence:
    """Validated current or committed plan artifact evidence."""

    work_id: str
    specification_path: str
    specification_digest: str
    material_digest: str
    phase: PlanPhase
    completed_slice_ids: tuple[str, ...]
    current_task: str | None
    current_slice: str | None
    slice_start_commit: str | None
    partial_slice_paths: tuple[str, ...]
    remediation_records: tuple[RemediationRecord, ...]
    validation_evidence: tuple[ValidationEvidence, ...]
    blocker: PlanBlocker | None
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class PlanArtifactInspection:
    """Artifact evidence or a safe parsing/digest failure."""

    evidence: PlanArtifactEvidence | None = None
    error: str | None = None


@dataclass(frozen=True)
class OwningCommitCandidate:
    """Reachable commit claiming ownership of one completed slice."""

    commit: str
    slice_id: str
    work_id: str
    slice_kind: str
    material_digest: str
    plan_content: bytes
    parent_plan_content: bytes | None


@dataclass(frozen=True)
class PlanHistoryObservation:
    """Current repository and reachable ownership evidence."""

    head_commit: str
    dirty_paths: tuple[str, ...]
    owning_candidates: tuple[OwningCommitCandidate, ...] = ()


@dataclass(frozen=True)
class PlanHistoryRequest:
    """Git history observation request for one accepted plan."""

    repository_root: Path
    plan_path: str
    completed_slice_ids: tuple[str, ...]


@dataclass(frozen=True)
class PlanReconciliationRequest:
    """Inputs required to authorize one exact implementation invocation."""

    repository_root: Path
    run_id: str
    approved_at: datetime
    plan_path: str
    plan_content: bytes
    specification_path: str
    specification_content: bytes
    selection_request: SliceSelectionRequest
    remediation_envelope_applicable: bool = True


@dataclass(frozen=True)
class PlanReconciliationBlocker:
    """Actionable reason implementation authorization was withheld."""

    code: str
    summary: str
    evidence: str | None = None


@dataclass(frozen=True)
class PlanReconciliationResult:
    """Authorized selected work, verified completion, or a blocker."""

    status: PlanReconciliationStatus
    approval: InvocationApproval | None = None
    selection: SelectedSlice | None = None
    blocker: PlanReconciliationBlocker | None = None
    owning_commits: tuple[tuple[str, str], ...] = field(default_factory=tuple)
