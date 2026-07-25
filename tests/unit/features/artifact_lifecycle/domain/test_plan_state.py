"""Tests for implementation-plan lifecycle state invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from cline_sdlc.features.artifact_lifecycle.domain.plan_state import (
    PlanBlocker,
    PlanPhase,
    PlanState,
    ReviewReadiness,
)

VALID_DIGEST = "sha256:" + "a" * 64
VALID_COMMIT = "b" * 40
NOW = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)


def ready_state(**overrides: object) -> PlanState:
    values: dict[str, object] = {
        "work_id": "example-work",
        "phase": PlanPhase.READY,
        "specification": "docs/specs/example.md",
        "specification_digest": VALID_DIGEST,
        "plan_revision": 1,
        "review_iteration": 1,
        "review_readiness": ReviewReadiness.READY,
        "material_digest": VALID_DIGEST,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return PlanState(**cast("Any", values))


def test_ready_state_accepts_minimal_valid_values() -> None:
    state = ready_state(completed_slices=("task-1.1a",), partial_slice_paths=("docs/plans/", "src/package.py"))

    assert state.phase is PlanPhase.READY
    assert state.partial_slice_paths == ("docs/plans/", "src/package.py")


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("work_id", "not snake", "kebab-case"),
        ("specification", "../spec.md", "traversal"),
        ("specification_digest", "sha256:ABC", "sha256"),
        ("plan_revision", 0, "positive"),
        ("review_iteration", 4, "between 1 and 3"),
        ("completed_slices", ("task-a", "task-a"), "unique"),
    ],
)
def test_state_rejects_invalid_scalar_and_sequence_fields(field: str, value: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        ready_state(**{field: value})


def test_implementing_state_may_be_clean_between_atomic_slices() -> None:
    state = ready_state(phase=PlanPhase.IMPLEMENTING)

    assert not state.has_active_slice


def test_active_slice_fields_must_be_set_together() -> None:
    with pytest.raises(ValueError, match="set together"):
        ready_state(phase=PlanPhase.IMPLEMENTING, current_task="task-1-3")


def test_blocked_state_requires_blocker() -> None:
    with pytest.raises(ValueError, match="blocked state"):
        ready_state(phase=PlanPhase.BLOCKED, review_readiness=ReviewReadiness.BLOCKED)


def test_complete_state_requires_completed_timestamp() -> None:
    with pytest.raises(ValueError, match="completed_at"):
        ready_state(phase=PlanPhase.COMPLETE)


@pytest.mark.parametrize(
    "next_phase",
    [
        PlanPhase.IMPLEMENTING,
        PlanPhase.BLOCKED,
    ],
)
def test_phase_transition_matrix_allows_documented_ready_transitions(next_phase: PlanPhase) -> None:
    state = ready_state()

    if next_phase is PlanPhase.IMPLEMENTING:
        state.transition_to(next_phase)
    else:
        with pytest.raises(ValueError, match="invalid plan phase transition"):
            state.transition_to(next_phase)


def test_blocked_state_can_resume_implementing() -> None:
    state = ready_state(
        phase=PlanPhase.BLOCKED,
        review_readiness=ReviewReadiness.BLOCKED,
        current_task="task-1-3",
        current_slice="task-1-3",
        slice_start_commit=VALID_COMMIT,
        blocker=PlanBlocker(code="needs-review", summary="Human review required."),
    )

    state.transition_to(PlanPhase.IMPLEMENTING)
