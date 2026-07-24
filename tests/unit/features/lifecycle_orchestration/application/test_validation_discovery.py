"""Tests for validation command discovery."""

from __future__ import annotations

import pytest

from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandSource,
    ValidationDiscoveryRequest,
    ValidationEvidenceStatus,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.discover_validation import (
    DiscoverValidationCommands,
)


def test_explicit_focused_commands_take_precedence() -> None:
    command = ValidationCommand(executable="uv", arguments=("run", "pytest", "tests/unit/custom_test.py"))

    result = DiscoverValidationCommands().execute(
        ValidationDiscoveryRequest(
            changed_paths=("src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/example.py",),
            explicit_focused_commands=(command,),
            include_broad_commands=False,
        )
    )

    assert result.ready
    assert len(result.commands) == 1
    assert result.commands[0].command == command
    assert result.commands[0].source is ValidationCommandSource.EXPLICIT
    assert result.evidence[0].status is ValidationEvidenceStatus.NOT_RUN


def test_discovers_focused_pytest_targets_from_python_paths() -> None:
    result = DiscoverValidationCommands().execute(
        ValidationDiscoveryRequest(
            changed_paths=(
                "src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/run_session_attempts.py",
                "tests/unit/features/lifecycle_orchestration/application/test_session_attempts.py",
            ),
            include_broad_commands=False,
        )
    )

    assert result.ready
    assert len(result.commands) == 1
    assert result.commands[0].scope is ValidationScope.FOCUSED
    assert result.commands[0].command == ValidationCommand(
        executable="uv",
        arguments=(
            "run",
            "pytest",
            "tests/unit/features/lifecycle_orchestration/application/use_cases/run_session_attempts",
            "tests/unit/features/lifecycle_orchestration/application/test_session_attempts.py",
        ),
    )


def test_discovers_deterministic_broad_quality_gate_commands() -> None:
    result = DiscoverValidationCommands().execute(ValidationDiscoveryRequest(changed_paths=()))

    assert result.ready
    broad_commands = [candidate.command for candidate in result.commands if candidate.scope is ValidationScope.BROAD]
    assert broad_commands == [
        ValidationCommand(executable="uv", arguments=("run", "ruff", "format", "--check", ".")),
        ValidationCommand(executable="uv", arguments=("run", "ruff", "check", ".")),
        ValidationCommand(executable="uv", arguments=("run", "mypy", ".")),
        ValidationCommand(executable="uv", arguments=("run", "pytest")),
        ValidationCommand(executable="uv", arguments=("build",)),
    ]
    assert all(evidence.status is ValidationEvidenceStatus.NOT_RUN for evidence in result.evidence)


def test_invalid_changed_path_blocks_discovery_without_successful_evidence() -> None:
    result = DiscoverValidationCommands().execute(
        ValidationDiscoveryRequest(changed_paths=("../outside.py",), include_broad_commands=False)
    )

    assert not result.ready
    assert result.commands == ()
    assert result.blockers[0].code == "invalid_validation_path"
    assert result.evidence[0].status is ValidationEvidenceStatus.BLOCKED


@pytest.mark.parametrize("value", ["", " ", "bad\x00value"])
def test_validation_command_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match="validation command"):
        ValidationCommand(executable=value)
