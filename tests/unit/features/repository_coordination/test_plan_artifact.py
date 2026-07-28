"""Unit tests for plan artifact reconciliation evidence."""

from __future__ import annotations

from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase
from cline_sdlc.features.repository_coordination.adapters.outbound.plan_artifact import StrictPlanArtifactInspector


def test_plain_plan_without_embedded_state_yields_initial_evidence() -> None:
    plan = b"""# Implementation Plan: Example Work

Based on `docs/specs/example-work-spec.md`.

## Task 1: First slice

**Likely files/components touched:**

- `src/example.py`
"""
    specification = b"# Example Work Spec\n\nAccepted behavior.\n"

    result = StrictPlanArtifactInspector().inspect(plan, specification)

    assert result.error is None
    assert result.evidence is not None
    assert result.evidence.work_id == "implementation-plan-example-work"
    assert result.evidence.specification_path == "docs/specs/example-work-spec.md"
    assert result.evidence.specification_digest.startswith("sha256:")
    assert result.evidence.material_digest.startswith("sha256:")
    assert result.evidence.phase is PlanPhase.READY
    assert result.evidence.completed_slice_ids == ()
    assert result.evidence.current_task is None
    assert result.evidence.current_slice is None
