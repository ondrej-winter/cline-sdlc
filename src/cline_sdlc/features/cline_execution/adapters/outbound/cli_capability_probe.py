"""Subprocess-backed Cline CLI capability probe adapter."""

import json
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
_SUCCESSFUL_SESSION_STATUSES = frozenset({"completed", "blocked", "approval_required", "failed"})


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
            *_skill_observations(request.command, request.required_skills),
            *_session_observations(request),
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


def _run_with_timeout(arguments: Sequence[str], timeout_seconds: float) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # noqa: S603
            list(arguments),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None


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


def _skill_observations(command: Sequence[str], required_skills: tuple[str, ...]) -> tuple[CapabilityObservation, ...]:
    if not required_skills:
        return ()

    skill_result = _run((*command, "skill", "list"))
    skill_text = skill_result.stdout + skill_result.stderr
    available_skills = frozenset(line.strip() for line in skill_text.splitlines() if line.strip())

    return tuple(
        CapabilityObservation(
            name=f"required_skill:{skill}",
            status=_skill_status(skill_result.returncode, skill, available_skills),
            criticality=CapabilityCriticality.CRITICAL,
            evidence=_skill_evidence(skill_result.returncode, skill),
        )
        for skill in required_skills
    )


def _skill_status(return_code: int, skill: str, available_skills: frozenset[str]) -> CapabilityStatus:
    if return_code != 0:
        return CapabilityStatus.UNPROVEN
    if skill in available_skills:
        return CapabilityStatus.PROVEN
    return CapabilityStatus.MISSING


def _skill_evidence(return_code: int, skill: str) -> str:
    if return_code != 0:
        return "Skill list command did not complete successfully; availability is unproven."
    return f"Skill list output was inspected for required skill {skill!r}."


def _session_observations(request: CapabilityProbeRequest) -> tuple[CapabilityObservation, ...]:
    if not request.supervised_session_probe:
        return _unproven_session_observations()

    arguments = _session_arguments(request)
    result = _run_with_timeout(arguments, request.session_timeout_seconds)
    if result is None:
        return (
            _critical(
                "exactly_one_machine_detectable_terminal_outcome",
                CapabilityStatus.UNPROVEN,
                "Supervised session timed out before a terminal outcome could be validated.",
            ),
            _critical(
                "pre_execution_permission_mediation",
                CapabilityStatus.UNPROVEN,
                "Timed-out session did not prove pre-execution permission mediation.",
            ),
            _critical(
                "interruption_recovery_observability",
                CapabilityStatus.PROVEN,
                "The parent observed and bounded a timeout from the supervised session process.",
            ),
        )

    outcomes = _terminal_outcomes(result.stdout)
    return (
        _terminal_outcome_observation(outcomes),
        _metadata_observation(
            "pre_execution_permission_mediation",
            outcomes,
            metadata_key="permission_mediation",
            proven_evidence="Supervised session outcome reported pre-execution permission mediation evidence.",
            unproven_evidence="Supervised session outcome did not prove pre-execution permission mediation.",
        ),
        _metadata_observation(
            "interruption_recovery_observability",
            outcomes,
            metadata_key="interruption_recovery",
            proven_evidence="Supervised session outcome reported interruption recovery observability evidence.",
            unproven_evidence="Supervised session outcome did not prove interruption recovery observability.",
        ),
    )


def _session_arguments(request: CapabilityProbeRequest) -> tuple[str, ...]:
    arguments = [
        *request.command,
        "--json",
        "--timeout",
        str(request.session_timeout_seconds),
    ]
    if request.repository_root is not None:
        arguments.extend(("--cwd", str(request.repository_root)))
    if request.data_directory is not None:
        arguments.extend(("--data-dir", str(request.data_directory)))
    if request.hooks_directory is not None:
        arguments.extend(("--hooks-dir", str(request.hooks_directory)))
    arguments.append(request.probe_prompt)
    return tuple(arguments)


def _terminal_outcomes(stdout: str) -> tuple[dict[str, object], ...]:
    outcomes: list[dict[str, object]] = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and value.get("schema_version") == 1
            and value.get("status") in _SUCCESSFUL_SESSION_STATUSES
        ):
            outcomes.append(value)
    return tuple(outcomes)


def _terminal_outcome_observation(outcomes: tuple[dict[str, object], ...]) -> CapabilityObservation:
    if len(outcomes) == 1:
        return _critical(
            "exactly_one_machine_detectable_terminal_outcome",
            CapabilityStatus.PROVEN,
            "Supervised session emitted exactly one schema-versioned terminal outcome JSON object.",
        )
    return _critical(
        "exactly_one_machine_detectable_terminal_outcome",
        CapabilityStatus.UNPROVEN,
        f"Supervised session emitted {len(outcomes)} parseable terminal outcomes; expected exactly one.",
    )


def _metadata_observation(
    name: str,
    outcomes: tuple[dict[str, object], ...],
    *,
    metadata_key: str,
    proven_evidence: str,
    unproven_evidence: str,
) -> CapabilityObservation:
    if len(outcomes) == 1 and outcomes[0].get(metadata_key) is True:
        return _critical(name, CapabilityStatus.PROVEN, proven_evidence)
    return _critical(name, CapabilityStatus.UNPROVEN, unproven_evidence)


def _unproven_session_observations() -> tuple[CapabilityObservation, ...]:
    return (
        _critical(
            "exactly_one_machine_detectable_terminal_outcome",
            CapabilityStatus.UNPROVEN,
            "Help/version probes do not prove a dedicated terminal outcome channel or exactly-one semantics.",
        ),
        _critical(
            "pre_execution_permission_mediation",
            CapabilityStatus.UNPROVEN,
            "Help output advertises hooks, but this spike does not prove operations are mediated before execution.",
        ),
        _critical(
            "interruption_recovery_observability",
            CapabilityStatus.UNPROVEN,
            "Help output advertises timeouts, but this spike does not prove bounded cleanup and write attribution.",
        ),
    )


def _critical(name: str, status: CapabilityStatus, evidence: str) -> CapabilityObservation:
    return CapabilityObservation(
        name=name,
        status=status,
        criticality=CapabilityCriticality.CRITICAL,
        evidence=evidence,
    )
