"""DTOs for validating an initially authored implementation plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanState


@dataclass(frozen=True)
class AuthoredPlanValidationRequest:
    """Content and identity required to validate an authored plan."""

    specification_path: str
    specification_content: bytes
    plan_path: str
    plan_content: bytes
    plan_state: PlanState


@dataclass(frozen=True)
class AuthoredPlanInspectionRequest:
    """Artifact paths to inspect after a plan-author session."""

    specification_path: str
    plan_path: str


@dataclass(frozen=True)
class AuthoredPlanBlocker:
    """Actionable authored-plan validation failure."""

    code: str
    summary: str
    evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "authored-plan blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "authored-plan blocker summary must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class AuthoredPlanValidationResult:
    """Validated authored-plan identity and digest evidence."""

    valid: bool
    plan_path: str
    specification_digest: str | None = None
    material_digest: str | None = None
    blockers: tuple[AuthoredPlanBlocker, ...] = field(default_factory=tuple)
