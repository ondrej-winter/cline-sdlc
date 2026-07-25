"""DTOs for ignored run audit summary records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path  # noqa: TC003 - Runtime dataclass boundary intentionally exposes Path.


class RunAuditStatus(StrEnum):
    """Terminal status for recording a run audit summary."""

    RECORDED = "recorded"
    FAILED = "failed"


@dataclass(frozen=True)
class RunAuditBlocker:
    """Actionable reason that prevented safe audit persistence."""

    code: str
    summary: str
    path: str | None = None
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "run-audit blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "run-audit blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class RunAuditEvent:
    """One redaction-safe operational event included in a run summary."""

    category: str
    message: str
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.category.strip():
            message = "run-audit event category must not be empty"
            raise ValueError(message)
        if not self.message.strip():
            message = "run-audit event message must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class RunAuditRecord:
    """Versioned run summary payload safe to persist in an ignored directory."""

    schema_version: int
    run_id: str
    terminal_status: str
    events: tuple[RunAuditEvent, ...] = ()


@dataclass(frozen=True)
class InvocationApprovalRecord:
    """Versioned immutable invocation approval persisted before implementation."""

    schema_version: int
    run_id: str
    profile: str
    starting_head: str
    approved_at: str
    specification_digest: str
    material_digest: str
    remediation_envelope_applicable: bool


@dataclass(frozen=True)
class RunAuditRequest:
    """Application request to redact and persist one run summary."""

    repository_root: Path
    run_id: str
    terminal_status: str
    events: tuple[RunAuditEvent, ...] = ()
    sensitive_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunAuditResult:
    """Typed result for ignored run audit summary persistence."""

    status: RunAuditStatus
    summary_path: str | None = None
    record: RunAuditRecord | None = None
    blockers: tuple[RunAuditBlocker, ...] = field(default_factory=tuple)

    @property
    def recorded(self) -> bool:
        """Return whether the summary was safely recorded."""
        return self.status is RunAuditStatus.RECORDED


@dataclass(frozen=True)
class InvocationApprovalRecordResult:
    """Result of immutable invocation approval persistence."""

    recorded: bool
    approval_path: str | None = None
    blocker: RunAuditBlocker | None = None
