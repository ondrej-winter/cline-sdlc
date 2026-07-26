"""DTOs for repository-wide validation after planned slice commits."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import ValidationEvidence
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class FinalValidationStatus(StrEnum):
    """Terminal status for final repository-wide validation."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class FinalValidationBlocker:
    """Actionable reason final validation did not complete."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "final-validation blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class FinalValidationRequest:
    """Approved commit range and runtime boundary for broad validation."""

    approval: InvocationApproval
    specification_digest: str
    material_digest: str
    start_commit: str
    end_commit: str
    working_directory: Path
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        for commit in (self.start_commit, self.end_commit):
            if _COMMIT_PATTERN.fullmatch(commit) is None:
                message = "final-validation commits must be full lowercase Git hashes"
                raise ValueError(message)
        if self.start_commit != self.approval.starting_head:
            message = "final-validation range must start at the approval starting HEAD"
            raise ValueError(message)
        if self.start_commit == self.end_commit:
            message = "final-validation commit range must include committed implementation work"
            raise ValueError(message)
        for digest in (self.specification_digest, self.material_digest):
            if _DIGEST_PATTERN.fullmatch(digest) is None:
                message = "final-validation digests must use sha256:<lowercase hexadecimal>"
                raise ValueError(message)
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            message = "final-validation timeout must be a finite positive number of seconds"
            raise ValueError(message)


@dataclass(frozen=True)
class FinalValidationResult:
    """Broad evidence tied to one immutable approval and commit range."""

    status: FinalValidationStatus
    run_id: str
    commit_range: tuple[str, str]
    evidence: tuple[ValidationEvidence, ...] = field(default_factory=tuple)
    blocker: FinalValidationBlocker | None = None
