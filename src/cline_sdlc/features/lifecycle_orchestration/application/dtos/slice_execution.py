"""DTOs for executing one approved implementation-plan slice."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import (
    Path,
    PurePosixPath,
)
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.domain.outcome import SessionRole
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import ValidationScope

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
        SessionAttemptResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import SelectedSlice
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
        ValidationCommandCandidate,
        ValidationEvidence,
    )
    from cline_sdlc.features.operation_policy.application.dtos.operation import ClassifyOperationRequest
    from cline_sdlc.features.operation_policy.domain.policy import OperationDecision
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
    from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest


class SliceExecutionStatus(StrEnum):
    """Terminal status for one bounded slice-execution transaction."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class SlicePlanActStatus(StrEnum):
    """Orchestrator-owned classification of implementation Plan/Act readiness."""

    NEEDS_USER_INPUT = "needs_user_input"
    READY_TO_ACT = "ready_to_act"
    UNPROVEN = "unproven"


@dataclass(frozen=True)
class SliceExecutionBlocker:
    """Actionable reason a slice did not reach focused verification."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "slice-execution blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SlicePlanActMediation:
    """Session-bound evidence for implementation Plan/Act mediation.

    The DTO intentionally models only orchestrator-approved mediation evidence.
    Unproven or ambiguous SDK support must remain blocked rather than inferred
    from ordinary assistant prose, SDK diagnostics, or terminal output.
    """

    status: SlicePlanActStatus
    summary: str
    run_id: str
    task_id: str
    slice_id: str
    specification_digest: str
    material_digest: str
    operation_policy: str
    diagnostic_reference: str | None = None

    def __post_init__(self) -> None:
        required_values = (
            self.summary,
            self.run_id,
            self.task_id,
            self.slice_id,
            self.specification_digest,
            self.material_digest,
            self.operation_policy,
        )
        if any(not value.strip() for value in required_values):
            message = "Plan/Act mediation evidence fields must not be empty"
            raise ValueError(message)
        if self.diagnostic_reference is not None and not self.diagnostic_reference.strip():
            message = "Plan/Act diagnostic reference must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SliceExecutionRequest:
    """Approved context and boundaries for exactly one implementation slice."""

    approval: InvocationApproval
    selection: SelectedSlice
    specification_path: str
    specification_content: str
    specification_digest: str
    plan_path: str
    plan_content: str
    material_digest: str
    repository_request: RepositoryInspectionRequest
    cline_command: str
    timeout_seconds: float
    focused_validation_commands: tuple[ValidationCommandCandidate, ...]
    expected_paths: tuple[str, ...] = ()
    operations: tuple[ClassifyOperationRequest, ...] = ()
    session_role: SessionRole = SessionRole.IMPLEMENTATION
    plan_act_mediation: SlicePlanActMediation | None = None

    def __post_init__(self) -> None:  # noqa: C901 - Boundary DTO validates each independent input invariant.
        if not self.specification_path.strip() or not self.plan_path.strip():
            message = "slice execution artifact paths must not be empty"
            raise ValueError(message)
        if not self.specification_content.strip() or not self.plan_content.strip():
            message = "slice execution requires accepted specification and plan content"
            raise ValueError(message)
        if not self.cline_command.strip():
            message = "slice execution Cline command must not be empty"
            raise ValueError(message)
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            message = "slice execution timeout must be a finite positive number"
            raise ValueError(message)
        if not self.focused_validation_commands:
            message = "slice execution requires at least one focused validation command"
            raise ValueError(message)
        if any(candidate.scope is not ValidationScope.FOCUSED for candidate in self.focused_validation_commands):
            message = "slice execution accepts focused validation commands only"
            raise ValueError(message)
        if self.session_role not in {SessionRole.IMPLEMENTATION, SessionRole.REMEDIATION}:
            message = "slice execution supports implementation and remediation sessions only"
            raise ValueError(message)
        if len(set(self.expected_paths)) != len(self.expected_paths):
            message = "slice execution expected paths must be unique"
            raise ValueError(message)
        for expected_path in self.expected_paths:
            path = PurePosixPath(expected_path)
            if (
                not expected_path.strip()
                or expected_path.startswith(("/", "../"))
                or "\\" in expected_path
                or ".." in path.parts
            ):
                message = "slice execution expected paths must be normalized repository-relative paths"
                raise ValueError(message)

    @property
    def working_directory(self) -> Path:
        """Return the repository working directory used by session and validation ports."""
        return self.repository_request.working_directory


@dataclass(frozen=True)
class SliceExecutionResult:
    """Session, policy, and focused-validation evidence for one slice."""

    status: SliceExecutionStatus
    session_attempts: tuple[SessionAttemptResult, ...] = field(default_factory=tuple)
    operation_decisions: tuple[OperationDecision, ...] = field(default_factory=tuple)
    validation_evidence: tuple[ValidationEvidence, ...] = field(default_factory=tuple)
    changed_paths: tuple[str, ...] = field(default_factory=tuple)
    repair_attempts: int = 0
    blocker: SliceExecutionBlocker | None = None

    @property
    def completed(self) -> bool:
        """Return whether the slice session and independent focused validation completed."""
        return self.status is SliceExecutionStatus.COMPLETED
