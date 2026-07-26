"""Tests for strict embedded plan-state YAML parsing."""

from __future__ import annotations

import pytest

from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import (
    StrictStateYAMLError,
    parse_plan_state_from_markdown,
    parse_plan_state_yaml,
)
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase

VALID_DIGEST = "sha256:" + "a" * 64


def valid_state_yaml(**overrides: object) -> str:
    values = {
        "schema_version": 1,
        "work_id": "example-work",
        "profile": "balanced",
        "phase": "ready",
        "specification": "docs/specs/example.md",
        "specification_digest": VALID_DIGEST,
        "plan_revision": 1,
        "review_iteration": 1,
        "review_readiness": "ready",
        "digest_schema_version": 1,
        "material_digest": VALID_DIGEST,
        "current_task": None,
        "current_slice": None,
        "slice_start_commit": None,
        "partial_slice_paths": [],
        "completed_slices": [],
        "remediation_records": [],
        "validation_evidence": [],
        "blocker": None,
        "created_at": "2026-07-24T09:30:00Z",
        "updated_at": "2026-07-24T09:30:00Z",
        "completed_at": None,
    }
    values.update(overrides)
    lines: list[str] = []
    for key, value in values.items():
        if value is None:
            rendered = "null"
        elif isinstance(value, list):
            rendered = "[]"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines)


def test_parses_exactly_one_state_block_from_markdown() -> None:
    markdown = f"# Plan\n\n```cline-sdlc-state\n{valid_state_yaml()}\n```\n"

    state = parse_plan_state_from_markdown(markdown)

    assert state.phase is PlanPhase.READY


@pytest.mark.parametrize(
    "markdown",
    [
        "# Plan without state\n",
        "```cline-sdlc-state\nphase: ready\n```\n```cline-sdlc-state\nphase: ready\n```\n",
    ],
)
def test_rejects_missing_or_multiple_state_blocks(markdown: str) -> None:
    with pytest.raises(StrictStateYAMLError, match="exactly one"):
        parse_plan_state_from_markdown(markdown)


def test_rejects_duplicate_keys() -> None:
    raw_yaml = f"{valid_state_yaml()}\nphase: complete\n"

    with pytest.raises(StrictStateYAMLError, match="invalid cline-sdlc-state YAML"):
        parse_plan_state_yaml(raw_yaml)


def test_rejects_unknown_top_level_fields() -> None:
    raw_yaml = f"{valid_state_yaml()}\nunexpected: value\n"

    with pytest.raises(StrictStateYAMLError, match="unknown plan state fields"):
        parse_plan_state_yaml(raw_yaml)


def test_rejects_unsupported_schema_version() -> None:
    with pytest.raises(StrictStateYAMLError, match="unsupported"):
        parse_plan_state_yaml(valid_state_yaml(schema_version=2))


def test_rejects_path_traversal() -> None:
    with pytest.raises(StrictStateYAMLError, match="traversal"):
        parse_plan_state_yaml(valid_state_yaml(specification="../spec.md"))


def test_rejects_unexpected_type() -> None:
    with pytest.raises(StrictStateYAMLError, match="plan_revision must be an integer"):
        parse_plan_state_yaml(valid_state_yaml(plan_revision="one"))


def test_rejects_aliases() -> None:
    raw_yaml = valid_state_yaml().replace("partial_slice_paths: []", "partial_slice_paths: &paths []")

    with pytest.raises(StrictStateYAMLError, match="aliases"):
        parse_plan_state_yaml(raw_yaml)


def test_rejects_custom_tags() -> None:
    raw_yaml = valid_state_yaml(work_id="!custom example-work")

    with pytest.raises(StrictStateYAMLError, match=r"custom tags|invalid cline-sdlc-state YAML"):
        parse_plan_state_yaml(raw_yaml)


def test_parses_strict_pending_remediation_record() -> None:
    record_yaml = """
  - finding_id: FINAL-001
    requirement: Preserve broad validation evidence.
    path_scope:
      - src/final_validation.py
    correction: Preserve every affected broad check.
    verification: uv run pytest tests/test_final_validation.py
    status: pending
    attempt_count: 0"""

    state = parse_plan_state_yaml(valid_state_yaml(remediation_records=record_yaml))

    assert len(state.remediation_records) == 1
    assert state.remediation_records[0].finding_id == "FINAL-001"
    assert state.remediation_records[0].path_scope == ("src/final_validation.py",)


def test_rejects_remediation_status_attempt_mismatch() -> None:
    record_yaml = """
  - finding_id: FINAL-001
    requirement: Preserve broad validation evidence.
    path_scope:
      - src/final_validation.py
    correction: Preserve every affected broad check.
    verification: uv run pytest tests/test_final_validation.py
    status: completed
    attempt_count: 0"""

    with pytest.raises(StrictStateYAMLError, match="status and attempt_count"):
        parse_plan_state_yaml(valid_state_yaml(remediation_records=record_yaml))
