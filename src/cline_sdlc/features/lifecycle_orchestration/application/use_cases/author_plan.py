"""Coordinate one bounded initial implementation-plan authoring session."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import (
    AuthoredPlanInspectionRequest,
    AuthoredPlanValidationRequest,
)
from cline_sdlc.features.cline_execution.application.dtos.session import ClineSessionRequest
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_authoring import (
    PlanAuthoringBlocker,
    PlanAuthoringRequest,
    PlanAuthoringResult,
    PlanAuthoringStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import (
    SessionAttemptRequest,
    SessionAttemptStatus,
)
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage

if TYPE_CHECKING:
    from cline_sdlc.features.artifact_lifecycle.application.dtos.authored_plan import AuthoredPlanValidationResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import (
        StagePreflightRequest,
        StagePreflightResult,
    )
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.session_attempt import SessionAttemptResult
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
        ValidationDiscoveryRequest,
        ValidationDiscoveryResult,
    )


class StagePreflightPort(Protocol):
    """Published lifecycle boundary for ordered stage preflight."""

    def execute(self, request: StagePreflightRequest) -> StagePreflightResult:
        """Return stage authorization or an actionable blocker."""


class ValidationDiscoveryPort(Protocol):
    """Published lifecycle boundary for authoritative command discovery."""

    def execute(self, request: ValidationDiscoveryRequest) -> ValidationDiscoveryResult:
        """Return structured commands without executing them."""


class SessionAttemptsPort(Protocol):
    """Published lifecycle boundary for bounded Cline session attempts."""

    def execute(self, request: SessionAttemptRequest) -> SessionAttemptResult:
        """Return typed session-attempt evidence."""


class AuthoredPlanContentPort(Protocol):
    """Boundary for reading specification and plan content after authoring."""

    def read(self, request: AuthoredPlanInspectionRequest) -> AuthoredPlanValidationRequest:
        """Return artifact content for independent application validation."""


class AuthoredPlanValidatorPort(Protocol):
    """Published artifact-lifecycle boundary for authored-plan validation."""

    def execute(self, request: AuthoredPlanValidationRequest) -> AuthoredPlanValidationResult:
        """Return structural and digest validation evidence."""


class AuthorPlan:
    """Run one fresh plan-author session and validate its bounded artifact."""

    def __init__(
        self,
        *,
        preflight: StagePreflightPort,
        validation_discovery: ValidationDiscoveryPort,
        session_attempts: SessionAttemptsPort,
        content_reader: AuthoredPlanContentPort,
        plan_validator: AuthoredPlanValidatorPort,
    ) -> None:
        self._preflight = preflight
        self._validation_discovery = validation_discovery
        self._session_attempts = session_attempts
        self._content_reader = content_reader
        self._plan_validator = plan_validator

    def execute(self, request: PlanAuthoringRequest) -> PlanAuthoringResult:
        """Return completion only after one authored plan passes independent validation."""
        preflight_result = self._preflight.execute(request.preflight_request)
        if not preflight_result.authorized:
            return _blocked("plan_authoring_preflight_failed", "plan authoring preflight failed")

        discovery_result = self._validation_discovery.execute(request.validation_discovery_request)
        discovery_failure = _discovery_failure(discovery_result)
        if discovery_failure is not None:
            return discovery_failure

        session_result = self._session_attempts.execute(_session_attempt_request(request, discovery_result))
        session_failure = _session_failure(session_result)
        if session_failure is not None:
            return session_failure

        path_failure = _validate_session_artifact(request, session_result)
        if path_failure is not None:
            return path_failure

        return self._validate_authored_content(request)

    def _validate_authored_content(self, request: PlanAuthoringRequest) -> PlanAuthoringResult:
        specification_path = Path(request.invocation.source.value).as_posix()

        try:
            content = self._content_reader.read(
                AuthoredPlanInspectionRequest(
                    specification_path=specification_path,
                    plan_path=request.output_artifact.path,
                )
            )
        except (OSError, UnicodeError, ValueError) as err:
            return _blocked(
                "authored_plan_content_unavailable",
                "authored plan content could not be read and parsed safely",
                str(err),
            )
        validation = self._plan_validator.execute(content)
        if not validation.valid:
            evidence = "; ".join(blocker.evidence or blocker.code for blocker in validation.blockers)
            return _blocked("authored_plan_invalid", "authored plan failed independent validation", evidence)
        return PlanAuthoringResult(
            status=PlanAuthoringStatus.COMPLETED,
            output_paths=(request.output_artifact.path,),
            specification_digest=validation.specification_digest,
            material_digest=validation.material_digest,
        )


def _discovery_failure(discovery_result: ValidationDiscoveryResult) -> PlanAuthoringResult | None:
    if discovery_result.ready and discovery_result.commands:
        return None
    evidence = "; ".join(blocker.code for blocker in discovery_result.blockers) or "no validation commands"
    return _blocked(
        "validation_discovery_failed",
        "plan authoring requires authoritative validation commands",
        evidence,
    )


def _session_attempt_request(
    request: PlanAuthoringRequest,
    discovery: ValidationDiscoveryResult,
) -> SessionAttemptRequest:
    return SessionAttemptRequest(
        session_request=ClineSessionRequest(
            command=(request.invocation.cline_command, "--json", "--task", _prompt(request, discovery)),
            working_directory=request.preflight_request.repository_request.working_directory,
            timeout_seconds=request.invocation.timeout_seconds,
        ),
        repository_request=request.preflight_request.repository_request,
    )


def _prompt(request: PlanAuthoringRequest, discovery: ValidationDiscoveryResult) -> str:
    specification_path = Path(request.invocation.source.value).as_posix()
    commands = "\n".join(f"- {candidate.command.display}" for candidate in discovery.commands)
    return "\n".join(
        (
            "Use the planning-and-task-breakdown skill to author an implementation plan only.",
            "Inspect repository rules and existing implementation patterns before defining slices.",
            "Stop after writing the initial plan; do not review or implement it.",
            f"Lifecycle stage: {LifecycleStage.PLAN_CREATION_AND_REVIEW.value}",
            f"Read the accepted specification from: {specification_path}",
            f"Write the initial plan to: {request.output_artifact.path}",
            "Record these authoritative validation commands in the plan:",
            commands,
        )
    )


def _session_failure(session_result: SessionAttemptResult) -> PlanAuthoringResult | None:
    if session_result.status is SessionAttemptStatus.COMPLETED and session_result.terminal_session_result is not None:
        return None
    blocker = session_result.blocker
    return PlanAuthoringResult(
        status=PlanAuthoringStatus.BLOCKED
        if session_result.status is SessionAttemptStatus.BLOCKED
        else PlanAuthoringStatus.FAILED,
        blocker=PlanAuthoringBlocker(
            code=blocker.code if blocker is not None else "plan_author_session_failed",
            summary=blocker.summary if blocker is not None else "plan author session did not complete",
        ),
    )


def _validate_session_artifact(
    request: PlanAuthoringRequest,
    session_result: SessionAttemptResult,
) -> PlanAuthoringResult | None:
    terminal_result = session_result.terminal_session_result
    if terminal_result is None or len(terminal_result.terminal_outcomes) != 1:
        return _blocked("plan_terminal_outcome_unavailable", "plan authoring requires one typed session outcome")
    outcome = terminal_result.terminal_outcomes[0]
    if outcome.session_role is not SessionRole.PLAN_AUTHOR:
        return _blocked("unexpected_session_role", "initial plan authoring must complete as a plan_author session")
    expected_path = request.output_artifact.path
    if outcome.artifact_paths != (expected_path,) or session_result.changed_paths != (expected_path,):
        return _blocked(
            "plan_artifact_not_verified",
            "plan authoring must report exactly one changed selected plan artifact",
            expected_path,
        )
    return None


def _blocked(code: str, summary: str, evidence: str | None = None) -> PlanAuthoringResult:
    return PlanAuthoringResult(
        status=PlanAuthoringStatus.BLOCKED,
        blocker=PlanAuthoringBlocker(code=code, summary=summary, evidence=evidence),
    )
