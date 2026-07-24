"""DTOs for ordered lifecycle stage preflight orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
        ArtifactLocationResult,
        SelectArtifactLocationRequest,
    )
    from cline_sdlc.features.cline_execution.application.dtos.preflight import ClinePreflightRequest
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest
    from cline_sdlc.features.repository_coordination.application.dtos.repository import (
        RepositoryInspectionRequest,
        RepositorySnapshot,
    )
    from cline_sdlc.features.run_audit.application.dtos.run_audit import RunAuditRequest


class StagePreflightStatus(StrEnum):
    """Terminal status for ordered no-write stage preflight."""

    AUTHORIZED = "authorized"
    BLOCKED = "blocked"


class StagePreflightStep(StrEnum):
    """Ordered stage preflight steps that may produce evidence or blockers."""

    INVOCATION = "invocation"
    ARTIFACT_LOCATION = "artifact_location"
    REPOSITORY = "repository"
    RUN_AUDIT = "run_audit"
    CLINE_CAPABILITY = "cline_capability"


@dataclass(frozen=True)
class StagePreflightBlocker:
    """Actionable reason that prevents starting a lifecycle stage session."""

    step: StagePreflightStep
    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "stage preflight blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "stage preflight blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class StagePreflightEvidence:
    """One ordered preflight observation suitable for tests and run summaries."""

    step: StagePreflightStep
    summary: str

    def __post_init__(self) -> None:
        if not self.summary.strip():
            message = "stage preflight evidence summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class StagePreflightRequest:
    """Application request to authorize one lifecycle stage before any stage session starts."""

    invocation: InvocationRequest
    artifact_location_request: SelectArtifactLocationRequest | None
    repository_request: RepositoryInspectionRequest
    cline_preflight_request: ClinePreflightRequest
    run_audit_request: RunAuditRequest | None = None


@dataclass(frozen=True)
class StagePreflightResult:
    """Typed authorization or blocker result for one ordered preflight transaction."""

    status: StagePreflightStatus
    evidence: tuple[StagePreflightEvidence, ...] = ()
    blockers: tuple[StagePreflightBlocker, ...] = field(default_factory=tuple)
    artifact_location: ArtifactLocationResult | None = None
    repository_snapshot: RepositorySnapshot | None = None
    audit_summary_path: str | None = None

    @property
    def authorized(self) -> bool:
        """Return whether a lifecycle stage session may start."""
        return self.status is StagePreflightStatus.AUTHORIZED
