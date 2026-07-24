"""Integration tests for subprocess-backed validation execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.adapters.outbound.validation_runner import (
    SubprocessValidationCommandRunner,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationEvidenceStatus,
    ValidationExecutionRequest,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.run_validation import RunValidationCommands
from cline_sdlc.features.operation_policy.application.use_cases.classify_operation import ClassifyOperation

if TYPE_CHECKING:
    from pathlib import Path


def test_executes_allowed_uv_build_command_and_records_actual_exit(tmp_path: Path) -> None:
    candidate = ValidationCommandCandidate(
        scope=ValidationScope.BROAD,
        command=ValidationCommand(executable="uv", arguments=("build",)),
        source=ValidationCommandSource.DEFAULT,
        reason="local build command is allowed by policy",
    )

    result = RunValidationCommands(
        classifier=ClassifyOperation(),
        runner=SubprocessValidationCommandRunner(),
    ).execute(
        ValidationExecutionRequest(
            commands=(candidate,),
            working_directory=tmp_path,
            timeout_seconds=5.0,
        )
    )

    assert not result.ready
    assert result.evidence[0].status is ValidationEvidenceStatus.FAILED
    assert result.evidence[0].exit_code is not None
    assert result.evidence[0].exit_code != 0
