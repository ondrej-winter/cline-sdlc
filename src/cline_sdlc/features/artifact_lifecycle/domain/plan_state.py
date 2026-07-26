"""Plan lifecycle state schema values."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath

PLAN_STATE_SCHEMA_VERSION = 1
DIGEST_SCHEMA_VERSION = 1
MAX_REVIEW_ITERATION = 3

_KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STABLE_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class PlanPhase(StrEnum):
    """Allowed implementation-plan lifecycle phases."""

    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    READY = "ready"
    IMPLEMENTING = "implementing"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class PlanProfile(StrEnum):
    """Allowed operation profile for MVP plan state."""

    BALANCED = "balanced"


class ReviewReadiness(StrEnum):
    """Allowed plan-review readiness values."""

    NOT_REVIEWED = "not_reviewed"
    CHANGES_REQUIRED = "changes_required"
    READY = "ready"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PlanBlocker:
    """Structured blocker attached to blocked plan state."""

    code: str
    summary: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.code, field_name="blocker code")
        _require_non_empty_text(self.summary, field_name="blocker summary")


@dataclass(frozen=True)
class ValidationEvidence:
    """Structured validation evidence recorded in plan progress state."""

    slice_id: str
    command: str
    result: str
    exit_code: int | None
    recorded_at: datetime

    def __post_init__(self) -> None:
        _require_stable_identifier(self.slice_id, field_name="validation evidence slice_id")
        _require_non_empty_text(self.command, field_name="validation evidence command")
        _require_non_empty_text(self.result, field_name="validation evidence result")
        _require_utc_datetime(self.recorded_at, field_name="validation evidence recorded_at")


@dataclass(frozen=True)
class RemediationRecord:
    """Progress-only final-review correction state."""

    finding_id: str
    requirement: str
    path_scope: tuple[str, ...]
    correction: str
    verification: str
    status: str
    attempt_count: int

    def __post_init__(self) -> None:
        if not re.fullmatch(r"FINAL-[0-9]{3,}", self.finding_id):
            message = "remediation finding_id must use FINAL- followed by at least three digits"
            raise ValueError(message)
        for field_name, value in (
            ("requirement", self.requirement),
            ("correction", self.correction),
            ("verification", self.verification),
        ):
            _require_non_empty_text(value, field_name=f"remediation {field_name}")
        object.__setattr__(self, "path_scope", _normalized_unique_paths(self.path_scope))
        if not self.path_scope:
            message = "remediation path_scope must not be empty"
            raise ValueError(message)
        expected_attempts = {"pending": 0, "completed": 1}
        if self.status not in expected_attempts or self.attempt_count != expected_attempts[self.status]:
            message = "remediation status and attempt_count must describe zero or one implementation attempt"
            raise ValueError(message)


@dataclass(frozen=True)
class PlanState:
    """Validated version-1 implementation-plan lifecycle state."""

    work_id: str
    phase: PlanPhase
    specification: str
    specification_digest: str
    plan_revision: int
    review_iteration: int
    review_readiness: ReviewReadiness
    material_digest: str
    created_at: datetime
    updated_at: datetime
    schema_version: int = PLAN_STATE_SCHEMA_VERSION
    profile: PlanProfile = PlanProfile.BALANCED
    digest_schema_version: int = DIGEST_SCHEMA_VERSION
    current_task: str | None = None
    current_slice: str | None = None
    slice_start_commit: str | None = None
    partial_slice_paths: tuple[str, ...] = field(default_factory=tuple)
    completed_slices: tuple[str, ...] = field(default_factory=tuple)
    remediation_records: tuple[RemediationRecord, ...] = field(default_factory=tuple)
    validation_evidence: tuple[ValidationEvidence, ...] = field(default_factory=tuple)
    blocker: PlanBlocker | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.schema_version != PLAN_STATE_SCHEMA_VERSION:
            message = "unsupported plan state schema version"
            raise ValueError(message)
        if self.digest_schema_version != DIGEST_SCHEMA_VERSION:
            message = "unsupported plan state digest schema version"
            raise ValueError(message)
        _require_kebab_case_identifier(self.work_id, field_name="work_id")
        _require_repository_path(self.specification, field_name="specification")
        _require_digest(self.specification_digest, field_name="specification_digest")
        _require_digest(self.material_digest, field_name="material_digest")
        _require_positive_int(self.plan_revision, field_name="plan_revision")
        _require_review_iteration(self.review_iteration)
        _require_utc_datetime(self.created_at, field_name="created_at")
        _require_utc_datetime(self.updated_at, field_name="updated_at")
        if self.completed_at is not None:
            _require_utc_datetime(self.completed_at, field_name="completed_at")
        if self.current_task is not None:
            _require_stable_identifier(self.current_task, field_name="current_task")
        if self.current_slice is not None:
            _require_stable_identifier(self.current_slice, field_name="current_slice")
        if self.slice_start_commit is not None and not _GIT_COMMIT_PATTERN.fullmatch(self.slice_start_commit):
            message = "slice_start_commit must be a full lowercase Git commit hash"
            raise ValueError(message)

        object.__setattr__(self, "partial_slice_paths", _normalized_unique_paths(self.partial_slice_paths))
        object.__setattr__(self, "completed_slices", _unique_slice_ids(self.completed_slices))
        remediation_ids = tuple(record.finding_id for record in self.remediation_records)
        if len(set(remediation_ids)) != len(remediation_ids):
            message = "remediation finding IDs must be unique"
            raise ValueError(message)
        self._validate_phase_invariants()

    def transition_to(self, next_phase: PlanPhase) -> None:
        """Validate whether this state may transition to the next phase."""
        if (self.phase, next_phase) not in _ALLOWED_PHASE_TRANSITIONS:
            message = f"invalid plan phase transition: {self.phase.value} -> {next_phase.value}"
            raise ValueError(message)

    @property
    def has_active_slice(self) -> bool:
        """Return whether the state records an active or recoverable slice."""
        return self.current_task is not None or self.current_slice is not None or self.slice_start_commit is not None

    def _validate_phase_invariants(self) -> None:
        active_fields = (self.current_task, self.current_slice, self.slice_start_commit)
        if any(value is not None for value in active_fields) and not all(value is not None for value in active_fields):
            message = "current_task, current_slice, and slice_start_commit must be set together"
            raise ValueError(message)
        if self.phase not in {PlanPhase.IMPLEMENTING, PlanPhase.BLOCKED} and self.has_active_slice:
            message = "active slice fields are only valid while implementing or blocked"
            raise ValueError(message)
        # An implementing plan may be between atomic slices. Active fields are
        # required only while a slice has attributable uncommitted work.
        if self.phase is PlanPhase.BLOCKED and self.blocker is None:
            message = "blocked state must include a blocker"
            raise ValueError(message)
        if self.phase is not PlanPhase.BLOCKED and self.blocker is not None:
            message = "only blocked state may include a blocker"
            raise ValueError(message)
        if self.phase is PlanPhase.COMPLETE and self.completed_at is None:
            message = "complete state must include completed_at"
            raise ValueError(message)
        if self.phase is not PlanPhase.COMPLETE and self.completed_at is not None:
            message = "completed_at is only valid in complete state"
            raise ValueError(message)
        if self.phase is PlanPhase.READY and self.review_readiness is not ReviewReadiness.READY:
            message = "ready state must have ready review_readiness"
            raise ValueError(message)
        if self.phase is PlanPhase.DRAFTING and self.review_readiness is not ReviewReadiness.NOT_REVIEWED:
            message = "drafting state must not be reviewed"
            raise ValueError(message)


_ALLOWED_PHASE_TRANSITIONS = frozenset(
    {
        (PlanPhase.DRAFTING, PlanPhase.REVIEWING),
        (PlanPhase.REVIEWING, PlanPhase.READY),
        (PlanPhase.REVIEWING, PlanPhase.BLOCKED),
        (PlanPhase.READY, PlanPhase.IMPLEMENTING),
        (PlanPhase.IMPLEMENTING, PlanPhase.BLOCKED),
        (PlanPhase.BLOCKED, PlanPhase.REVIEWING),
        (PlanPhase.BLOCKED, PlanPhase.IMPLEMENTING),
        (PlanPhase.IMPLEMENTING, PlanPhase.COMPLETE),
    },
)


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)


def _require_kebab_case_identifier(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or _KEBAB_CASE_PATTERN.fullmatch(value) is None:
        message = f"{field_name} must be a non-empty kebab-case identifier"
        raise ValueError(message)


def _require_stable_identifier(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or _STABLE_IDENTIFIER_PATTERN.fullmatch(value) is None:
        message = f"{field_name} must be a non-empty stable identifier"
        raise ValueError(message)


def _require_digest(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_DIGEST_PATTERN.fullmatch(value) is None:
        message = f"{field_name} must use sha256:<lowercase hexadecimal>"
        raise ValueError(message)


def _require_positive_int(value: int, *, field_name: str) -> None:
    if not isinstance(value, int) or value < 1:
        message = f"{field_name} must be a positive integer"
        raise ValueError(message)


def _require_review_iteration(value: int) -> None:
    if not isinstance(value, int) or not 1 <= value <= MAX_REVIEW_ITERATION:
        message = "review_iteration must be between 1 and 3"
        raise ValueError(message)


def _require_utc_datetime(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        message = f"{field_name} must be a UTC RFC 3339 timestamp"
        raise ValueError(message)


def _normalized_unique_paths(raw_paths: tuple[str, ...]) -> tuple[str, ...]:
    normalized_paths = tuple(_require_repository_path(path, field_name="partial_slice_paths") for path in raw_paths)
    if len(set(normalized_paths)) != len(normalized_paths):
        message = "partial_slice_paths must be unique"
        raise ValueError(message)
    return normalized_paths


def _require_repository_path(raw_path: str, *, field_name: str) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)
    if raw_path.startswith("/") or "\\" in raw_path:
        message = f"{field_name} must be a normalized repository-relative POSIX path"
        raise ValueError(message)
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        message = f"{field_name} must not contain traversal or empty segments"
        raise ValueError(message)
    if raw_path.endswith("/"):
        return f"{path.as_posix()}/"
    return path.as_posix()


def _unique_slice_ids(raw_values: tuple[str, ...]) -> tuple[str, ...]:
    values = tuple(raw_values)
    for value in values:
        _require_stable_identifier(value, field_name="completed_slices")
    if len(set(values)) != len(values):
        message = "completed_slices must be unique"
        raise ValueError(message)
    return values
