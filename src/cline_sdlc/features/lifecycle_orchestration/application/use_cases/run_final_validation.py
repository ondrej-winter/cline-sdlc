"""Run authoritative broad checks after all planned slices are committed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.lifecycle_orchestration.application.dtos.final_validation import (
    FinalValidationBlocker,
    FinalValidationRequest,
    FinalValidationResult,
    FinalValidationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationDiscoveryRequest,
    ValidationEvidenceStatus,
    ValidationExecutionRequest,
    ValidationScope,
)

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
        ValidationCommandCandidate,
        ValidationDiscoveryResult,
        ValidationEvidence,
        ValidationExecutionResult,
    )


class ValidationDiscoveryPort(Protocol):
    """Discover authoritative validation commands without executing them."""

    def execute(self, request: ValidationDiscoveryRequest) -> ValidationDiscoveryResult:
        """Return structured validation candidates and discovery blockers."""


class ValidationExecutionPort(Protocol):
    """Classify and execute structured validation commands."""

    def execute(self, request: ValidationExecutionRequest) -> ValidationExecutionResult:
        """Return truthful execution evidence and blockers."""


class RunFinalValidation:
    """Require all authoritative repository-wide checks to pass."""

    def __init__(self, *, discovery: ValidationDiscoveryPort, execution: ValidationExecutionPort) -> None:
        self._discovery = discovery
        self._execution = execution

    def execute(self, request: FinalValidationRequest) -> FinalValidationResult:
        """Return completed only for passing broad evidence under the current approval."""
        approval_failure = _approval_failure(request)
        if approval_failure is not None:
            return _result(request, FinalValidationStatus.BLOCKED, blocker=approval_failure)

        discovery = self._discovery.execute(
            ValidationDiscoveryRequest(
                changed_paths=(),
                include_broad_commands=True,
                include_build_command=True,
            )
        )
        if discovery.blockers:
            return _result(
                request,
                FinalValidationStatus.BLOCKED,
                blocker=FinalValidationBlocker(
                    code="broad_validation_discovery_blocked",
                    summary="authoritative broad validation could not be discovered safely",
                    evidence=_blocker_evidence(discovery),
                ),
            )

        broad_commands: tuple[ValidationCommandCandidate, ...] = tuple(
            command for command in discovery.commands if command.scope is ValidationScope.BROAD
        )
        if not broad_commands or len(broad_commands) != len(discovery.commands):
            return _result(
                request,
                FinalValidationStatus.BLOCKED,
                blocker=FinalValidationBlocker(
                    code="broad_validation_unavailable",
                    summary="final validation requires a non-empty authoritative broad-only command set",
                ),
            )

        execution = self._execution.execute(
            ValidationExecutionRequest(
                commands=broad_commands,
                working_directory=request.working_directory,
                timeout_seconds=request.timeout_seconds,
            )
        )
        if not _all_commands_passed(broad_commands, execution):
            status = (
                FinalValidationStatus.FAILED
                if any(item.status is ValidationEvidenceStatus.FAILED for item in execution.evidence)
                else FinalValidationStatus.BLOCKED
            )
            return _result(
                request,
                status,
                evidence=execution.evidence,
                blocker=FinalValidationBlocker(
                    code=(
                        "broad_validation_failed"
                        if status is FinalValidationStatus.FAILED
                        else "broad_validation_blocked"
                    ),
                    summary="every required broad validation command must run and pass",
                    evidence=_blocker_evidence(execution),
                ),
            )
        return _result(request, FinalValidationStatus.COMPLETED, evidence=execution.evidence)


def _approval_failure(request: FinalValidationRequest) -> FinalValidationBlocker | None:
    if request.specification_digest != request.approval.specification_digest:
        return FinalValidationBlocker(
            code="specification_digest_diverged",
            summary="specification digest no longer matches invocation approval",
        )
    if request.material_digest != request.approval.material_digest:
        return FinalValidationBlocker(
            code="material_digest_diverged",
            summary="plan material digest no longer matches invocation approval",
        )
    return None


def _all_commands_passed(
    broad_commands: tuple[ValidationCommandCandidate, ...],
    execution: ValidationExecutionResult,
) -> bool:
    expected = tuple(command.command for command in broad_commands)
    observed = tuple(item.command for item in execution.evidence)
    return (
        not execution.blockers
        and observed == expected
        and all(
            item.scope is ValidationScope.BROAD
            and item.status is ValidationEvidenceStatus.PASSED
            and item.exit_code == 0
            and item.recorded_at is not None
            for item in execution.evidence
        )
    )


def _blocker_evidence(result: ValidationDiscoveryResult | ValidationExecutionResult) -> str | None:
    evidence = "; ".join(blocker.evidence or blocker.code for blocker in result.blockers)
    return evidence or None


def _result(
    request: FinalValidationRequest,
    status: FinalValidationStatus,
    *,
    evidence: tuple[ValidationEvidence, ...] = (),
    blocker: FinalValidationBlocker | None = None,
) -> FinalValidationResult:
    return FinalValidationResult(
        status=status,
        run_id=request.approval.run_id,
        commit_range=(request.start_commit, request.end_commit),
        evidence=evidence,
        blocker=blocker,
    )
