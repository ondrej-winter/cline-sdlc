"""DTOs for serial implementation-plan transaction orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SelectedSlice
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval


class PlanImplementationStatus(StrEnum):
    """Terminal status for the serial implementation loop."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True)
class PlanImplementationBlocker:
    """Actionable reason the serial implementation loop stopped."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "plan implementation blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class PlanImplementationRequest:
    """One approved invocation and its initially reconciled slice."""

    approval: InvocationApproval
    initial_selection: SelectedSlice


@dataclass(frozen=True)
class PlanImplementationResult:
    """Serially committed slices or the first terminal transaction failure."""

    status: PlanImplementationStatus
    approval: InvocationApproval
    completed_slice_ids: tuple[str, ...] = field(default_factory=tuple)
    commits: tuple[str, ...] = field(default_factory=tuple)
    blocker: PlanImplementationBlocker | None = None
