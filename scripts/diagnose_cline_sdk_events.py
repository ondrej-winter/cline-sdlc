"""Run the Cline SDK adapter and print safe event-focused diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.adapters.outbound.cline_sdk import ClineSdkSessionRunner
from cline_sdlc.features.cline_execution.application.dtos.session import (
    ClineSessionEvidence,
    ClineSessionEvidenceType,
    ClineSessionProcessStatus,
    ClineSessionRequest,
    ClineSessionResult,
    ClineSessionTerminalStatus,
)
from cline_sdlc.features.cline_execution.domain.outcome import SessionRole

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_INSTRUCTIONS = "Run a safe Cline SDK event diagnostic and report concise progress."
DEFAULT_OUTCOME_CONTRACT = (
    "Emit safe normalized event diagnostics only. Do not include secrets, raw model reasoning, "
    "or raw repository content in normal output."
)


def build_parser() -> argparse.ArgumentParser:
    """Build the SDK event diagnostic argument parser."""
    parser = argparse.ArgumentParser(
        description="Inspect safe normalized events from the experimental adapter-local Cline SDK runner."
    )
    parser.add_argument(
        "--repository-root",
        default=Path.cwd(),
        type=Path,
        help="Working directory passed to the SDK runner. Defaults to the current directory.",
    )
    parser.add_argument(
        "--timeout-seconds",
        default=30.0,
        type=float,
        help="Finite timeout for the diagnostic session. Defaults to 30 seconds.",
    )
    parser.add_argument(
        "--node-command",
        nargs="+",
        default=["node"],
        help="Node.js command as an argument array. Defaults to: node",
    )
    parser.add_argument(
        "--instruction",
        default=DEFAULT_INSTRUCTIONS,
        help="Safe instruction text for the diagnostic session. Avoid secrets and raw repository content.",
    )
    parser.add_argument(
        "--safe-context",
        action="append",
        default=[],
        help="Safe context string to pass to the adapter. Repeat for multiple values.",
    )
    return parser


def run_diagnostic(arguments: argparse.Namespace) -> int:
    """Run one SDK event diagnostic session and write safe JSON to stdout."""
    try:
        request = ClineSessionRequest(
            command=(*tuple(arguments.node_command), "runner.mjs"),
            working_directory=arguments.repository_root,
            timeout_seconds=arguments.timeout_seconds,
            session_role=SessionRole.IMPLEMENTATION,
            instructions=arguments.instruction,
            outcome_contract=DEFAULT_OUTCOME_CONTRACT,
            safe_context=tuple(arguments.safe_context),
        )
        result = ClineSdkSessionRunner(node_command=tuple(arguments.node_command)).run(request)
    except ValueError as err:
        sys.stderr.write(f"usage error: {err}\n")
        return 2

    sys.stdout.write(json.dumps(_result_to_safe_payload(result), indent=2, sort_keys=True))
    sys.stdout.write("\n")
    return _exit_code_for_result(result)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the SDK event diagnostic command and return a stable process code."""
    arguments = build_parser().parse_args(argv)
    return run_diagnostic(arguments)


def _result_to_safe_payload(result: ClineSessionResult) -> dict[str, object]:
    return {
        "process_status": result.process_status.value,
        "exit_code": result.exit_code,
        "sdk_terminal_status": result.sdk_terminal_status.value if result.sdk_terminal_status else None,
        "events": [_event_to_safe_payload(event) for event in result.events],
        "unknown_sdk_event_observations": [
            _event_to_safe_payload(event) for event in result.events if _is_unknown_sdk_event_observation(event)
        ],
        "blockers": [
            {"code": blocker.code, "summary": blocker.summary, "evidence": blocker.evidence}
            for blocker in result.blockers
        ],
        "diagnostic_references": [
            {"kind": reference.kind, "value": reference.value, "summary": reference.summary}
            for reference in result.diagnostic_references
        ],
        "authoritative_lifecycle_evidence": False,
    }


def _event_to_safe_payload(event: ClineSessionEvidence) -> dict[str, object]:
    return {
        "normalized_event_type": event.evidence_type.value,
        "summary": event.summary,
        "sdk_event_type": event.sdk_event_type,
        "paths": list(event.paths),
        "diagnostic_only": event.evidence_type is ClineSessionEvidenceType.DIAGNOSTIC,
    }


def _is_unknown_sdk_event_observation(event: ClineSessionEvidence) -> bool:
    return event.evidence_type is ClineSessionEvidenceType.DIAGNOSTIC and event.sdk_event_type is not None


def _exit_code_for_result(result: ClineSessionResult) -> int:
    if result.process_status in {ClineSessionProcessStatus.TIMED_OUT, ClineSessionProcessStatus.INTERRUPTED}:
        return 6
    if result.sdk_terminal_status is ClineSessionTerminalStatus.COMPLETED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
