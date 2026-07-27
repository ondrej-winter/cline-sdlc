"""CLI parsing adapter for supervised lifecycle runner invocations."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Never

from cline_sdlc import __version__
from cline_sdlc.features.artifact_lifecycle.application.dtos.artifact_location import (
    ArtifactKind,
    ArtifactLocationBlocker,
    SelectArtifactLocationRequest,
)
from cline_sdlc.features.artifact_lifecycle.application.use_cases.select_artifact_location import SelectArtifactLocation
from cline_sdlc.features.cline_execution.adapters.outbound.cli_capability_probe import SubprocessClineCapabilityProbe
from cline_sdlc.features.cline_execution.adapters.outbound.interactive_process import AttachedTtyClineSessionRunner
from cline_sdlc.features.cline_execution.application.dtos.preflight import ClinePreflightRequest
from cline_sdlc.features.cline_execution.application.use_cases.preflight import PreflightClineCapabilities
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
from cline_sdlc.features.lifecycle_orchestration.application.dtos.preflight import StagePreflightRequest
from cline_sdlc.features.lifecycle_orchestration.application.dtos.specification_stage import (
    SpecificationCreationRequest,
    SpecificationCreationResult,
    SpecificationCreationStatus,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.terminal_result import TerminalBlocker, TerminalResult
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.create_specification import CreateSpecification
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.preflight_stage import PreflightLifecycleStage
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.refine_idea import RefineIdea
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.run_session_attempts import RunSessionAttempts
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
_SAFE_STEM_WORD_PATTERN = re.compile(r"[a-z0-9]+")


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
        return CliRunResult(
            exit_code=int(exit_category_for_status(result.status)),
            stdout=f"cline-sdlc {__version__}\n",
            stderr="",
            terminal_result=result,
        )

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

    if parsed.request.stage is LifecycleStage.IDEA_REFINEMENT:
        result = _run_idea_refinement(parsed.request, cwd=cwd or Path.cwd())
        return _render_cli_result(result, emit_json=parsed.request.emit_json)
    if parsed.request.stage is LifecycleStage.SPECIFICATION_CREATION:
        result = _run_specification_creation(parsed.request, cwd=cwd or Path.cwd())
        return _render_cli_result(result, emit_json=parsed.request.emit_json)

    result = TerminalResult(
        status=TerminalStatus.BLOCKED,
        reason=UNSUPPORTED_STAGE_REASON,
        stage=parsed.request.stage,
        input_path=_input_path(parsed.request),
        blocker=TerminalBlocker(
            code="stage_not_wired",
            summary="Only idea refinement is currently wired through the supervised CLI runner.",
        ),
    )
    return _render_cli_result(result, emit_json=parsed.request.emit_json)


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
    artifact_selector = SelectArtifactLocation()
    artifact_location = artifact_selector.execute(
        SelectArtifactLocationRequest(
            artifact_kind=ArtifactKind.IDEA_BRIEF,
            artifact_stem=_artifact_stem(str(request.source.value)),
        )
    )
    if isinstance(artifact_location, ArtifactLocationBlocker):
        return TerminalResult(
            status=TerminalStatus.BLOCKED,
            reason=IDEA_BLOCKED_REASON,
            stage=request.stage,
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
            required_skills=("idea-refine",),
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
    result = RefineIdea(preflight=preflight, session_attempts=session_attempts).execute(
        IdeaRefinementRequest(
            invocation=request,
            preflight_request=preflight_request,
            output_artifact=artifact_location,
        )
    )
    return _terminal_result_from_idea_result(request, result)


def _run_specification_creation(request: InvocationRequest, *, cwd: Path) -> TerminalResult:
    artifact_selector = SelectArtifactLocation()
    idea_path = Path(request.source.value)
    artifact_stem = _artifact_stem(idea_path.stem.removesuffix("-idea"))
    artifact_location = artifact_selector.execute(
        SelectArtifactLocationRequest(
            artifact_kind=ArtifactKind.SPECIFICATION,
            artifact_stem=artifact_stem,
        )
    )
    if isinstance(artifact_location, ArtifactLocationBlocker):
        return TerminalResult(
            status=TerminalStatus.BLOCKED,
            reason=SPEC_BLOCKED_REASON,
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
            required_skills=("spec-driven-development",),
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
    result = CreateSpecification(preflight=preflight, session_attempts=session_attempts).execute(
        SpecificationCreationRequest(
            invocation=request,
            preflight_request=preflight_request,
            output_artifact=artifact_location,
        )
    )
    return _terminal_result_from_specification_result(request, result)


@dataclass(frozen=True)
class _RepositoryInspectionAdapter:
    inspector: GitCliRepositoryInspector

    def execute(self, request: RepositoryInspectionRequest) -> RepositoryInspectionResult:
        return self.inspector.inspect(request)


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
