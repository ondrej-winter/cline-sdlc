"""CLI parsing adapter for supervised lifecycle runner invocations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Never

from cline_sdlc import __version__
from cline_sdlc.features.artifact_lifecycle.adapters.inbound.filesystem_authored_plan import (
    FilesystemAuthoredPlanContentReader,
)
from cline_sdlc.features.artifact_lifecycle.adapters.inbound.filesystem_plan_review import (
    FilesystemPlanReviewProgressWriter,
)
from cline_sdlc.features.artifact_lifecycle.adapters.inbound.state_yaml import (
    StrictStateYAMLError,
    parse_plan_state_from_markdown,
)
from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationBlocker,
    ArtifactLocationResult,
    SelectArtifactLocationRequest,
)
from cline_sdlc.features.artifact_lifecycle.application.use_cases.select_artifact_location import SelectArtifactLocation
from cline_sdlc.features.artifact_lifecycle.application.use_cases.validate_authored_plan import ValidateAuthoredPlan
from cline_sdlc.features.artifact_lifecycle.domain.digests import compute_specification_digest
from cline_sdlc.features.artifact_lifecycle.domain.plan_state import PlanPhase, PlanState, ReviewReadiness
from cline_sdlc.features.cline_execution.adapters.outbound.cli_capability_probe import SubprocessClineCapabilityProbe
from cline_sdlc.features.cline_execution.adapters.outbound.interactive_process import AttachedTtyClineSessionRunner
from cline_sdlc.features.cline_execution.application.dtos.preflight import ClinePreflightRequest
from cline_sdlc.features.cline_execution.application.use_cases.preflight import PreflightClineCapabilities
from cline_sdlc.features.lifecycle_orchestration.adapters.inbound.plan_tasks import (
    PlanTaskParseError,
    parse_plan_task_definitions,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.idea_stage import (
    IdeaRefinementRequest,
    IdeaRefinementResult,
    IdeaRefinementStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import (
    InvocationParseError,
    InvocationRequest,
    InvocationSource,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_authoring import (
    PlanAuthoringRequest,
    PlanAuthoringResult,
    PlanAuthoringStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.plan_review import (
    PlanReviewRequest,
    PlanReviewResult,
    PlanReviewStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import StagePreflightRequest
from cline_sdlc.features.lifecycle_orchestration.application.dtos.slice_selection import (
    PartialSliceProgress,
    SliceCompletionEvidence,
    SliceSelectionRequest,
    SliceSelectionStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.specification_stage import (
    SpecificationCreationRequest,
    SpecificationCreationResult,
    SpecificationCreationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.terminal_result import TerminalBlocker, TerminalResult
from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import ValidationDiscoveryRequest
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.author_plan import AuthorPlan
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.complete_plan_review import CompletePlanReview
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.create_specification import CreateSpecification
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.discover_validation import (
    DiscoverValidationCommands,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.preflight_stage import PreflightLifecycleStage
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.refine_idea import RefineIdea
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.review_plan import ReviewPlan
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.revise_plan import RevisePlan
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.run_session_attempts import RunSessionAttempts
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_slice import SelectSlice
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_stage import SelectLifecycleStage
from cline_sdlc.features.lifecycle_orchestration.domain.stage import LifecycleStage
from cline_sdlc.features.lifecycle_orchestration.domain.terminal_result import (
    TerminalStatus,
    exit_category_for_status,
)
from cline_sdlc.features.repository_coordination.adapters.outbound.git_cli import GitCliRepositoryInspector
from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionRequest

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cline_sdlc.features.repository_coordination.application.dtos.repository import RepositoryInspectionResult

DEFAULT_TIMEOUT_SECONDS = 1_800.0
INVALID_TIMEOUT_MESSAGE = "--timeout must be a finite positive number of seconds"
USAGE_ERROR_REASON = "invalid_invocation"
DRY_RUN_REASON = "dry_run_preview"
UNSUPPORTED_STAGE_REASON = "stage_not_wired"
IDEA_COMPLETED_REASON = "idea_brief_accepted"
IDEA_BLOCKED_REASON = "idea_refinement_blocked"
IDEA_FAILED_REASON = "idea_refinement_failed"
SPEC_COMPLETED_REASON = "specification_accepted"
SPEC_BLOCKED_REASON = "specification_creation_blocked"
SPEC_FAILED_REASON = "specification_creation_failed"
PLAN_COMPLETED_REASON = "plan_ready"
PLAN_BLOCKED_REASON = "plan_creation_and_review_blocked"
PLAN_FAILED_REASON = "plan_creation_and_review_failed"
IMPLEMENTATION_COMPLETED_REASON = "plan_implementation_completed"
IMPLEMENTATION_BLOCKED_REASON = "plan_implementation_blocked"
IMPLEMENTATION_FAILED_REASON = "plan_implementation_failed"
_SAFE_STEM_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_SPECIFICATION_REFERENCE_PATTERN = re.compile(r"`(?P<path>docs/specs/[^`]+\.md)`")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


@dataclass(frozen=True)
class ParsedCliInvocation:
    """Successful CLI parse result for one supervised lifecycle invocation."""

    request: InvocationRequest


@dataclass(frozen=True)
class CliRunResult:
    """Rendered CLI result and process exit code for one invocation."""

    exit_code: int
    stdout: str
    stderr: str
    terminal_result: TerminalResult


@dataclass(frozen=True)
class _InteractiveStageRuntime:
    """Shared CLI composition for one attached interactive lifecycle stage."""

    output_artifact: ArtifactLocationResult
    preflight_request: StagePreflightRequest
    preflight: PreflightLifecycleStage
    session_attempts: RunSessionAttempts


@dataclass(frozen=True)
class _InteractiveStageConfig:
    """Stage-specific knobs for otherwise shared interactive CLI wiring."""

    artifact_kind: ArtifactKind
    artifact_stem: str
    required_skill: str
    blocked_reason: str


def parse_cli_invocation(argv: Sequence[str], *, cwd: Path | None = None) -> ParsedCliInvocation | InvocationParseError:
    """Parse CLI arguments into an application-owned invocation request."""
    parser = _build_parser()
    try:
        namespace = parser.parse_args(list(argv))
        timeout_seconds = _parse_timeout(namespace.timeout)
        request = _request_from_namespace(namespace, cwd=cwd or Path.cwd(), timeout_seconds=timeout_seconds)
    except ValueError as err:
        return InvocationParseError(message=str(err))

    return ParsedCliInvocation(request=SelectLifecycleStage().execute(request))


def run_cli_invocation(argv: Sequence[str], *, cwd: Path | None = None) -> CliRunResult:
    """Run one supervised lifecycle CLI invocation."""
    if list(argv) == ["--version"]:
        result = TerminalResult(status=TerminalStatus.COMPLETED, reason="version_displayed")
        return _version_cli_result(result)

    parsed = parse_cli_invocation(argv, cwd=cwd)
    if isinstance(parsed, InvocationParseError):
        result = TerminalResult(
            status=TerminalStatus.INVALID_INVOCATION,
            reason=USAGE_ERROR_REASON,
            blocker=TerminalBlocker(code="invalid_invocation", summary=parsed.message),
        )
        return _render_cli_result(result, emit_json=_argv_requests_json(argv))

    if parsed.request.dry_run:
        result = _dry_run_result(parsed.request)
        return _render_cli_result(result, emit_json=parsed.request.emit_json)

    result = _run_selected_stage(parsed.request, cwd=cwd or Path.cwd())
    return _render_cli_result(result, emit_json=parsed.request.emit_json)


def _run_selected_stage(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
    """Dispatch one parsed invocation to its selected lifecycle stage."""
    if request.stage is LifecycleStage.IDEA_REFINEMENT:
        return _run_idea_refinement(request, cwd=cwd)
    if request.stage is LifecycleStage.SPECIFICATION_CREATION:
        return _run_specification_creation(request, cwd=cwd)
    if request.stage is LifecycleStage.PLAN_CREATION_AND_REVIEW:
        return _run_plan_creation_and_review(request, cwd=cwd)
    if request.stage is LifecycleStage.PLAN_IMPLEMENTATION:
        return _run_plan_implementation(request, cwd=cwd)
    return _unsupported_stage_result(request)


def _version_cli_result(result: TerminalResult) -> CliRunResult:
    return CliRunResult(
        exit_code=int(exit_category_for_status(result.status)),
        stdout=f"cline-sdlc {__version__}\n",
        stderr="",
        terminal_result=result,
    )


def _unsupported_stage_result(request: InvocationRequest) -> TerminalResult:
    return TerminalResult(
        status=TerminalStatus.BLOCKED,
        reason=UNSUPPORTED_STAGE_REASON,
        stage=request.stage,
        input_path=_input_path(request),
        blocker=TerminalBlocker(
            code="stage_not_wired",
            summary="This lifecycle stage is not currently wired through the supervised CLI runner.",
        ),
    )


def _dry_run_result(request: InvocationRequest) -> TerminalResult:
    return TerminalResult(
        status=TerminalStatus.BLOCKED,
        reason=DRY_RUN_REASON,
        stage=request.stage,
        input_path=_input_path(request),
        blocker=TerminalBlocker(
            code="dry_run_only",
            summary="Dry run selected; lifecycle execution was not started.",
        ),
    )


def _run_idea_refinement(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
    runtime = _interactive_stage_runtime(
        request,
        cwd=cwd,
        config=_InteractiveStageConfig(
            artifact_kind=ArtifactKind.IDEA_BRIEF,
            artifact_stem=_artifact_stem(str(request.source.value)),
            required_skill="idea-refine",
            blocked_reason=IDEA_BLOCKED_REASON,
        ),
    )
    if isinstance(runtime, TerminalResult):
        return runtime
    result = RefineIdea(preflight=runtime.preflight, session_attempts=runtime.session_attempts).execute(
        IdeaRefinementRequest(
            invocation=request,
            preflight_request=runtime.preflight_request,
            output_artifact=runtime.output_artifact,
        )
    )
    return _terminal_result_from_idea_result(request, result)


def _run_specification_creation(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
    idea_path = Path(request.source.value)
    runtime = _interactive_stage_runtime(
        request,
        cwd=cwd,
        config=_InteractiveStageConfig(
            artifact_kind=ArtifactKind.SPECIFICATION,
            artifact_stem=_artifact_stem(idea_path.stem.removesuffix("-idea")),
            required_skill="spec-driven-development",
            blocked_reason=SPEC_BLOCKED_REASON,
        ),
    )
    if isinstance(runtime, TerminalResult):
        return runtime
    result = CreateSpecification(preflight=runtime.preflight, session_attempts=runtime.session_attempts).execute(
        SpecificationCreationRequest(
            invocation=request,
            preflight_request=runtime.preflight_request,
            output_artifact=runtime.output_artifact,
        )
    )
    return _terminal_result_from_specification_result(request, result)


def _run_plan_creation_and_review(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
    spec_path = Path(request.source.value)
    runtime = _interactive_stage_runtime(
        request,
        cwd=cwd,
        config=_InteractiveStageConfig(
            artifact_kind=ArtifactKind.PLAN,
            artifact_stem=_artifact_stem(spec_path.stem.removesuffix("-spec")),
            required_skill="planning-and-task-breakdown",
            blocked_reason=PLAN_BLOCKED_REASON,
        ),
    )
    if isinstance(runtime, TerminalResult):
        return runtime

    repository_root = runtime.preflight_request.repository_request.working_directory
    content_reader = FilesystemAuthoredPlanContentReader(repository_root=repository_root)
    plan_validator = ValidateAuthoredPlan()
    repository_inspector = GitCliRepositoryInspector()
    session_attempts = RunSessionAttempts(
        runner=AttachedTtyClineSessionRunner(),
        repository_inspector=repository_inspector,
    )

    authoring = AuthorPlan(
        preflight=runtime.preflight,
        validation_discovery=DiscoverValidationCommands(),
        session_attempts=session_attempts,
        content_reader=content_reader,
        plan_validator=plan_validator,
    ).execute(
        PlanAuthoringRequest(
            invocation=request,
            preflight_request=runtime.preflight_request,
            validation_discovery_request=ValidationDiscoveryRequest(changed_paths=(runtime.output_artifact.path,)),
            output_artifact=runtime.output_artifact,
        )
    )
    if authoring.status is not PlanAuthoringStatus.COMPLETED:
        return _terminal_result_from_plan_authoring_result(request, authoring)

    reviewer = ReviewPlan(
        content_reader=content_reader,
        plan_validator=plan_validator,
        session_attempts=session_attempts,
        progress_writer=FilesystemPlanReviewProgressWriter(repository_root=repository_root),
        clock=_SystemClock(),
    )
    review = CompletePlanReview(
        reviewer=reviewer,
        reviser=RevisePlan(
            content_reader=content_reader,
            plan_validator=plan_validator,
            session_attempts=session_attempts,
        ),
    ).execute(
        PlanReviewRequest(
            invocation=request,
            preflight_request=runtime.preflight_request,
            plan_path=runtime.output_artifact.path,
        )
    )
    return _terminal_result_from_plan_review_result(
        request,
        review,
        specification_digest=authoring.specification_digest,
    )


def _run_plan_implementation(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
    """Run or safely block the supervised implementation-plan stage."""
    plan_path = Path(request.source.value)
    try:
        plan_content = plan_path.read_text(encoding="utf-8")
        plan_state = _plan_state_from_markdown_or_legacy_plan(
            plan_content,
            plan_path=plan_path,
            repository_root=cwd,
        )
    except (OSError, UnicodeError, ValueError) as err:
        return TerminalResult(
            status=TerminalStatus.BLOCKED,
            reason=IMPLEMENTATION_BLOCKED_REASON,
            stage=request.stage,
            input_path=_input_path(request),
            blocker=TerminalBlocker(
                code="plan_state_unavailable",
                summary="plan implementation requires a valid cline-sdlc-state block before execution can start",
                evidence=str(err),
            ),
        )

    try:
        tasks = parse_plan_task_definitions(plan_content)
    except PlanTaskParseError as err:
        return TerminalResult(
            status=TerminalStatus.BLOCKED,
            reason=IMPLEMENTATION_BLOCKED_REASON,
            stage=request.stage,
            input_path=_input_path(request),
            plan_material_digest=plan_state.material_digest,
            specification_digest=plan_state.specification_digest,
            blocker=TerminalBlocker(
                code="plan_task_definitions_unavailable",
                summary="plan implementation requires structured task and slice metadata before execution can start",
                evidence=str(err),
            ),
        )

    selection = SelectSlice().execute(
        SliceSelectionRequest(
            tasks=tasks,
            completed_slice_ids=plan_state.completed_slices,
            completion_evidence=tuple(
                SliceCompletionEvidence(slice_id=slice_id, completed=True) for slice_id in plan_state.completed_slices
            ),
            partial_slice=PartialSliceProgress(
                task_id=plan_state.current_task,
                slice_id=plan_state.current_slice,
                paths=plan_state.partial_slice_paths,
            )
            if plan_state.current_task is not None and plan_state.current_slice is not None
            else None,
        )
    )
    if selection.status is SliceSelectionStatus.BLOCKED:
        blocker = selection.blocker
        return TerminalResult(
            status=TerminalStatus.BLOCKED,
            reason=IMPLEMENTATION_BLOCKED_REASON,
            stage=request.stage,
            input_path=_input_path(request),
            plan_material_digest=plan_state.material_digest,
            specification_digest=plan_state.specification_digest,
            blocker=TerminalBlocker(
                code=blocker.code if blocker is not None else "slice_selection_blocked",
                summary=blocker.summary if blocker is not None else "plan task metadata did not select work safely",
                evidence=blocker.evidence if blocker is not None else None,
            ),
        )
    if selection.status is SliceSelectionStatus.COMPLETE:
        return TerminalResult(
            status=TerminalStatus.COMPLETED,
            reason=IMPLEMENTATION_COMPLETED_REASON,
            stage=request.stage,
            input_path=_input_path(request),
            output_paths=(plan_path.as_posix(),),
            plan_material_digest=plan_state.material_digest,
            specification_digest=plan_state.specification_digest,
        )

    selected = selection.selection
    evidence = f"{selected.task_id}:{selected.slice_id}" if selected is not None else plan_state.work_id
    return TerminalResult(
        status=TerminalStatus.BLOCKED,
        reason=IMPLEMENTATION_BLOCKED_REASON,
        stage=request.stage,
        input_path=_input_path(request),
        plan_material_digest=plan_state.material_digest,
        specification_digest=plan_state.specification_digest,
        blocker=TerminalBlocker(
            code="plan_implementation_runtime_unavailable",
            summary="plan task metadata is available but implementation runtime composition is not yet wired",
            evidence=evidence,
        ),
    )


def _plan_state_from_markdown_or_legacy_plan(markdown: str, *, plan_path: Path, repository_root: Path) -> PlanState:
    try:
        return parse_plan_state_from_markdown(markdown)
    except StrictStateYAMLError as err:
        if str(err) != "plan must contain exactly one cline-sdlc-state block":
            raise
    specification_path = _legacy_plan_specification_path(markdown, repository_root=repository_root)
    specification_content = specification_path.read_bytes()
    specification_digest = compute_specification_digest(specification_content)
    material_digest = _legacy_plan_material_digest(
        plan_markdown=markdown,
        specification=_repository_relative_path(specification_path, repository_root=repository_root),
        specification_digest=specification_digest,
    )
    now = datetime.now(UTC)
    return PlanState(
        work_id=_legacy_plan_work_id(plan_path),
        phase=PlanPhase.READY,
        specification=_repository_relative_path(specification_path, repository_root=repository_root),
        specification_digest=specification_digest,
        plan_revision=1,
        review_iteration=1,
        review_readiness=ReviewReadiness.READY,
        material_digest=material_digest,
        created_at=now,
        updated_at=now,
    )


def _legacy_plan_specification_path(markdown: str, *, repository_root: Path) -> Path:
    matches = tuple(_SPECIFICATION_REFERENCE_PATTERN.finditer(markdown))
    if not matches:
        message = "legacy plan must reference an accepted specification under docs/specs"
        raise ValueError(message)
    specification_path = (repository_root / matches[0].group("path")).resolve(strict=True)
    root = repository_root.resolve(strict=True)
    if not specification_path.is_relative_to(root) or not specification_path.is_file():
        message = "legacy plan specification reference must resolve inside the repository"
        raise ValueError(message)
    return specification_path


def _legacy_plan_work_id(plan_path: Path) -> str:
    stem = plan_path.stem.removesuffix("-plan")
    words = _SAFE_STEM_WORD_PATTERN.findall(stem.lower())
    if not words:
        message = "legacy plan filename must contain a stable work id"
        raise ValueError(message)
    return "-".join(words)


def _legacy_plan_material_digest(*, plan_markdown: str, specification: str, specification_digest: str) -> str:
    normalized = plan_markdown.replace("\r\n", "\n").replace("\r", "\n")
    payload = json.dumps(
        {
            "legacy_plan_markdown": normalized,
            "plan_revision": 1,
            "specification": specification,
            "specification_digest": specification_digest,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _repository_relative_path(path: Path, *, repository_root: Path) -> str:
    return path.resolve(strict=True).relative_to(repository_root.resolve(strict=True)).as_posix()


def _interactive_stage_runtime(
    request: InvocationRequest,
    *,
    cwd: Path,
    config: _InteractiveStageConfig,
) -> _InteractiveStageRuntime | TerminalResult:
    artifact_selector = SelectArtifactLocation()
    artifact_location = artifact_selector.execute(
        SelectArtifactLocationRequest(
            artifact_kind=config.artifact_kind,
            artifact_stem=config.artifact_stem,
        )
    )
    if isinstance(artifact_location, ArtifactLocationBlocker):
        return TerminalResult(
            status=TerminalStatus.BLOCKED,
            reason=config.blocked_reason,
            stage=request.stage,
            input_path=_input_path(request),
            blocker=TerminalBlocker(code=artifact_location.code, summary=artifact_location.summary),
        )

    repository_request = RepositoryInspectionRequest(
        working_directory=cwd,
        managed_paths=(Path(artifact_location.directory),),
    )
    preflight_request = StagePreflightRequest(
        invocation=request,
        artifact_location_request=None,
        repository_request=repository_request,
        cline_preflight_request=ClinePreflightRequest(
            command=(request.cline_command,),
            required_skills=(config.required_skill,),
        ),
    )
    repository_inspector = GitCliRepositoryInspector()
    preflight = PreflightLifecycleStage(
        repository_inspector=_RepositoryInspectionAdapter(repository_inspector),
        cline_preflight=PreflightClineCapabilities(SubprocessClineCapabilityProbe()),
    )
    session_attempts = RunSessionAttempts(
        runner=AttachedTtyClineSessionRunner(),
        repository_inspector=repository_inspector,
    )
    return _InteractiveStageRuntime(
        output_artifact=artifact_location,
        preflight_request=preflight_request,
        preflight=preflight,
        session_attempts=session_attempts,
    )


@dataclass(frozen=True)
class _RepositoryInspectionAdapter:
    inspector: GitCliRepositoryInspector

    def execute(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        return self.inspector.inspect(request)


class _SystemClock:
    """Adapter for timezone-aware UTC timestamps used in plan review progress."""

    def now(self) -> datetime:
        """Return the current UTC timestamp."""
        return datetime.now(UTC)


def _terminal_result_from_idea_result(request: InvocationRequest, result: IdeaRefinementResult) -> TerminalResult:
    if result.status is IdeaRefinementStatus.COMPLETED:
        return TerminalResult(
            status=TerminalStatus.COMPLETED,
            reason=IDEA_COMPLETED_REASON,
            stage=request.stage,
            output_paths=result.output_paths,
        )
    blocker = result.blocker
    return TerminalResult(
        status=TerminalStatus.BLOCKED if result.status is IdeaRefinementStatus.BLOCKED else TerminalStatus.FAILED,
        reason=IDEA_BLOCKED_REASON if result.status is IdeaRefinementStatus.BLOCKED else IDEA_FAILED_REASON,
        stage=request.stage,
        blocker=TerminalBlocker(
            code=blocker.code if blocker is not None else "idea_refinement_failed",
            summary=blocker.summary if blocker is not None else "idea refinement did not complete",
            evidence=blocker.evidence if blocker is not None else None,
        ),
    )


def _terminal_result_from_specification_result(
    request: InvocationRequest,
    result: SpecificationCreationResult,
) -> TerminalResult:
    if result.status is SpecificationCreationStatus.COMPLETED:
        return TerminalResult(
            status=TerminalStatus.COMPLETED,
            reason=SPEC_COMPLETED_REASON,
            stage=request.stage,
            input_path=_input_path(request),
            output_paths=result.output_paths,
        )
    blocker = result.blocker
    return TerminalResult(
        status=TerminalStatus.BLOCKED
        if result.status is SpecificationCreationStatus.BLOCKED
        else TerminalStatus.FAILED,
        reason=SPEC_BLOCKED_REASON if result.status is SpecificationCreationStatus.BLOCKED else SPEC_FAILED_REASON,
        stage=request.stage,
        input_path=_input_path(request),
        blocker=TerminalBlocker(
            code=blocker.code if blocker is not None else "specification_creation_failed",
            summary=blocker.summary if blocker is not None else "specification creation did not complete",
            evidence=blocker.evidence if blocker is not None else None,
        ),
    )


def _terminal_result_from_plan_authoring_result(
    request: InvocationRequest,
    result: PlanAuthoringResult,
) -> TerminalResult:
    blocker = result.blocker
    return TerminalResult(
        status=TerminalStatus.BLOCKED if result.status is PlanAuthoringStatus.BLOCKED else TerminalStatus.FAILED,
        reason=PLAN_BLOCKED_REASON if result.status is PlanAuthoringStatus.BLOCKED else PLAN_FAILED_REASON,
        stage=request.stage,
        input_path=_input_path(request),
        output_paths=result.output_paths,
        specification_digest=result.specification_digest,
        plan_material_digest=result.material_digest,
        blocker=TerminalBlocker(
            code=blocker.code if blocker is not None else "plan_authoring_failed",
            summary=blocker.summary if blocker is not None else "plan authoring did not complete",
            evidence=blocker.evidence if blocker is not None else None,
        ),
    )


def _terminal_result_from_plan_review_result(
    request: InvocationRequest,
    result: PlanReviewResult,
    *,
    specification_digest: str | None,
) -> TerminalResult:
    if result.status is PlanReviewStatus.READY:
        return TerminalResult(
            status=TerminalStatus.COMPLETED,
            reason=PLAN_COMPLETED_REASON,
            stage=request.stage,
            input_path=_input_path(request),
            output_paths=result.output_paths,
            specification_digest=specification_digest,
            plan_material_digest=result.material_digest,
        )
    blocker = result.blocker
    return TerminalResult(
        status=TerminalStatus.BLOCKED if result.status is PlanReviewStatus.BLOCKED else TerminalStatus.FAILED,
        reason=PLAN_BLOCKED_REASON if result.status is PlanReviewStatus.BLOCKED else PLAN_FAILED_REASON,
        stage=request.stage,
        input_path=_input_path(request),
        output_paths=result.output_paths,
        specification_digest=specification_digest,
        plan_material_digest=result.material_digest,
        blocker=TerminalBlocker(
            code=blocker.code if blocker is not None else "plan_review_failed",
            summary=blocker.summary if blocker is not None else "plan review did not mark the plan ready",
            evidence=blocker.evidence if blocker is not None else None,
        ),
    )


def _artifact_stem(rough_idea: str) -> str:
    words = _SAFE_STEM_WORD_PATTERN.findall(rough_idea.lower())
    return "-".join(words[:6]) or "idea"


def _render_cli_result(result: TerminalResult, *, emit_json: bool) -> CliRunResult:
    payload = json.dumps(result.to_payload(), sort_keys=True, separators=(",", ":"))
    exit_code = int(exit_category_for_status(result.status))
    if emit_json:
        return CliRunResult(exit_code=exit_code, stdout=f"{payload}\n", stderr="", terminal_result=result)
    diagnostic = _human_diagnostic(result)
    return CliRunResult(exit_code=exit_code, stdout=f"{diagnostic}\n{payload}\n", stderr="", terminal_result=result)


def _human_diagnostic(result: TerminalResult) -> str:
    summary = result.blocker.summary if result.blocker is not None else result.reason
    return f"cline-sdlc: {result.status.value}: {summary}"


def _argv_requests_json(argv: Sequence[str]) -> bool:
    return "--json" in argv


def _input_path(request: InvocationRequest) -> str | None:
    value = request.source.value
    if isinstance(value, Path):
        return value.as_posix()
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="cline-sdlc", add_help=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--idea")
    inputs.add_argument("--idea-file")
    inputs.add_argument("--spec-file")
    inputs.add_argument("--plan-file")
    parser.add_argument("--timeout", default=str(DEFAULT_TIMEOUT_SECONDS))
    parser.add_argument("--cline-command", default="cline")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _parse_timeout(raw_timeout: str) -> float:
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as err:
        raise ValueError(INVALID_TIMEOUT_MESSAGE) from err
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError(INVALID_TIMEOUT_MESSAGE)
    return timeout_seconds


def _request_from_namespace(namespace: argparse.Namespace, *, cwd: Path, timeout_seconds: float) -> InvocationRequest:
    source = _source_from_namespace(namespace, cwd=cwd)
    return InvocationRequest(
        source=source,
        timeout_seconds=timeout_seconds,
        cline_command=namespace.cline_command,
        emit_json=namespace.json,
        verbose=namespace.verbose,
        dry_run=namespace.dry_run,
    )


def _source_from_namespace(namespace: argparse.Namespace, *, cwd: Path) -> InvocationSource:
    if namespace.idea is not None:
        idea = namespace.idea.strip()
        if not idea:
            message = "--idea must not be empty"
            raise ValueError(message)
        return InvocationSource.from_idea(idea)
    if namespace.idea_file is not None:
        return InvocationSource.from_idea_file(_validated_file(namespace.idea_file, cwd=cwd))
    if namespace.spec_file is not None:
        return InvocationSource.from_spec_file(_validated_file(namespace.spec_file, cwd=cwd))
    if namespace.plan_file is not None:
        return InvocationSource.from_plan_file(_validated_file(namespace.plan_file, cwd=cwd))
    message = "exactly one input option is required"
    raise ValueError(message)


def _validated_file(raw_path: str, *, cwd: Path) -> Path:
    path = Path(raw_path).expanduser()
    resolved_path = path if path.is_absolute() else cwd / path
    if not resolved_path.exists():
        message = f"input file does not exist: {raw_path}"
        raise ValueError(message)
    if not resolved_path.is_file():
        message = f"input path is not a file: {raw_path}"
        raise ValueError(message)
    return resolved_path
