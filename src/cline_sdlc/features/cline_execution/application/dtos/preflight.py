"""DTOs for Cline capability and skill preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ClinePreflightStatus(StrEnum):
    """Terminal status for a Cline preflight check."""

    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class ClinePreflightBlocker:
    """Actionable reason that prevents starting a lifecycle stage session."""

    code: str
    summary: str
    evidence: str


@dataclass(frozen=True)
class ClinePreflightRequest:
    """Application request to verify Cline readiness before stage execution."""

    command: tuple[str, ...] = ("cline",)
    required_skills: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.command:
            message = "preflight command must not be empty"
            raise ValueError(message)
        if any(not argument for argument in self.command):
            message = "preflight command arguments must not be empty"
            raise ValueError(message)
        if any(not skill.strip() for skill in self.required_skills):
            message = "required skills must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class ClinePreflightResult:
    """Typed Cline readiness result for pre-session orchestration."""

    status: ClinePreflightStatus
    executable: str
    version: str | None
    blockers: tuple[ClinePreflightBlocker, ...] = ()

    @property
    def ready(self) -> bool:
        """Return whether a lifecycle stage may start a Cline session."""
        return self.status is ClinePreflightStatus.READY
