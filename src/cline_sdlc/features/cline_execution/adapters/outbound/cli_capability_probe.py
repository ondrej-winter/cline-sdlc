"""Subprocess-backed Cline CLI capability probe adapter."""

import subprocess
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.domain.capability import (
    CapabilityCriticality,
    CapabilityObservation,
    CapabilityStatus,
    ClineCapabilityReport,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest

_PROBE_TIMEOUT_SECONDS = 10.0


class SubprocessClineCapabilityProbe:
    """Inspect Cline CLI help/version output with argument-array subprocess calls."""

    def probe(self, request: CapabilityProbeRequest) -> ClineCapabilityReport:
        """Return advertised capabilities and explicitly unproven critical contracts."""
        help_result = _run((*request.command, "--help"))
        version_result = _run((*request.command, "--version"))

        help_text = help_result.stdout + help_result.stderr
        version = _first_non_empty_line(version_result.stdout + version_result.stderr)

        observations = [
            _advertised("json_output", "--json", help_text),
            _advertised("finite_timeout_option", "--timeout", help_text),
            _advertised("isolated_data_directory", "--data-dir", help_text),
            _advertised("hook_injection_directory", "--hooks-dir", help_text),
            _advertised("explicit_working_directory", "--cwd", help_text),
            _advertised("skill_management_command", "skill", help_text),
            CapabilityObservation(
                name="exactly_one_machine_detectable_terminal_outcome",
                status=CapabilityStatus.UNPROVEN,
                criticality=CapabilityCriticality.CRITICAL,
                evidence=(
                    "Help/version probes do not prove a dedicated terminal outcome channel or exactly-one semantics."
                ),
            ),
            CapabilityObservation(
                name="pre_execution_permission_mediation",
                status=CapabilityStatus.UNPROVEN,
                criticality=CapabilityCriticality.CRITICAL,
                evidence=(
                    "Help output advertises hooks, but this spike does not prove operations are mediated "
                    "before execution."
                ),
            ),
            CapabilityObservation(
                name="interruption_recovery_observability",
                status=CapabilityStatus.UNPROVEN,
                criticality=CapabilityCriticality.CRITICAL,
                evidence=(
                    "Help output advertises timeouts, but this spike does not prove bounded cleanup and "
                    "write attribution."
                ),
            ),
        ]

        limitations = tuple(
            observation.evidence
            for observation in observations
            if observation.criticality is CapabilityCriticality.CRITICAL and not observation.is_satisfied
        )
        return ClineCapabilityReport(
            executable=" ".join(request.command),
            version=version,
            observations=tuple(observations),
            limitations=limitations,
        )


def _run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        list(arguments),
        capture_output=True,
        check=False,
        text=True,
        timeout=_PROBE_TIMEOUT_SECONDS,
    )


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _advertised(name: str, token: str, help_text: str) -> CapabilityObservation:
    status = CapabilityStatus.ADVERTISED if token in help_text else CapabilityStatus.MISSING
    evidence = (
        f"Cline help output {'contains' if status is CapabilityStatus.ADVERTISED else 'does not contain'} {token!r}."
    )
    return CapabilityObservation(
        name=name,
        status=status,
        criticality=CapabilityCriticality.SUPPORTING,
        evidence=evidence,
    )
