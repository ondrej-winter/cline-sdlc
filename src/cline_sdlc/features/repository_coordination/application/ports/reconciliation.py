"""Outbound ports for plan artifact, Git history, and approval reconciliation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import (
        InvocationApproval,
        PlanArtifactInspection,
        PlanHistoryObservation,
        PlanHistoryRequest,
    )


class PlanArtifactInspectorPort(Protocol):
    """Validate plan/specification content and expose normalized progress evidence."""

    def inspect(self, plan_content: bytes, specification_content: bytes) -> PlanArtifactInspection:
        """Return strict artifact and digest evidence."""


class PlanHistoryReaderPort(Protocol):
    """Observe current Git state and reachable slice-owner candidates."""

    def observe(self, request: PlanHistoryRequest) -> PlanHistoryObservation:
        """Return Git evidence without modifying the repository."""


class InvocationApprovalRecorderPort(Protocol):
    """Persist one immutable invocation approval before work is authorized."""

    def record_approval(self, repository_root: str, approval: InvocationApproval) -> str:
        """Record approval and return its repository-relative ignored summary path."""
