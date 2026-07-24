"""DTOs for validation command discovery and evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import (
    Path,
    PurePosixPath,
)


class ValidationScope(StrEnum):
    """Supported validation command scopes."""

    FOCUSED = "focused"
    BROAD = "broad"


class ValidationCommandSource(StrEnum):
    """Where a validation command candidate came from."""

    EXPLICIT = "explicit"
    DISCOVERED = "discovered"
    DEFAULT = "default"


class ValidationEvidenceStatus(StrEnum):
    """Truthful status for validation evidence."""

    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ValidationCommandRunStatus(StrEnum):
    """Observable status returned by a validation command runner."""

    EXITED = "exited"
    TIMED_OUT = "timed_out"
    START_FAILED = "start_failed"


@dataclass(frozen=True)
class ValidationCommand:
    """Structured executable and argument-array validation command."""

    executable: str
    arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.executable.strip():
            message = "validation command executable must not be empty"
            raise ValueError(message)
        if any(not argument.strip() for argument in self.arguments):
            message = "validation command arguments must not contain empty values"
            raise ValueError(message)
        if any("\x00" in value for value in (self.executable, *self.arguments)):
            message = "validation command values must not contain NUL bytes"
            raise ValueError(message)

    @property
    def display(self) -> str:
        """Return a stable command summary for evidence and diagnostics."""
        return " ".join((self.executable, *self.arguments))


@dataclass(frozen=True)
class ValidationCommandCandidate:
    """A command candidate selected for a validation scope."""

    scope: ValidationScope
    command: ValidationCommand
    source: ValidationCommandSource
    reason: str


@dataclass(frozen=True)
class ValidationEvidence:
    """Truthful validation evidence for a command candidate."""

    scope: ValidationScope
    command: ValidationCommand | None
    status: ValidationEvidenceStatus
    summary: str
    exit_code: int | None = None
    recorded_at: datetime | None = None
    policy_rule_id: str | None = None

    def __post_init__(self) -> None:
        if not self.summary.strip():
            message = "validation evidence summary must not be empty"
            raise ValueError(message)
        if self.status is ValidationEvidenceStatus.NOT_RUN and self.exit_code is not None:
            message = "not-run validation evidence must not include an exit code"
            raise ValueError(message)
        if self.status is ValidationEvidenceStatus.PASSED and self.exit_code != 0:
            message = "passed validation evidence must include exit code 0"
            raise ValueError(message)
        if self.status in {ValidationEvidenceStatus.FAILED, ValidationEvidenceStatus.BLOCKED} and self.exit_code == 0:
            message = "failed or blocked validation evidence must not include exit code 0"
            raise ValueError(message)
        if self.recorded_at is not None and (
            self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() != UTC.utcoffset(self.recorded_at)
        ):
            message = "validation evidence recorded_at must be a UTC timestamp"
            raise ValueError(message)


@dataclass(frozen=True)
class ValidationCommandRunRequest:
    """Adapter request to execute one structured validation command."""

    command: ValidationCommand
    working_directory: Path
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            message = "validation command timeout must be positive"
            raise ValueError(message)


@dataclass(frozen=True)
class ValidationCommandRunResult:
    """Adapter result for one validation command execution."""

    status: ValidationCommandRunStatus
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ValidationExecutionRequest:
    """Application request to classify and execute validation command candidates."""

    commands: tuple[ValidationCommandCandidate, ...]
    working_directory: Path
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            message = "validation execution timeout must be a finite positive number of seconds"
            raise ValueError(message)


@dataclass(frozen=True)
class ValidationExecutionResult:
    """Validation execution evidence and blockers for orchestration decisions."""

    evidence: tuple[ValidationEvidence, ...] = ()
    blockers: tuple[ValidationDiscoveryBlocker, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        """Return whether no validation command was blocked or failed."""
        return not self.blockers and all(item.status is ValidationEvidenceStatus.PASSED for item in self.evidence)


@dataclass(frozen=True)
class ValidationDiscoveryBlocker:
    """Actionable reason validation command discovery could not proceed safely."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "validation discovery blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "validation discovery blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class ValidationDiscoveryRequest:
    """Application request to discover focused and broad validation commands."""

    changed_paths: tuple[str, ...] = ()
    explicit_focused_commands: tuple[ValidationCommand, ...] = ()
    include_broad_commands: bool = True
    include_build_command: bool = True


@dataclass(frozen=True)
class ValidationDiscoveryResult:
    """Discovered validation candidates plus truthful pre-execution evidence."""

    commands: tuple[ValidationCommandCandidate, ...] = ()
    evidence: tuple[ValidationEvidence, ...] = ()
    blockers: tuple[ValidationDiscoveryBlocker, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        """Return whether discovery produced no blocking validation issues."""
        return not self.blockers


def normalized_validation_path(path: str) -> str:
    """Normalize a repository-relative validation path for matching."""
    normalized = PurePosixPath(path.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts or not normalized.as_posix().strip():
        message = "validation paths must be non-empty repository-relative paths"
        raise ValueError(message)
    return normalized.as_posix()
