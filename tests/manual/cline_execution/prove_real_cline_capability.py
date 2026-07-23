"""Supervised real-Cline capability proof entry point.

This module is intentionally outside the default automated proof path. It can be
run manually against an explicitly selected Cline command and disposable
repository while unit tests exercise the same reporting behavior with a fake
executable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.adapters.outbound.cli_capability_probe import SubprocessClineCapabilityProbe
from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest
from cline_sdlc.features.cline_execution.application.use_cases.prove_cli_contracts import ProveClineCliContracts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cline_sdlc.features.cline_execution.domain.capability import ClineCapabilityReport

DEFAULT_REQUIRED_SKILLS = (
    "idea-refine",
    "spec-driven-development",
    "planning-and-task-breakdown",
    "code-review-and-quality",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the supervised proof command parser."""
    parser = argparse.ArgumentParser(description="Run a supervised Cline CLI capability proof.")
    parser.add_argument(
        "--cline-command",
        required=True,
        nargs="+",
        help="Explicit Cline command as an argument array, for example: --cline-command /path/to/cline",
    )
    parser.add_argument(
        "--repository-root",
        required=True,
        type=Path,
        help="Disposable repository root used for the supervised session probe.",
    )
    parser.add_argument(
        "--data-directory",
        required=True,
        type=Path,
        help="Isolated Cline data directory for this proof run.",
    )
    parser.add_argument(
        "--hooks-directory",
        required=True,
        type=Path,
        help="Hook directory used only for this proof run.",
    )
    parser.add_argument(
        "--required-skill",
        action="append",
        dest="required_skills",
        default=[],
        help="Required skill to probe. Repeat for multiple skills. Defaults to stage-critical skills.",
    )
    parser.add_argument(
        "--session-timeout-seconds",
        default=30.0,
        type=float,
        help="Finite timeout for the supervised session probe.",
    )
    parser.add_argument(
        "--probe-prompt",
        default="Emit one machine-readable capability outcome and no lifecycle artifact writes.",
        help="Prompt sent to Cline during the supervised session probe.",
    )
    return parser


def run_supervised_proof(arguments: argparse.Namespace) -> ClineCapabilityReport:
    """Run the capability proof use case with explicit supervised inputs."""
    required_skills = tuple(arguments.required_skills) or DEFAULT_REQUIRED_SKILLS
    request = CapabilityProbeRequest(
        command=tuple(arguments.cline_command),
        required_skills=required_skills,
        supervised_session_probe=True,
        repository_root=arguments.repository_root,
        data_directory=arguments.data_directory,
        hooks_directory=arguments.hooks_directory,
        session_timeout_seconds=arguments.session_timeout_seconds,
        probe_prompt=arguments.probe_prompt,
    )
    return ProveClineCliContracts(SubprocessClineCapabilityProbe()).execute(request)


def report_to_json(report: ClineCapabilityReport) -> str:
    """Serialize the redacted capability report as stable JSON."""
    payload = asdict(report)
    payload["critical_capabilities_proven"] = report.critical_capabilities_proven
    payload["blocking_observations"] = [asdict(observation) for observation in report.blocking_observations]
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the supervised proof command and return a process exit code."""
    parser = build_parser()
    arguments, cline_extra_arguments = parser.parse_known_args(argv)
    arguments.cline_command.extend(cline_extra_arguments)
    report = run_supervised_proof(arguments)
    sys.stdout.write(report_to_json(report))
    sys.stdout.write("\n")
    return 0 if report.critical_capabilities_proven else 1


if __name__ == "__main__":
    raise SystemExit(main())
