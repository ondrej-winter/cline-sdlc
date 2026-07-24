"""CLI parsing adapter for supervised lifecycle runner invocations."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Never

from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import (
    InvocationParseError,
    InvocationRequest,
    InvocationSource,
)
from cline_sdlc.features.lifecycle_orchestration.application.dtos.terminal_result import TerminalBlocker, TerminalResult
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_stage import SelectLifecycleStage
from cline_sdlc.features.lifecycle_orchestration.domain.terminal_result import (
    TerminalStatus,
    exit_category_for_status,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_TIMEOUT_SECONDS = 1_800.0
INVALID_TIMEOUT_MESSAGE = "--timeout must be a finite positive number of seconds"
USAGE_ERROR_REASON = "invalid_invocation"
DRY_RUN_REASON = "dry_run_preview"


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
    """Run the currently implemented CLI boundary without starting Cline."""
    parsed = parse_cli_invocation(argv, cwd=cwd)
    if isinstance(parsed, InvocationParseError):
        result = TerminalResult(
            status=TerminalStatus.INVALID_INVOCATION,
            reason=USAGE_ERROR_REASON,
            blocker=TerminalBlocker(code="invalid_invocation", summary=parsed.message),
        )
        return _render_cli_result(result, emit_json=_argv_requests_json(argv))

    result = TerminalResult(
        status=TerminalStatus.BLOCKED,
        reason=DRY_RUN_REASON,
        stage=parsed.request.stage,
        input_path=_input_path(parsed.request),
        blocker=TerminalBlocker(
            code="dry_run_only",
            summary="Task 1.1b renders terminal results; Cline execution is not implemented in this slice.",
        ),
    )
    return _render_cli_result(result, emit_json=parsed.request.emit_json)


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
