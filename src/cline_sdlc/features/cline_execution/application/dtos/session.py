"""DTOs for one bounded Cline session application boundary."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from cline_sdlc.features.cline_execution.domain.outcome import SessionOutcome, SessionRole

_SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ClineSessionProcessStatus(StrEnum):
    """Observable process-level status for one Cline session."""

    EXITED = "exited"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"
    START_FAILED = "start_failed"


class ClineSessionExecutionMode(StrEnum):
    """Repository mutation capability requested for a bounded Cline session."""

    READ_ONLY = "read_only"
    WRITE_CAPABLE = "write_capable"


class ClineSessionEvidenceType(StrEnum):
    """Normalized SDK evidence categories visible to the application core."""

    ASSISTANT_OUTPUT = "assistant_output"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    FILE_CHANGE = "file_change"
    VALIDATION = "validation"
    APPROVAL_REQUEST = "approval_request"
    BLOCKER = "blocker"
    DIAGNOSTIC = "diagnostic"
    LIFECYCLE = "lifecycle"


class ClineSessionTerminalStatus(StrEnum):
    """Normalized SDK terminal status values returned by a bounded session."""

    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"
    INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True)
class ClineSessionArtifactContext:
    """Accepted artifact reference supplied to a bounded Cline session."""

    path: str
    digest: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _normalize_repository_path(self.path))
        if _SHA256_DIGEST_PATTERN.fullmatch(self.digest) is None:
            message = "session artifact context digests must use sha256:<lowercase hexadecimal>"
            raise ValueError(message)
        if not self.description.strip():
            message = "session artifact context description must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class ClineSessionEvidence:
    """Normalized SDK event or evidence observation for one bounded session."""

    evidence_type: ClineSessionEvidenceType
    summary: str
    sdk_event_type: str | None = None
    paths: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.summary.strip():
            message = "session evidence summary must not be empty"
            raise ValueError(message)
        if self.sdk_event_type is not None and not self.sdk_event_type.strip():
            message = "SDK event type diagnostic string must not be empty"
            raise ValueError(message)
        object.__setattr__(self, "paths", _normalized_unique_paths(self.paths))


@dataclass(frozen=True)
class ClineSessionBlocker:
    """Safe SDK-shaped blocker explaining why a bounded session could not complete."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "session blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "session blocker summary must not be empty"
            raise ValueError(message)
        if self.evidence is not None and not self.evidence.strip():
            message = "session blocker evidence must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class ClineSessionDiagnosticReference:
    """Safe reference to SDK-owned diagnostics without embedding raw transcripts."""

    kind: str
    value: str
    summary: str

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.value.strip() or not self.summary.strip():
            message = "session diagnostic reference kind, value, and summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class ClineSessionRequest:
    """Application request to execute one bounded Cline session.

    The command fields preserve the existing subprocess adapters during the SDK
    transition. The SDK-shaped fields express orchestrator-owned semantics and do
    not expose Node, TypeScript, or SDK package objects through the port.
    """

    command: tuple[str, ...]
    working_directory: Path
    timeout_seconds: float
    session_role: SessionRole | None = None
    instructions: str = ""
    outcome_contract: str = ""
    required_skills: tuple[str, ...] = field(default_factory=tuple)
    artifact_context: tuple[ClineSessionArtifactContext, ...] = field(default_factory=tuple)
    execution_mode: ClineSessionExecutionMode = ClineSessionExecutionMode.READ_ONLY
    safe_context: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.command:
            message = "session command must not be empty"
            raise ValueError(message)
        if any(not argument for argument in self.command):
            message = "session command arguments must not be empty"
            raise ValueError(message)
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            message = "session timeout must be a finite positive number of seconds"
            raise ValueError(message)
        if any(not skill.strip() for skill in self.required_skills):
            message = "required skills must not be empty"
            raise ValueError(message)
        if any(not item.strip() for item in self.safe_context):
            message = "safe context values must not be empty"
            raise ValueError(message)
        if self.session_role is not None:
            if not self.instructions.strip():
                message = "session instructions must not be empty when a session role is set"
                raise ValueError(message)
            if not self.outcome_contract.strip():
                message = "session outcome contract must not be empty when a session role is set"
                raise ValueError(message)


@dataclass(frozen=True)
class ClineSessionResult:
    """Typed observations returned by a bounded Cline session adapter."""

    process_status: ClineSessionProcessStatus
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    terminal_outcomes: tuple[SessionOutcome, ...] = field(default_factory=tuple)
    malformed_output_lines: tuple[str, ...] = field(default_factory=tuple)
    events: tuple[ClineSessionEvidence, ...] = field(default_factory=tuple)
    sdk_terminal_status: ClineSessionTerminalStatus | None = None
    blockers: tuple[ClineSessionBlocker, ...] = field(default_factory=tuple)
    diagnostic_references: tuple[ClineSessionDiagnosticReference, ...] = field(default_factory=tuple)

    @property
    def timed_out(self) -> bool:
        """Return whether the parent bounded the child by timeout."""
        return self.process_status is ClineSessionProcessStatus.TIMED_OUT

    @property
    def interrupted(self) -> bool:
        """Return whether the parent stopped the child after an interruption request."""
        return self.process_status is ClineSessionProcessStatus.INTERRUPTED

    @property
    def has_exactly_one_terminal_outcome(self) -> bool:
        """Return whether the captured stream contained exactly one validated outcome."""
        return len(self.terminal_outcomes) == 1


def _normalized_unique_paths(raw_paths: tuple[str, ...]) -> tuple[str, ...]:
    normalized_paths = tuple(_normalize_repository_path(path) for path in raw_paths)
    if len(set(normalized_paths)) != len(normalized_paths):
        message = "session evidence paths must be unique"
        raise ValueError(message)
    return normalized_paths


def _normalize_repository_path(raw_path: str) -> str:
    if not raw_path.strip():
        message = "session paths must not be empty"
        raise ValueError(message)
    if raw_path.startswith("/") or "\\" in raw_path:
        message = "session paths must be normalized repository-relative POSIX paths"
        raise ValueError(message)
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        message = "session paths must not contain traversal or empty segments"
        raise ValueError(message)
    return path.as_posix()
