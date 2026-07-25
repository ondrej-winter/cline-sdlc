"""DTOs for pure implementation-plan slice selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

_STABLE_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class SliceSelectionStatus(StrEnum):
    """Terminal status for selecting implementation work."""

    SELECTED = "selected"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PlanSliceDefinition:
    """Stable slice definition in plan declaration order."""

    slice_id: str
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_stable_identifier(self.slice_id, field_name="slice_id")
        for dependency in self.dependencies:
            _require_stable_identifier(dependency, field_name="slice dependency")


@dataclass(frozen=True)
class PlanTaskDefinition:
    """Stable task definition containing its ordered implementation slices."""

    task_id: str
    slices: tuple[PlanSliceDefinition, ...]

    def __post_init__(self) -> None:
        _require_stable_identifier(self.task_id, field_name="task_id")


@dataclass(frozen=True)
class SliceCompletionEvidence:
    """Reconciled progress evidence for one declared slice."""

    slice_id: str
    completed: bool

    def __post_init__(self) -> None:
        _require_stable_identifier(self.slice_id, field_name="completion evidence slice_id")


@dataclass(frozen=True)
class PartialSliceProgress:
    """Recorded uncommitted slice progress eligible for exclusive resumption."""

    task_id: str
    slice_id: str
    paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_stable_identifier(self.task_id, field_name="partial task_id")
        _require_stable_identifier(self.slice_id, field_name="partial slice_id")


@dataclass(frozen=True)
class SliceSelectionRequest:
    """Pure selection input built from parsed plan definitions and progress."""

    tasks: tuple[PlanTaskDefinition, ...]
    completed_slice_ids: tuple[str, ...] = ()
    completion_evidence: tuple[SliceCompletionEvidence, ...] = ()
    partial_slice: PartialSliceProgress | None = None

    def __post_init__(self) -> None:
        for slice_id in self.completed_slice_ids:
            _require_stable_identifier(slice_id, field_name="completed slice_id")


@dataclass(frozen=True)
class SelectedSlice:
    """One dependency-ready slice selected in plan declaration order."""

    task_id: str
    slice_id: str
    resuming_partial: bool


@dataclass(frozen=True)
class SliceSelectionBlocker:
    """Actionable reason reconciled progress could not select work safely."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "slice-selection blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "slice-selection blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SliceSelectionResult:
    """Selected work, verified completion, or a fail-closed blocker."""

    status: SliceSelectionStatus
    selection: SelectedSlice | None = None
    blocker: SliceSelectionBlocker | None = None
    completed_slice_ids: tuple[str, ...] = field(default_factory=tuple)


def _require_stable_identifier(value: str, *, field_name: str) -> None:
    if _STABLE_IDENTIFIER_PATTERN.fullmatch(value) is None:
        message = f"{field_name} must be a non-empty stable identifier"
        raise ValueError(message)
