"""Public subprocess-backed Cline CLI capability probe adapter."""

from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.domain.capability import (
    CapabilityCriticality,
    ClineCapabilityReport,
)

from ._observations import advertised
from ._session import session_observations
from ._skills import skill_observations
from ._subprocess import first_non_empty_line, run

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest


class SubprocessClineCapabilityProbe:
    """Inspect Cline CLI help/version output with argument-array subprocess calls."""

    def probe(self, request: CapabilityProbeRequest) -> ClineCapabilityReport:
        """Return advertised capabilities and explicitly unproven critical contracts."""
        help_result = run((*request.command, "--help"))
        version_result = run((*request.command, "--version"))

        help_text = help_result.stdout + help_result.stderr
        version = first_non_empty_line(version_result.stdout + version_result.stderr)

        observations = [
            advertised("json_output", "--json", help_text),
            advertised("finite_timeout_option", "--timeout", help_text),
            advertised("isolated_data_directory", "--data-dir", help_text),
            advertised("hook_injection_directory", "--hooks-dir", help_text),
            advertised("explicit_working_directory", "--cwd", help_text),
            advertised("skill_management_command", "skill", help_text),
            *skill_observations(request.command, request.required_skills, request.repository_root),
            *session_observations(request),
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
