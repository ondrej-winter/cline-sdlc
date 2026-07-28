"""Private supervised-session probing helpers for the Cline CLI probe adapter."""

import json
from typing import TYPE_CHECKING, TypeGuard

from cline_sdlc.features.cline_execution.domain.capability import CapabilityObservation, CapabilityStatus

from ._observations import supporting
from ._subprocess import run_with_timeout

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest

_SUCCESSFUL_SESSION_STATUSES = frozenset({"completed", "blocked", "approval_required", "failed"})


def session_observations(request: CapabilityProbeRequest) -> tuple[CapabilityObservation, ...]:
    """Return critical observations for supervised session contract behavior."""
    if not request.supervised_session_probe:
        return _unproven_session_observations()

    arguments = _session_arguments(request)
    result = run_with_timeout(arguments, request.session_timeout_seconds)
    if result is None:
        return (
            supporting(
                "cline_authored_terminal_outcome",
                CapabilityStatus.UNPROVEN,
                "Supervised session timed out before a terminal outcome could be validated.",
            ),
            supporting(
                "cline_authored_interruption_recovery_metadata",
                CapabilityStatus.PROVEN,
                "The parent observed and bounded a timeout from the supervised session process.",
            ),
        )

    outcomes = _terminal_outcomes(result.stdout)
    return (
        _terminal_outcome_observation(outcomes),
        _metadata_observation(
            "cline_authored_interruption_recovery_metadata",
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
        outcomes.extend(_candidate_outcomes(value))
    return tuple(outcomes)


def _candidate_outcomes(value: object) -> tuple[dict[str, object], ...]:
    if _is_terminal_outcome(value):
        return (value,)
    if not isinstance(value, dict):
        return ()

    candidates = (
        value.get("message"),
        value.get("content"),
        value.get("text"),
        value.get("data"),
        value.get("payload"),
    )
    outcomes: list[dict[str, object]] = []
    for candidate in candidates:
        if _is_terminal_outcome(candidate):
            outcomes.append(candidate)
        elif isinstance(candidate, str):
            parsed = _json_object_from_text(candidate)
            if _is_terminal_outcome(parsed):
                outcomes.append(parsed)
    return tuple(outcomes)


def _json_object_from_text(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def _is_terminal_outcome(value: object) -> TypeGuard[dict[str, object]]:
    return (
        isinstance(value, dict)
        and value.get("schema_version") == 1
        and value.get("status") in _SUCCESSFUL_SESSION_STATUSES
    )


def _terminal_outcome_observation(outcomes: tuple[dict[str, object], ...]) -> CapabilityObservation:
    if len(outcomes) == 1:
        return supporting(
            "cline_authored_terminal_outcome",
            CapabilityStatus.PROVEN,
            "Supervised session emitted exactly one schema-versioned terminal outcome JSON object.",
        )
    return supporting(
        "cline_authored_terminal_outcome",
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
        return supporting(name, CapabilityStatus.PROVEN, proven_evidence)
    return supporting(name, CapabilityStatus.UNPROVEN, unproven_evidence)


def _unproven_session_observations() -> tuple[CapabilityObservation, ...]:
    return (
        supporting(
            "cline_authored_terminal_outcome",
            CapabilityStatus.UNPROVEN,
            "Help/version probes do not prove Cline-authored terminal outcome JSON; supervised MVP readiness "
            "relies on orchestrator-owned slice transaction classification.",
        ),
        supporting(
            "cline_authored_interruption_recovery_metadata",
            CapabilityStatus.UNPROVEN,
            "Help output advertises timeouts, but this spike does not prove Cline-authored interruption recovery "
            "metadata; supervised MVP recovery can be observed by the orchestrator.",
        ),
    )
