"""Use case for recording redacted run audit summaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.run_audit.application.dtos.run_audit import (
    RunAuditEvent,
    RunAuditRecord,
    RunAuditRequest,
    RunAuditResult,
)
from cline_sdlc.features.run_audit.domain.redaction import RedactionPolicy

if TYPE_CHECKING:
    from cline_sdlc.features.run_audit.application.ports.audit_store import RunAuditStorePort

RUN_AUDIT_SCHEMA_VERSION = 1


class RecordRunSummary:
    """Redact a run summary and persist it through an audit store port."""

    def __init__(self, store: RunAuditStorePort) -> None:
        self._store = store

    def execute(self, request: RunAuditRequest) -> RunAuditResult:
        """Persist a redacted versioned run summary without performing filesystem I/O directly."""
        policy = RedactionPolicy(sensitive_fragments=request.sensitive_fragments)
        record = RunAuditRecord(
            schema_version=RUN_AUDIT_SCHEMA_VERSION,
            run_id=policy.redact(request.run_id),
            terminal_status=policy.redact(request.terminal_status),
            events=tuple(_redact_event(event, policy) for event in request.events),
        )
        return self._store.store(request, record)


def _redact_event(event: RunAuditEvent, policy: RedactionPolicy) -> RunAuditEvent:
    return RunAuditEvent(
        category=policy.redact(event.category),
        message=policy.redact(event.message),
        metadata=tuple((policy.redact(key), policy.redact(value)) for key, value in event.metadata),
    )
