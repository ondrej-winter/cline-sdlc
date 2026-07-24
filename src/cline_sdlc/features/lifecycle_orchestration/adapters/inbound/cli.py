"""CLI parsing adapter for supervised lifecycle runner invocations."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Never

from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import (
    InvocationParseError,
    InvocationRequest,
    InvocationSource,
)
from cline_sdlc.features.lifecycle_orchestration.application.use_cases.select_stage import SelectLifecycleStage

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_TIMEOUT_SECONDS = 1_800.0
INVALID_TIMEOUT_MESSAGE = "--timeout must be a finite positive number of seconds"


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


@dataclass(frozen=True)
class ParsedCliInvocation:
    """Successful CLI parse result for one supervised lifecycle invocation."""

    request: InvocationRequest


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
