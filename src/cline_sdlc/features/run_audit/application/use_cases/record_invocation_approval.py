"""Record one immutable invocation approval through the audit store."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_sdlc.features.run_audit.application.dtos.run_audit import (
        InvocationApprovalRecord,
        InvocationApprovalRecordResult,
    )
    from cline_sdlc.features.run_audit.application.ports.audit_store import InvocationApprovalStorePort

APPROVAL_SCHEMA_VERSION = 1


class RecordInvocationApproval:
    """Persist an already validated approval payload without changing it."""

    def __init__(self, store: InvocationApprovalStorePort) -> None:
        self._store = store

    def execute(self, repository_root: str, record: InvocationApprovalRecord) -> InvocationApprovalRecordResult:
        """Delegate immutable persistence to the configured audit store."""
        if record.schema_version != APPROVAL_SCHEMA_VERSION:
            message = "unsupported invocation approval schema version"
            raise ValueError(message)
        return self._store.store_approval(repository_root, record)
