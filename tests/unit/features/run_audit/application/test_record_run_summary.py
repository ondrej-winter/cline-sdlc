"""Tests for recording redacted run summaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cline_sdlc.features.run_audit.application.dtos.run_audit import (
    RunAuditEvent,
    RunAuditRecord,
    RunAuditRequest,
    RunAuditResult,
    RunAuditStatus,
)
from cline_sdlc.features.run_audit.application.use_cases.record_run_summary import (
    RUN_AUDIT_SCHEMA_VERSION,
    RecordRunSummary,
)
from cline_sdlc.features.run_audit.domain.redaction import REDACTION_MARKER


@dataclass
class RecordingStore:
    request: RunAuditRequest | None = None
    record: RunAuditRecord | None = None

    def store(self, request: RunAuditRequest, record: RunAuditRecord) -> RunAuditResult:
        self.request = request
        self.record = record
        return RunAuditResult(
            status=RunAuditStatus.RECORDED, summary_path=".cline-sdlc/runs/run-1/summary.json", record=record
        )


def test_redacts_summary_before_delegating_to_store() -> None:
    store = RecordingStore()
    request = RunAuditRequest(
        repository_root=Path("/repo"),
        run_id="run-1",
        terminal_status="blocked token=abc",
        events=(
            RunAuditEvent(
                category="session",
                message="Authorization=Bearer secret-value",
                metadata=(("prompt", "private prompt"), ("changed_paths", "docs/spec.md")),
            ),
        ),
        sensitive_fragments=("private prompt",),
    )

    result = RecordRunSummary(store).execute(request)

    assert result.recorded
    assert store.request == request
    assert store.record is not None
    assert store.record.schema_version == RUN_AUDIT_SCHEMA_VERSION
    assert store.record.terminal_status == f"blocked token={REDACTION_MARKER}"
    assert store.record.events[0].message == f"Authorization=Bearer {REDACTION_MARKER}"
    assert store.record.events[0].metadata == (("prompt", REDACTION_MARKER), ("changed_paths", "docs/spec.md"))
