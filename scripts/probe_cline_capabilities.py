"""Run the public Cline CLI capability probe adapter and print a JSON report."""

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
    """Build the capability probe script argument parser."""
    parser = argparse.ArgumentParser(description="Run the Cline CLI capability probe and print a JSON report.")
    parser.add_argument(
        "--cline-command",
        nargs="+",
        default=["cline"],
        help="Cline command as an argument array. Defaults to: cline",
    )
    parser.add_argument(
        "--required-skill",
        action="append",
        dest="required_skills",
        default=[],
        help="Required skill to probe. Repeat for multiple skills. Defaults to stage-critical skills.",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        help="Repository root used to detect local .agents/skills and optionally as supervised session --cwd.",
    )
    parser.add_argument(
        "--data-directory", type=Path, help="Optional isolated Cline data directory for supervised probing."
    )
    parser.add_argument("--hooks-directory", type=Path, help="Optional hooks directory for supervised probing.")
    parser.add_argument(
        "--supervised-session-probe",
        action="store_true",
        help="Run the bounded JSON session probe instead of only help/version/skill-list checks.",
    )
    parser.add_argument(
        "--session-timeout-seconds",
        default=10.0,
        type=float,
        help="Finite timeout for the supervised session probe.",
    )
    parser.add_argument(
        "--probe-prompt",
        default="Write one machine-readable capability status sidecar.",
        help="Prompt sent to Cline during the supervised session probe.",
    )
    return parser


def run_probe(arguments: argparse.Namespace) -> ClineCapabilityReport:
    """Run the public capability proof use case for script arguments."""
    required_skills = tuple(arguments.required_skills) or DEFAULT_REQUIRED_SKILLS
    request = CapabilityProbeRequest(
        command=tuple(arguments.cline_command),
        required_skills=required_skills,
        supervised_session_probe=arguments.supervised_session_probe,
        repository_root=arguments.repository_root,
        data_directory=arguments.data_directory,
        hooks_directory=arguments.hooks_directory,
        session_timeout_seconds=arguments.session_timeout_seconds,
        probe_prompt=arguments.probe_prompt,
    )
    return ProveClineCliContracts(SubprocessClineCapabilityProbe()).execute(request)


def report_to_json(report: ClineCapabilityReport) -> str:
    """Serialize the capability report as stable JSON."""
    payload = asdict(report)
    payload["critical_capabilities_proven"] = report.critical_capabilities_proven
    payload["blocking_observations"] = [asdict(observation) for observation in report.blocking_observations]
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the capability probe script and return a status code."""
    arguments = build_parser().parse_args(argv)
    report = run_probe(arguments)
    sys.stdout.write(report_to_json(report))
    sys.stdout.write("\n")
    return 0 if report.critical_capabilities_proven else 1


if __name__ == "__main__":
    raise SystemExit(main())
