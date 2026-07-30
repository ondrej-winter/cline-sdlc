"""Execute one approved implementation slice without deciding commit eligibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_execution import (
    SliceExecutionBlocker,
    SliceExecutionRequest,
    SliceExecutionResult,
    SliceExecutionStatus,
    SlicePlanActMediation,
    SlicePlanActStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationEvidence,
    ValidationExecutionRequest,
)

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import SessionAttemptResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import ValidationExecutionResult
    from cline_sdlc.features.operation_policy.application.dtos.operation import ClassifyOperationRequest
    from cline_sdlc.features.operation_policy.domain.policy import OperationDecision


class SessionAttemptsPort(Protocol):
    """Published boundary for bounded process/protocol session attempts."""

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        """Return typed observations for one fresh bounded session."""


class OperationClassifierPort(Protocol):
    """Published operation-policy boundary for proposed slice operations."""

    def execute(self, request: ClassifyOperationRequest) -> OperationDecision:
        """Return a fail-closed balanced-profile decision."""


class ValidationExecutionPort(Protocol):
    """Published boundary for independent focused validation execution."""

    def execute(self, request: ValidationExecutionRequest) -> ValidationExecutionResult:
        """Return truthful command evidence and blockers."""


@dataclass
class _ExecutionEvidence:
    """Mutable evidence accumulated within one application transaction."""

    sessions: list[SessionAttemptResult] = field(default_factory=list)
    decisions: tuple[OperationDecision, ...] = ()
    validation_evidence: tuple[ValidationEvidence, ...] = ()
    repair_attempts: int = 0

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(path for session in self.sessions for path in session.changed_paths))


class ExecuteSlice:
    """Run one slice session and at most one focused-validation repair session."""

    def __init__(
        self,
        *,
        session_attempts: SessionAttemptsPort,
        operation_classifier: OperationClassifierPort,
        validation_execution: ValidationExecutionPort,
    ) -> None:
        self._session_attempts = session_attempts
        self._operation_classifier = operation_classifier
        self._validation_execution = validation_execution

    def execute(self, request: SliceExecutionRequest) -> SliceExecutionResult:
        """Return evidence for later reconciliation without staging or committing changes."""
        initial_failure = self._initial_failure(request)
        if initial_failure is not None:
            return initial_failure

        plan_act_failure = _plan_act_failure(request)
        if plan_act_failure is not None:
            return plan_act_failure

        evidence = _ExecutionEvidence(
            decisions=tuple(self._operation_classifier.execute(operation) for operation in request.operations)
        )
        operation_failure = _operation_failure(evidence)
        if operation_failure is not None:
            return operation_failure

        first_session = self._run_session(request, repair=False)
        evidence.sessions.append(first_session)
        session_failure = _session_failure(first_session, expected_role=request.session_role, evidence=evidence)
        if session_failure is not None:
            return session_failure

        validation = self._run_validation(request)
        evidence.validation_evidence = validation.evidence
        if validation.ready:
            return _result(SliceExecutionStatus.COMPLETED, evidence)

        return self._repair_failed_validation(request, evidence)

    def _repair_failed_validation(
        self,
        request: SliceExecutionRequest,
        evidence: _ExecutionEvidence,
    ) -> SliceExecutionResult:
        """Run the single permitted repair session and final focused validation."""
        repair_session = self._run_session(request, repair=True)
        evidence.sessions.append(repair_session)
        evidence.repair_attempts = 1
        repair_failure = _session_failure(repair_session, expected_role=request.session_role, evidence=evidence)
        if repair_failure is not None:
            return repair_failure

        repaired_validation = self._run_validation(request)
        evidence.validation_evidence = repaired_validation.evidence
        if not repaired_validation.ready:
            return _result(
                SliceExecutionStatus.FAILED,
                evidence,
                blocker=SliceExecutionBlocker(
                    "focused_validation_repair_exhausted",
                    "focused validation still failed after the single permitted repair attempt",
                    evidence=_validation_blocker_evidence(repaired_validation),
                ),
            )
        return _result(SliceExecutionStatus.COMPLETED, evidence)

    def _initial_failure(self, request: SliceExecutionRequest) -> SliceExecutionResult | None:
        if request.specification_digest != request.approval.specification_digest:
            return _simple_blocker(
                "specification_digest_diverged",
                "specification digest no longer matches invocation approval",
            )
        if request.material_digest != request.approval.material_digest:
            return _simple_blocker(
                "material_digest_diverged",
                "plan material digest no longer matches invocation approval",
            )
        return None

    def _run_session(self, request: SliceExecutionRequest, *, repair: bool) -> SessionAttemptResult:
        return self._session_attempts.execute(
            SessionAttemptRequest(
                session_request=ClineSessionRequest(
                    command=(request.cline_command, "--json", _prompt(request, repair=repair)),
                    working_directory=request.working_directory,
                    timeout_seconds=request.timeout_seconds,
                ),
                repository_request=request.repository_request,
            )
        )

    def _run_validation(self, request: SliceExecutionRequest) -> ValidationExecutionResult:
        return self._validation_execution.execute(
            ValidationExecutionRequest(
                commands=request.focused_validation_commands,
                working_directory=request.working_directory,
            )
        )


def _operation_failure(evidence: _ExecutionEvidence) -> SliceExecutionResult | None:
    denied = next((decision for decision in evidence.decisions if not decision.is_allowed), None)
    if denied is None:
        return None
    return _result(
        SliceExecutionStatus.BLOCKED,
        evidence,
        blocker=SliceExecutionBlocker(
            code="slice_operation_not_authorized",
            summary=denied.summary,
            evidence=denied.proposed_operation,
        ),
    )


def _plan_act_failure(request: SliceExecutionRequest) -> SliceExecutionResult | None:
    if request.session_role is not SessionRole.IMPLEMENTATION:
        return None
    mediation = request.plan_act_mediation
    if mediation is None:
        return _simple_blocker(
            "slice_plan_act_support_unproven",
            "implementation sessions require proven SDK Plan/Act mediation before acting",
        )
    mismatch = _plan_act_scope_mismatch(request, mediation)
    if mismatch is not None:
        return mismatch
    if mediation.status is SlicePlanActStatus.NEEDS_USER_INPUT:
        return _simple_blocker(
            "slice_plan_act_needs_user_input",
            mediation.summary,
            evidence=mediation.diagnostic_reference,
        )
    if mediation.status is SlicePlanActStatus.UNPROVEN:
        return _simple_blocker(
            "slice_plan_act_support_unproven",
            mediation.summary,
            evidence=mediation.diagnostic_reference,
        )
    return None


def _plan_act_scope_mismatch(
    request: SliceExecutionRequest,
    mediation: SlicePlanActMediation,
) -> SliceExecutionResult | None:
    expected = {
        "run_id": request.approval.run_id,
        "task_id": request.selection.task_id,
        "slice_id": request.selection.slice_id,
        "specification_digest": request.specification_digest,
        "material_digest": request.material_digest,
        "operation_policy": request.approval.profile,
    }
    actual = {
        "run_id": mediation.run_id,
        "task_id": mediation.task_id,
        "slice_id": mediation.slice_id,
        "specification_digest": mediation.specification_digest,
        "material_digest": mediation.material_digest,
        "operation_policy": mediation.operation_policy,
    }
    mismatched_fields = tuple(field for field, expected_value in expected.items() if actual[field] != expected_value)
    if not mismatched_fields:
        return None
    return _simple_blocker(
        "slice_plan_act_scope_mismatch",
        "Plan/Act mediation evidence does not match the approved session, slice, digests, and policy",
        evidence=", ".join(mismatched_fields),
    )


def _prompt(request: SliceExecutionRequest, *, repair: bool) -> str:
    operation_summaries = tuple(
        " ".join((operation.executable, *operation.arguments)) for operation in request.operations
    )
    expected_paths = request.expected_paths or ("No pre-authorized path list; report every observed changed path.",)
    if request.session_role is SessionRole.REMEDIATION:
        responsibility = (
            "Correct only the approved final-review finding and update its progress-only remediation record."
        )
    elif repair:
        responsibility = "Repair only the current slice so its focused validation passes."
    else:
        responsibility = "Implement only the current approved slice, including its focused tests and progress update."
    return "\n".join(
        (
            responsibility,
            "Use the incremental-implementation and test-driven-development skills where applicable.",
            "Do not work on later slices, stage files, create commits, or change material plan content.",
            f"Return exactly one typed {request.session_role.value} terminal outcome "
            "with changed paths and validation run.",
            f"Approved run: {request.approval.run_id}",
            f"Current task: {request.selection.task_id}",
            f"Current slice: {request.selection.slice_id}",
            f"Specification path: {request.specification_path}",
            f"Plan path: {request.plan_path}",
            f"Specification digest: {request.specification_digest}",
            f"Plan material digest: {request.material_digest}",
            "Expected path scope:",
            *(f"- {path}" for path in expected_paths),
            "Pre-classified planned operations:",
            *(f"- {operation}" for operation in operation_summaries),
            "Focused validation commands:",
            *(f"- {candidate.command.display}" for candidate in request.focused_validation_commands),
            "Accepted specification:",
            request.specification_content,
            "Ready implementation plan:",
            request.plan_content,
        )
    )


def _session_failure(
    result: SessionAttemptResult,
    *,
    expected_role: SessionRole,
    evidence: _ExecutionEvidence,
) -> SliceExecutionResult | None:
    if result.status is not SessionAttemptStatus.COMPLETED or result.terminal_session_result is None:
        blocker = result.blocker
        return _result(
            (
                SliceExecutionStatus.INTERRUPTED
                if result.status is SessionAttemptStatus.INTERRUPTED
                else (
                    SliceExecutionStatus.BLOCKED
                    if result.status is SessionAttemptStatus.BLOCKED
                    else SliceExecutionStatus.FAILED
                )
            ),
            evidence,
            blocker=SliceExecutionBlocker(
                code=blocker.code if blocker is not None else "slice_session_failed",
                summary=blocker.summary if blocker is not None else "slice session did not complete",
            ),
        )
    outcome = result.terminal_session_result.terminal_outcomes[0]
    if outcome.session_role is not expected_role:
        return _result(
            SliceExecutionStatus.BLOCKED,
            evidence,
            blocker=SliceExecutionBlocker(
                code="unexpected_slice_session_role",
                summary=f"slice execution requires a {expected_role.value} session outcome",
            ),
        )
    return None


def _result(
    status: SliceExecutionStatus,
    evidence: _ExecutionEvidence,
    *,
    blocker: SliceExecutionBlocker | None = None,
) -> SliceExecutionResult:
    return SliceExecutionResult(
        status=status,
        session_attempts=tuple(evidence.sessions),
        operation_decisions=evidence.decisions,
        validation_evidence=evidence.validation_evidence,
        changed_paths=evidence.changed_paths,
        repair_attempts=evidence.repair_attempts,
        blocker=blocker,
    )


def _simple_blocker(code: str, summary: str, *, evidence: str | None = None) -> SliceExecutionResult:
    return _result(
        SliceExecutionStatus.BLOCKED,
        _ExecutionEvidence(),
        blocker=SliceExecutionBlocker(code=code, summary=summary, evidence=evidence),
    )


def _validation_blocker_evidence(validation: ValidationExecutionResult) -> str | None:
    evidence = "; ".join(blocker.evidence or blocker.code for blocker in validation.blockers)
    return evidence or None
