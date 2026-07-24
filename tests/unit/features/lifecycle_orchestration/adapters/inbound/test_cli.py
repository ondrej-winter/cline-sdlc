"""Tests for supervised runner CLI input parsing and stage mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cline_sdlc.features.lifecycle_orchestration.adapters.inbound.cli import parse_cli_invocation
from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationParseError
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage, StageInputKind

if TYPE_CHECKING:
    from pathlib import Path

CUSTOM_TIMEOUT_SECONDS = 42.0


def test_rejects_missing_input() -> None:
    result = parse_cli_invocation([])

    assert isinstance(result, InvocationParseError)
    assert "required" in result.message


def test_rejects_multiple_inputs(tmp_path: Path) -> None:
    idea_file = tmp_path / "idea.md"
    idea_file.write_text("idea", encoding="utf-8")

    result = parse_cli_invocation(["--idea", "rough", "--idea-file", str(idea_file)])

    assert isinstance(result, InvocationParseError)
    assert "not allowed" in result.message


def test_rejects_empty_rough_idea() -> None:
    result = parse_cli_invocation(["--idea", "  "])

    assert isinstance(result, InvocationParseError)
    assert "must not be empty" in result.message


@pytest.mark.parametrize(
    ("option", "expected_kind", "expected_stage"),
    [
        ("--idea-file", StageInputKind.IDEA_FILE, LifecycleStage.SPECIFICATION_CREATION),
        ("--spec-file", StageInputKind.SPEC_FILE, LifecycleStage.PLAN_CREATION_AND_REVIEW),
        ("--plan-file", StageInputKind.PLAN_FILE, LifecycleStage.PLAN_IMPLEMENTATION),
    ],
)
def test_maps_file_input_to_stage(
    tmp_path: Path,
    option: str,
    expected_kind: StageInputKind,
    expected_stage: LifecycleStage,
) -> None:
    input_file = tmp_path / "artifact.md"
    input_file.write_text("artifact", encoding="utf-8")

    result = parse_cli_invocation([option, str(input_file)], cwd=tmp_path)

    assert not isinstance(result, InvocationParseError)
    assert result.request.source.kind is expected_kind
    assert result.request.source.value == input_file
    assert result.request.stage is expected_stage


def test_maps_rough_idea_to_idea_refinement() -> None:
    result = parse_cli_invocation(["--idea", "Build a supervised workflow runner"])

    assert not isinstance(result, InvocationParseError)
    assert result.request.source.kind is StageInputKind.IDEA
    assert result.request.source.value == "Build a supervised workflow runner"
    assert result.request.stage is LifecycleStage.IDEA_REFINEMENT


def test_rejects_missing_file_input(tmp_path: Path) -> None:
    result = parse_cli_invocation(["--spec-file", "missing.md"], cwd=tmp_path)

    assert isinstance(result, InvocationParseError)
    assert "does not exist" in result.message


def test_rejects_directory_file_input(tmp_path: Path) -> None:
    result = parse_cli_invocation(["--plan-file", str(tmp_path)], cwd=tmp_path)

    assert isinstance(result, InvocationParseError)
    assert "not a file" in result.message


def test_accepts_dry_run_friendly_common_options() -> None:
    result = parse_cli_invocation(
        [
            "--idea",
            "Refine this",
            "--timeout",
            str(CUSTOM_TIMEOUT_SECONDS),
            "--cline-command",
            "/opt/bin/cline",
            "--json",
            "--verbose",
            "--dry-run",
        ],
    )

    assert not isinstance(result, InvocationParseError)
    assert result.request.timeout_seconds == CUSTOM_TIMEOUT_SECONDS
    assert result.request.cline_command == "/opt/bin/cline"
    assert result.request.emit_json is True
    assert result.request.verbose is True
    assert result.request.dry_run is True


def test_rejects_non_finite_timeout() -> None:
    result = parse_cli_invocation(["--idea", "rough", "--timeout", "inf"])

    assert isinstance(result, InvocationParseError)
    assert "finite positive" in result.message
