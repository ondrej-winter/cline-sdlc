"""DTOs for applying an independently validated initial plan review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from cline_sdlc.features.artifact_lifecycle.domain.findings import Finding, PlanReviewReadiness
    from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanState


@dataclass(frozen=True)
class PlanReviewProgressRequest:
    """Validated review evidence to persist in one plan progress region."""

    plan_path: str
    findings: tuple[Finding, ...]
    readiness: PlanReviewReadiness
    updated_at: datetime


@dataclass(frozen=True)
class PlanReviewProgressResult:
    """Result of persisting progress-only initial review evidence."""

    updated: bool
    plan_path: str
    plan_state: PlanState | None = None
    material_digest: str | None = None
    blockers: tuple[str, ...] = field(default_factory=tuple)
