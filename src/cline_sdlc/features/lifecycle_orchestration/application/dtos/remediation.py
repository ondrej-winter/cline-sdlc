"""DTOs for bounded final-review remediation and confirmation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
    FinalReviewStatus,
    RemediationRecord,
    RemediationStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_review import (
        FinalReviewResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import FinalValidationResult
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval


class RemediationExecutionStatus(StrEnum):
    """Terminal status for the complete remediation transaction group."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class RemediationBlocker:
    """Actionable reason remediation could not authorize finalization."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "remediation blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class RemediationRequest:
    """Immutable approval and Task 5.2 findings authorized for one attempt each."""

    approval: InvocationApproval
    specification_digest: str
    material_digest: str
    initial_review: FinalReviewResult

    def __post_init__(self) -> None:
        if not self.approval.remediation_envelope_applicable:
            message = "remediation requires an applicable invocation approval envelope"
            raise ValueError(message)
        if self.specification_digest != self.approval.specification_digest:
            message = "remediation specification digest must match invocation approval"
            raise ValueError(message)
        if self.material_digest != self.approval.material_digest:
            message = "remediation material digest must match invocation approval"
            raise ValueError(message)
        if self.initial_review.status is not FinalReviewStatus.REMEDIATION_REQUIRED:
            message = "remediation requires a Task 5.2 remediation-required result"
            raise ValueError(message)
        records = self.initial_review.remediation_records
        if not records or any(
            record.status is not RemediationStatus.PENDING or record.attempt_count != 0 for record in records
        ):
            message = "remediation requires non-empty pending records with no prior attempt"
            raise ValueError(message)
        ids = tuple(record.finding_id for record in records)
        if len(set(ids)) != len(ids):
            message = "remediation finding IDs must be unique"
            raise ValueError(message)


@dataclass(frozen=True)
class RemediationResult:
    """Committed corrections, latest broad evidence, and confirmation outcome."""

    status: RemediationExecutionStatus
    remediation_records: tuple[RemediationRecord, ...] = field(default_factory=tuple)
    commits: tuple[str, ...] = field(default_factory=tuple)
    final_validation: FinalValidationResult | None = None
    confirmation_review: FinalReviewResult | None = None
    blocker: RemediationBlocker | None = None
