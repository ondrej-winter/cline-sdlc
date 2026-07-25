"""Outbound port for ignored run audit summary persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.run_audit.application.dtos.run_audit import (
        InvocationApprovalRecord,
        InvocationApprovalRecordResult,
        RunAuditRecord,
        RunAuditRequest,
        RunAuditResult,
    )


class RunAuditStorePort(Protocol):
    """Persist a redacted audit record after establishing an ignored destination."""

    def store(self, request: RunAuditRequest, record: RunAuditRecord) -> RunAuditResult:
        """Persist the supplied redacted summary record."""


class InvocationApprovalStorePort(Protocol):
    """Persist an immutable invocation approval in ignored run state."""

    def store_approval(
        self,
        repository_root: str,
        record: InvocationApprovalRecord,
    ) -> InvocationApprovalRecordResult:
        """Persist one immutable approval record."""
