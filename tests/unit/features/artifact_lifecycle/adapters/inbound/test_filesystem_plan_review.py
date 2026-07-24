"""Tests for progress-only filesystem plan-review updates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.filesystem_plan_review import (
    FilesystemPlanReviewProgressWriter,
)
from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import parse_plan_state_from_markdown
from cline_sdlc.features.artifact_lifecycle.application.dtos.plan_review import PlanReviewProgressRequest
from cline_sdlc.features.artifact_lifecycle.domain.digests import (
    PlanMaterialDigestInput,
    compute_plan_material_digest,
    compute_specification_digest,
)
from cline_sdlc.features.artifact_lifecycle.domain.findings import (
    Finding,
    FindingSeverity,
    FindingStatus,
    PlanReviewReadiness,
)
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase, ReviewReadiness
from cline_sdlc.features.artifact_lifecycle.domain.regions import parse_plan_regions

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SPECIFICATION_PATH = "docs/specs/example-spec.md"
PLAN_PATH = "docs/plans/example-plan.md"
SPECIFICATION_CONTENT = b"# Accepted specification\n"
PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"


def test_marks_ready_review_without_changing_material(tmp_path: Path) -> None:
    plan_path = _write_initial_plan(tmp_path)
    before = plan_path.read_text(encoding="utf-8")

    result = FilesystemPlanReviewProgressWriter(tmp_path).execute(
        PlanReviewProgressRequest(
            plan_path=PLAN_PATH,
            findings=(),
            readiness=PlanReviewReadiness.READY,
            updated_at=datetime(2026, 7, 24, 22, tzinfo=UTC),
        )
    )

    after = plan_path.read_text(encoding="utf-8")
    state = parse_plan_state_from_markdown(after)
    assert result.updated
    assert state.phase is PlanPhase.READY
    assert state.review_readiness is ReviewReadiness.READY
    assert "No findings." in after
    assert parse_plan_regions(before).material_content == parse_plan_regions(after).material_content
    assert result.material_digest == state.material_digest


def test_records_complete_findings_as_changes_required(tmp_path: Path) -> None:
    plan_path = _write_initial_plan(tmp_path)
    finding = Finding(
        id="PLAN-001",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        summary="Validation scope is incomplete.",
        evidence="The plan omits the broad quality gate.",
        required_correction="Add the broad quality gate.",
        affected_sections=("Verification",),
    )

    result = FilesystemPlanReviewProgressWriter(tmp_path).execute(
        PlanReviewProgressRequest(
            plan_path=PLAN_PATH,
            findings=(finding,),
            readiness=PlanReviewReadiness.CHANGES_REQUIRED,
            updated_at=datetime(2026, 7, 24, 22, tzinfo=UTC),
        )
    )

    markdown = plan_path.read_text(encoding="utf-8")
    state = parse_plan_state_from_markdown(markdown)
    assert result.updated
    assert state.phase is PlanPhase.REVIEWING
    assert state.review_readiness is ReviewReadiness.CHANGES_REQUIRED
    assert 'id: "PLAN-001"' in markdown
    assert 'required_correction: "Add the broad quality gate."' in markdown


def test_rejects_findings_after_state_without_changing_plan(tmp_path: Path) -> None:
    plan_path = _write_initial_plan(tmp_path)
    original = plan_path.read_text(encoding="utf-8")
    malformed = original.replace(
        "```\n<!-- cline-sdlc-progress:end -->",
        "```\n\n### Plan-review findings\n\nNo findings.\n<!-- cline-sdlc-progress:end -->",
    )
    plan_path.write_text(malformed, encoding="utf-8")

    result = _writer(tmp_path).execute(_ready_request())

    assert not result.updated
    assert plan_path.read_text(encoding="utf-8") == malformed


def test_atomic_write_failure_preserves_original_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan_path = _write_initial_plan(tmp_path)
    original = plan_path.read_text(encoding="utf-8")

    def fail_replace(_source: Path, _destination: Path) -> None:
        message = "replace failed"
        raise OSError(message)

    monkeypatch.setattr("pathlib.Path.replace", fail_replace)

    result = _writer(tmp_path).execute(_ready_request())

    assert not result.updated
    assert plan_path.read_text(encoding="utf-8") == original


def _writer(repository_root: Path) -> FilesystemPlanReviewProgressWriter:
    return FilesystemPlanReviewProgressWriter(repository_root)


def _ready_request() -> PlanReviewProgressRequest:
    return PlanReviewProgressRequest(
        plan_path=PLAN_PATH,
        findings=(),
        readiness=PlanReviewReadiness.READY,
        updated_at=datetime(2026, 7, 24, 22, tzinfo=UTC),
    )


def _write_initial_plan(repository_root: Path) -> Path:
    plan_path = repository_root / PLAN_PATH
    plan_path.parent.mkdir(parents=True)
    content = _plan_content(PLACEHOLDER_DIGEST)
    material_digest = compute_plan_material_digest(
        PlanMaterialDigestInput(
            plan_markdown=content,
            plan_revision=1,
            specification=SPECIFICATION_PATH,
            specification_digest=compute_specification_digest(SPECIFICATION_CONTENT),
        )
    )
    plan_path.write_bytes(_plan_content(material_digest))
    return plan_path


def _plan_content(material_digest: str) -> bytes:
    specification_digest = compute_specification_digest(SPECIFICATION_CONTENT)
    timestamp = datetime(2026, 7, 24, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    return f"""# Example plan

<!-- cline-sdlc-material:start -->
## Objective
Deliver the accepted specification.

## Scope
Implement the bounded capability.

## Non-goals
Do not expand scope.

## Repository context and constraints
Follow repository rules.

## Material decisions and risks
Keep boundaries explicit.

## Tasks and slices
Ordered slice 1.

## Verification
Run focused and broad checks.
<!-- cline-sdlc-material:end -->

<!-- cline-sdlc-progress:start -->
```cline-sdlc-state
schema_version: 1
work_id: example-work
profile: balanced
phase: drafting
specification: {SPECIFICATION_PATH}
specification_digest: {specification_digest}
plan_revision: 1
review_iteration: 1
review_readiness: not_reviewed
digest_schema_version: 1
material_digest: {material_digest}
current_task: null
current_slice: null
slice_start_commit: null
partial_slice_paths: []
completed_slices: []
remediation_records: []
validation_evidence: []
blocker: null
created_at: {timestamp}
updated_at: {timestamp}
completed_at: null
```
<!-- cline-sdlc-progress:end -->
""".encode()
