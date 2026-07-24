"""Tests for validation command execution orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandRunRequest,
    ValidationCommandRunResult,
    ValidationCommandRunStatus,
    ValidationCommandSource,
    ValidationEvidenceStatus,
    ValidationExecutionRequest,
    ValidationScope,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.run_validation import RunValidationCommands
from cline_sdlc.features.operation_policy.domain.policy import OperationDecision, OperationDecisionStatus

if TYPE_CHECKING:
    from pathlib import Path

    from cline_sdlc.features.operation_policy.application.dtos.operation import ClassifyOperationRequest


@dataclass
class RecordingClassifier:
    decision: OperationDecision
    requests: list[ClassifyOperationRequest]

    def execute(self, request: ClassifyOperationRequest) -> OperationDecision:
        self.requests.append(request)
        return self.decision


@dataclass
class RecordingRunner:
    result: ValidationCommandRunResult
    requests: list[ValidationCommandRunRequest]

    def run(self, request: ValidationCommandRunRequest) -> ValidationCommandRunResult:
        self.requests.append(request)
        return self.result


def test_allowed_validation_command_records_passed_evidence(tmp_path: Path) -> None:
    classifier = RecordingClassifier(decision=_allowed_decision(), requests=[])
    runner = RecordingRunner(
        result=ValidationCommandRunResult(status=ValidationCommandRunStatus.EXITED, exit_code=0),
        requests=[],
    )

    result = RunValidationCommands(classifier=classifier, runner=runner).execute(_request(tmp_path))

    assert result.ready
    assert result.evidence[0].status is ValidationEvidenceStatus.PASSED
    assert result.evidence[0].exit_code == 0
    assert result.evidence[0].recorded_at is not None
    assert result.evidence[0].policy_rule_id == "allow_local_validation"
    assert runner.requests[0].working_directory == tmp_path


def test_allowed_validation_command_records_failed_evidence(tmp_path: Path) -> None:
    classifier = RecordingClassifier(decision=_allowed_decision(), requests=[])
    runner = RecordingRunner(
        result=ValidationCommandRunResult(status=ValidationCommandRunStatus.EXITED, exit_code=1),
        requests=[],
    )

    result = RunValidationCommands(classifier=classifier, runner=runner).execute(_request(tmp_path))

    assert not result.ready
    assert result.evidence[0].status is ValidationEvidenceStatus.FAILED
    assert result.evidence[0].exit_code == 1
    assert result.blockers[0].code == "validation_command_failed"


def test_policy_denial_blocks_without_running_command(tmp_path: Path) -> None:
    classifier = RecordingClassifier(
        decision=OperationDecision(
            status=OperationDecisionStatus.APPROVAL_REQUIRED,
            rule_id="deny_network_access",
            summary="network-capable commands require manual approval",
            proposed_operation="curl https://example.test",
        ),
        requests=[],
    )
    runner = RecordingRunner(
        result=ValidationCommandRunResult(status=ValidationCommandRunStatus.EXITED, exit_code=0),
        requests=[],
    )

    result = RunValidationCommands(classifier=classifier, runner=runner).execute(_request(tmp_path))

    assert not result.ready
    assert runner.requests == []
    assert result.evidence[0].status is ValidationEvidenceStatus.BLOCKED
    assert result.evidence[0].exit_code is None
    assert result.blockers[0].code == "validation_command_blocked_by_policy"


def test_timeout_records_blocked_evidence(tmp_path: Path) -> None:
    classifier = RecordingClassifier(decision=_allowed_decision(), requests=[])
    runner = RecordingRunner(
        result=ValidationCommandRunResult(status=ValidationCommandRunStatus.TIMED_OUT, exit_code=None),
        requests=[],
    )

    result = RunValidationCommands(classifier=classifier, runner=runner).execute(_request(tmp_path))

    assert not result.ready
    assert result.evidence[0].status is ValidationEvidenceStatus.BLOCKED
    assert result.evidence[0].exit_code is None
    assert result.blockers[0].code == "validation_command_blocked"


def _request(working_directory: Path) -> ValidationExecutionRequest:
    return ValidationExecutionRequest(
        commands=(_candidate(),),
        working_directory=working_directory,
        timeout_seconds=1.0,
    )


def _candidate() -> ValidationCommandCandidate:
    return ValidationCommandCandidate(
        scope=ValidationScope.FOCUSED,
        command=ValidationCommand(executable="uv", arguments=("run", "pytest", "tests/unit/example.py")),
        source=ValidationCommandSource.EXPLICIT,
        reason="test candidate",
    )


def _allowed_decision() -> OperationDecision:
    return OperationDecision(
        status=OperationDecisionStatus.ALLOWED,
        rule_id="allow_local_validation",
        summary="configured local validation command is allowed",
        proposed_operation="uv run pytest tests/unit/example.py",
    )
