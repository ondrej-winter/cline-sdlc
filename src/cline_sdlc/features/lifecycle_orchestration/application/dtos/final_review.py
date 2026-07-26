"""DTOs for fresh final review and bounded remediation classification."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.domain.findings import FindingStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import FinalValidationStatus
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationEvidenceStatus,
    ValidationScope,
)

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.domain.findings import Finding, PlanReviewReadiness
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import FinalValidationResult
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
    from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_FINAL_FINDING_PATTERN = re.compile(r"^FINAL-[0-9]{3,}$")


class FinalReviewStatus(StrEnum):
    """Terminal status for final review and remediation classification."""

    CLEAN = "clean"
    REMEDIATION_REQUIRED = "remediation_required"
    BLOCKED = "blocked"
    FAILED = "failed"


class RemediationStatus(StrEnum):
    """Progress-only status of a bounded remediation record."""

    PENDING = "pending"


@dataclass(frozen=True)
class FinalReviewBlocker:
    """Actionable reason final review could not authorize completion or remediation."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.summary.strip():
            message = "final-review blocker code and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class ApprovedRemediationScope:
    """Accepted requirement context that may authorize a bounded correction."""

    requirement: str
    affected_section: str
    path_scope: tuple[str, ...]
    verification: str

    def __post_init__(self) -> None:
        if not self.requirement.strip() or not self.affected_section.strip() or not self.verification.strip():
            message = "approved remediation scope text fields must not be empty"
            raise ValueError(message)
        if not self.path_scope:
            message = "approved remediation scope requires at least one bounded path"
            raise ValueError(message)
        object.__setattr__(self, "path_scope", _normalized_unique_paths(self.path_scope))


@dataclass(frozen=True)
class RemediationRecord:
    """Progress-only correction authorized by accepted material requirements."""

    finding_id: str
    requirement: str
    path_scope: tuple[str, ...]
    correction: str
    verification: str
    status: RemediationStatus = RemediationStatus.PENDING
    attempt_count: int = 0

    def __post_init__(self) -> None:
        if _FINAL_FINDING_PATTERN.fullmatch(self.finding_id) is None:
            message = "remediation finding IDs must use FINAL- followed by at least three digits"
            raise ValueError(message)
        for value in (self.requirement, self.correction, self.verification):
            if not value.strip():
                message = "remediation record text fields must not be empty"
                raise ValueError(message)
        if not self.path_scope:
            message = "remediation record requires bounded path scope"
            raise ValueError(message)
        object.__setattr__(self, "path_scope", _normalized_unique_paths(self.path_scope))
        if self.attempt_count != 0:
            message = "new remediation records must start with attempt_count zero"
            raise ValueError(message)


@dataclass(frozen=True)
class FinalReviewRequest:
    """Approved artifacts, commit range, and evidence for one fresh final review."""

    approval: InvocationApproval
    specification_path: str
    specification_content: str
    specification_digest: str
    plan_path: str
    plan_content: str
    material_digest: str
    repository_rules: str
    repository_request: RepositoryInspectionRequest
    cline_command: str
    timeout_seconds: float
    start_commit: str
    end_commit: str
    final_validation: FinalValidationResult
    remediation_scopes: tuple[ApprovedRemediationScope, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _validate_final_review_text(self)
        _validate_final_review_identity(self)
        _validate_final_review_evidence(self)

    @property
    def working_directory(self) -> Path:
        """Return the repository working directory for the review session."""
        return self.repository_request.working_directory


@dataclass(frozen=True)
class FinalReviewResult:
    """Validated final findings and any safely classified remediation records."""

    status: FinalReviewStatus
    readiness: PlanReviewReadiness | None = None
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    remediation_records: tuple[RemediationRecord, ...] = field(default_factory=tuple)
    blocker: FinalReviewBlocker | None = None


def finding_is_open(finding: Finding) -> bool:
    """Return whether a final finding still requires disposition."""
    return finding.status is FindingStatus.OPEN


def _validate_final_review_text(request: FinalReviewRequest) -> None:
    values = (
        request.specification_path,
        request.specification_content,
        request.plan_path,
        request.plan_content,
        request.repository_rules,
        request.cline_command,
    )
    if any(not value.strip() for value in values):
        message = "final-review artifact, rule, and command values must not be empty"
        raise ValueError(message)
    if not math.isfinite(request.timeout_seconds) or request.timeout_seconds <= 0:
        message = "final-review timeout must be a finite positive number"
        raise ValueError(message)


def _validate_final_review_identity(request: FinalReviewRequest) -> None:
    if any(
        _DIGEST_PATTERN.fullmatch(digest) is None for digest in (request.specification_digest, request.material_digest)
    ):
        message = "final-review digests must use sha256:<lowercase hexadecimal>"
        raise ValueError(message)
    if any(_COMMIT_PATTERN.fullmatch(commit) is None for commit in (request.start_commit, request.end_commit)):
        message = "final-review commits must be full lowercase Git hashes"
        raise ValueError(message)
    if request.start_commit != request.approval.starting_head or request.start_commit == request.end_commit:
        message = "final-review commit range must cover approved implementation work"
        raise ValueError(message)


def _validate_final_review_evidence(request: FinalReviewRequest) -> None:
    if request.final_validation.status is not FinalValidationStatus.COMPLETED:
        message = "final review requires completed broad validation"
        raise ValueError(message)
    if request.final_validation.run_id != request.approval.run_id:
        message = "final review validation must belong to the invocation approval"
        raise ValueError(message)
    if request.final_validation.commit_range != (request.start_commit, request.end_commit):
        message = "final review validation must cover the reviewed commit range"
        raise ValueError(message)
    if not request.final_validation.evidence or any(
        evidence.scope is not ValidationScope.BROAD
        or evidence.status is not ValidationEvidenceStatus.PASSED
        or evidence.exit_code != 0
        or evidence.recorded_at is None
        for evidence in request.final_validation.evidence
    ):
        message = "final review requires complete passing broad-validation evidence"
        raise ValueError(message)
    if request.remediation_scopes and not request.approval.remediation_envelope_applicable:
        message = "approved remediation scopes require an applicable invocation remediation envelope"
        raise ValueError(message)
    sections = tuple(scope.affected_section for scope in request.remediation_scopes)
    if len(set(sections)) != len(sections):
        message = "approved remediation sections must be unique"
        raise ValueError(message)


def _normalized_unique_paths(raw_paths: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_path in raw_paths:
        path = PurePosixPath(raw_path)
        if (
            not raw_path.strip()
            or raw_path.startswith(("/", "../"))
            or "\\" in raw_path
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            message = "remediation paths must be normalized repository-relative paths"
            raise ValueError(message)
        normalized.append(path.as_posix())
    if len(set(normalized)) != len(normalized):
        message = "remediation paths must be unique"
        raise ValueError(message)
    return tuple(normalized)
