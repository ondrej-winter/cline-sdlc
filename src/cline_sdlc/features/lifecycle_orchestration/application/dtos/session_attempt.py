"""DTOs for bounded lifecycle Cline session attempts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest, ClineSessionResult
    from cline_sdlc.features.repository_coordination.application.dtos.repository import (
        RepositoryInspectionRequest,
        RepositorySnapshot,
    )

MIN_SESSION_ATTEMPTS = 1
MAX_SESSION_ATTEMPTS = 2


class SessionAttemptStatus(StrEnum):
    """Terminal status for a bounded session-attempt transaction."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class SessionRetryReason(StrEnum):
    """Documented reasons that may permit one fresh session retry."""

    PROTOCOL_OUTPUT = "protocol_output"
    TRANSIENT_STARTUP = "transient_startup"


@dataclass(frozen=True)
class SessionAttemptSdkEvidence:
    """Lifecycle-facing summary of normalized SDK evidence for one attempt.

    This DTO keeps SDK observations as supporting evidence. It does not make SDK
    events authoritative for lifecycle advancement, changed paths, validation, or
    commit eligibility.
    """

    sdk_terminal_status: str | None = None
    event_count: int = 0
    blocker_codes: tuple[str, ...] = field(default_factory=tuple)
    diagnostic_references: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.sdk_terminal_status is not None and not self.sdk_terminal_status.strip():
            message = "SDK terminal status evidence must not be empty"
            raise ValueError(message)
        if self.event_count < 0:
            message = "SDK event evidence count must not be negative"
            raise ValueError(message)
        if any(not code.strip() for code in self.blocker_codes):
            message = "SDK blocker evidence codes must not be empty"
            raise ValueError(message)
        if any(not reference.strip() for reference in self.diagnostic_references):
            message = "SDK diagnostic evidence references must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SessionAttemptBlocker:
    """Actionable reason that prevented more session attempts."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "session-attempt blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "session-attempt blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SessionAttemptObservation:
    """Repository and process evidence for one attempted Cline session."""

    attempt_number: int
    before_snapshot: RepositorySnapshot
    session_result: ClineSessionResult
    after_snapshot: RepositorySnapshot | None
    retry_reason: SessionRetryReason | None = None
    sdk_evidence: SessionAttemptSdkEvidence = field(default_factory=SessionAttemptSdkEvidence)


@dataclass(frozen=True)
class SessionAttemptRequest:
    """Application request to coordinate one bounded session attempt transaction."""

    session_request: ClineSessionRequest
    repository_request: RepositoryInspectionRequest
    max_attempts: int = 2
    transient_startup_exit_codes: tuple[int, ...] = (1,)

    def __post_init__(self) -> None:
        if self.max_attempts < MIN_SESSION_ATTEMPTS or self.max_attempts > MAX_SESSION_ATTEMPTS:
            message = "bounded session attempts support one initial attempt and at most one retry"
            raise ValueError(message)


@dataclass(frozen=True)
class SessionAttemptResult:
    """Typed outcome of coordinating bounded Cline session attempts."""

    status: SessionAttemptStatus
    attempts: tuple[SessionAttemptObservation, ...]
    blocker: SessionAttemptBlocker | None = None
    terminal_session_result: ClineSessionResult | None = None
    changed_paths: tuple[str, ...] = field(default_factory=tuple)

    @property
    def completed(self) -> bool:
        """Return whether exactly one terminal session outcome completed the transaction."""
        return self.status is SessionAttemptStatus.COMPLETED
