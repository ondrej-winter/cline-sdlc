"""Tests for filesystem authored-plan content loading."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.filesystem_authored_plan import (
    FilesystemAuthoredPlanContentReader,
)
from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import AuthoredPlanInspectionRequest

if TYPE_CHECKING:
    from pathlib import Path


def test_reads_artifact_content_and_strict_plan_state(tmp_path: Path) -> None:
    specification = tmp_path / "docs/specs/example.md"
    plan = tmp_path / "docs/plans/example.md"
    specification.parent.mkdir(parents=True)
    plan.parent.mkdir(parents=True)
    specification.write_text("# Specification\n", encoding="utf-8")
    plan.write_text(_plan_markdown(), encoding="utf-8")

    result = FilesystemAuthoredPlanContentReader(tmp_path).read(
        AuthoredPlanInspectionRequest(
            specification_path="docs/specs/example.md",
            plan_path="docs/plans/example.md",
        )
    )

    assert result.specification_content == b"# Specification\n"
    assert result.plan_state.work_id == "example-work"


def test_rejects_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-spec.md"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="inside the repository"):
        FilesystemAuthoredPlanContentReader(tmp_path).read(
            AuthoredPlanInspectionRequest(
                specification_path="../outside-spec.md",
                plan_path="docs/plans/missing.md",
            )
        )


def _plan_markdown() -> str:
    digest = f"sha256:{'0' * 64}"
    return f"""# Plan

<!-- cline-sdlc-material:start -->
material
<!-- cline-sdlc-material:end -->
<!-- cline-sdlc-progress:start -->
```cline-sdlc-state
schema_version: 1
work_id: example-work
profile: balanced
phase: drafting
specification: docs/specs/example.md
specification_digest: {digest}
plan_revision: 1
review_iteration: 1
review_readiness: not_reviewed
digest_schema_version: 1
material_digest: {digest}
current_task: null
current_slice: null
slice_start_commit: null
partial_slice_paths: []
completed_slices: []
remediation_records: []
validation_evidence: []
blocker: null
created_at: 2026-07-24T00:00:00Z
updated_at: 2026-07-24T00:00:00Z
completed_at: null
```
<!-- cline-sdlc-progress:end -->
"""
