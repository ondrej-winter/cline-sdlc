"""DTOs for validation command discovery and evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath


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
    """Truthful status for validation evidence before command execution."""

    NOT_RUN = "not_run"
    BLOCKED = "blocked"


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
    """Truthful validation evidence produced before execution is implemented."""

    scope: ValidationScope
    command: ValidationCommand | None
    status: ValidationEvidenceStatus
    summary: str


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
