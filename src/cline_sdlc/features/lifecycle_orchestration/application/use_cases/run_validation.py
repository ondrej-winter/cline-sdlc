"""Classify and execute validation command candidates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommandCandidate,
    ValidationCommandRunRequest,
    ValidationCommandRunResult,
    ValidationCommandRunStatus,
    ValidationDiscoveryBlocker,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationExecutionRequest,
    ValidationExecutionResult,
)
from cline_sdlc.features.operation_policy.application.dtos.operation import ClassifyOperationRequest

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.ports.validation_runner import (
        ValidationCommandRunnerPort,
    )
    from cline_sdlc.features.operation_policy.domain.policy import OperationDecision


class OperationClassifierPort(Protocol):
    """Published operation-policy application boundary used by validation execution."""

    def execute(self, request: ClassifyOperationRequest) -> OperationDecision:
        """Return a balanced-profile decision for one command operation."""


class RunValidationCommands:
    """Classify validation commands, run allowed commands, and record truthful evidence."""

    def __init__(self, *, classifier: OperationClassifierPort, runner: ValidationCommandRunnerPort) -> None:
        self._classifier = classifier
        self._runner = runner

    def execute(self, request: ValidationExecutionRequest) -> ValidationExecutionResult:
        """Return execution evidence without inventing successful results."""
        evidence: list[ValidationEvidence] = []
        blockers: list[ValidationDiscoveryBlocker] = []
        for candidate in request.commands:
            decision = self._classifier.execute(
                ClassifyOperationRequest(
                    executable=candidate.command.executable,
                    arguments=candidate.command.arguments,
                )
            )
            if not decision.is_allowed:
                blockers.append(
                    ValidationDiscoveryBlocker(
                        code="validation_command_blocked_by_policy",
                        summary=decision.summary,
                        evidence=decision.proposed_operation,
                    )
                )
                evidence.append(
                    ValidationEvidence(
                        scope=candidate.scope,
                        command=candidate.command,
                        status=ValidationEvidenceStatus.BLOCKED,
                        summary=decision.summary,
                        recorded_at=_now_utc(),
                        policy_rule_id=decision.rule_id,
                    )
                )
                continue

            run_result = self._runner.run(
                ValidationCommandRunRequest(
                    command=candidate.command,
                    working_directory=request.working_directory,
                    timeout_seconds=request.timeout_seconds,
                )
            )
            command_evidence = _evidence_from_run(candidate, run_result, policy_rule_id=decision.rule_id)
            evidence.append(command_evidence)
            if command_evidence.status is not ValidationEvidenceStatus.PASSED:
                blockers.append(
                    ValidationDiscoveryBlocker(
                        code=f"validation_command_{command_evidence.status.value}",
                        summary=command_evidence.summary,
                        evidence=candidate.command.display,
                    )
                )
        return ValidationExecutionResult(evidence=tuple(evidence), blockers=tuple(blockers))


def _evidence_from_run(
    candidate: ValidationCommandCandidate,
    run_result: ValidationCommandRunResult,
    *,
    policy_rule_id: str,
) -> ValidationEvidence:
    if run_result.status is ValidationCommandRunStatus.TIMED_OUT:
        return ValidationEvidence(
            scope=candidate.scope,
            command=candidate.command,
            status=ValidationEvidenceStatus.BLOCKED,
            summary="validation command timed out before producing an exit code",
            recorded_at=_now_utc(),
            policy_rule_id=policy_rule_id,
        )
    if run_result.status is ValidationCommandRunStatus.START_FAILED:
        return ValidationEvidence(
            scope=candidate.scope,
            command=candidate.command,
            status=ValidationEvidenceStatus.BLOCKED,
            summary="validation command could not be started",
            recorded_at=_now_utc(),
            policy_rule_id=policy_rule_id,
        )
    exit_code = run_result.exit_code
    if exit_code == 0:
        return ValidationEvidence(
            scope=candidate.scope,
            command=candidate.command,
            status=ValidationEvidenceStatus.PASSED,
            summary="validation command passed",
            exit_code=exit_code,
            recorded_at=_now_utc(),
            policy_rule_id=policy_rule_id,
        )
    return ValidationEvidence(
        scope=candidate.scope,
        command=candidate.command,
        status=ValidationEvidenceStatus.FAILED,
        summary="validation command failed",
        exit_code=exit_code,
        recorded_at=_now_utc(),
        policy_rule_id=policy_rule_id,
    )


def _now_utc() -> datetime:
    return datetime.now(UTC)
