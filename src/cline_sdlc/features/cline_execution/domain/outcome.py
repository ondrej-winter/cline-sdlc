"""Session outcome schema values for supervised Cline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath

SESSION_OUTCOME_SCHEMA_VERSION = 1


class SessionRole(StrEnum):
    """Allowed bounded Cline session responsibilities."""

    IDEA_REFINER = "idea_refiner"
    SPEC_AUTHOR = "spec_author"
    PLAN_AUTHOR = "plan_author"
    PLAN_REVIEWER = "plan_reviewer"
    IMPLEMENTATION = "implementation"
    REMEDIATION = "remediation"
    FINAL_REVIEWER = "final_reviewer"


class SessionStatus(StrEnum):
    """Allowed machine-readable session statuses."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    APPROVAL_REQUIRED = "approval_required"
    FAILED = "failed"
    INVALID_OUTPUT = "invalid_output"


class SessionValidationResult(StrEnum):
    """Allowed validation evidence outcomes reported by a session."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class SessionValidationEvidence:
    """Validation command evidence reported by a bounded session."""

    command: str
    result: SessionValidationResult
    exit_code: int | None

    def __post_init__(self) -> None:
        if not self.command.strip():
            message = "validation command must not be empty"
            raise ValueError(message)
        if self.result is SessionValidationResult.NOT_RUN and self.exit_code is not None:
            message = "not-run validation evidence must not include an exit code"
            raise ValueError(message)
        if self.result is not SessionValidationResult.NOT_RUN and self.exit_code is None:
            message = "executed validation evidence must include an exit code"
            raise ValueError(message)


@dataclass(frozen=True)
class SessionBlocker:
    """Safe diagnostic explaining why a session did not complete."""

    code: str
    summary: str
    proposed_operation: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SessionOutcome:
    """Validated terminal outcome for one bounded Cline session."""

    session_role: SessionRole
    status: SessionStatus
    reason: str
    schema_version: int = SESSION_OUTCOME_SCHEMA_VERSION
    artifact_paths: tuple[str, ...] = field(default_factory=tuple)
    changed_paths: tuple[str, ...] = field(default_factory=tuple)
    validation: tuple[SessionValidationEvidence, ...] = field(default_factory=tuple)
    finding_ids: tuple[str, ...] = field(default_factory=tuple)
    blocker: SessionBlocker | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != SESSION_OUTCOME_SCHEMA_VERSION:
            message = "unsupported session outcome schema version"
            raise ValueError(message)
        if not self.reason.strip():
            message = "session outcome reason must not be empty"
            raise ValueError(message)

        object.__setattr__(self, "artifact_paths", _normalized_unique_paths(self.artifact_paths))
        object.__setattr__(self, "changed_paths", _normalized_unique_paths(self.changed_paths))
        object.__setattr__(self, "finding_ids", _non_empty_unique_values(self.finding_ids, field_name="finding_ids"))

        if self.session_role in {SessionRole.PLAN_REVIEWER, SessionRole.FINAL_REVIEWER} and self.changed_paths:
            message = "reviewer session outcomes must not report changed paths"
            raise ValueError(message)
        if self.status is SessionStatus.APPROVAL_REQUIRED:
            if self.blocker is None or self.blocker.proposed_operation is None:
                message = "approval-required outcomes must include a proposed operation"
                raise ValueError(message)
        elif self.blocker is not None and self.blocker.proposed_operation is not None:
            message = "only approval-required outcomes may include a proposed operation"
            raise ValueError(message)


def _normalized_unique_paths(raw_paths: tuple[str, ...]) -> tuple[str, ...]:
    normalized_paths = tuple(_normalize_repository_path(path) for path in raw_paths)
    if len(set(normalized_paths)) != len(normalized_paths):
        message = "session outcome paths must be unique"
        raise ValueError(message)
    return normalized_paths


def _normalize_repository_path(raw_path: str) -> str:
    if not raw_path.strip():
        message = "session outcome paths must not be empty"
        raise ValueError(message)
    if raw_path.startswith("/") or "\\" in raw_path:
        message = "session outcome paths must be normalized repository-relative POSIX paths"
        raise ValueError(message)
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        message = "session outcome paths must not contain traversal or empty segments"
        raise ValueError(message)
    return path.as_posix()


def _non_empty_unique_values(raw_values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    values = tuple(value.strip() for value in raw_values)
    if any(not value for value in values):
        message = f"{field_name} must not contain empty values"
        raise ValueError(message)
    if len(set(values)) != len(values):
        message = f"{field_name} must be unique"
        raise ValueError(message)
    return values
