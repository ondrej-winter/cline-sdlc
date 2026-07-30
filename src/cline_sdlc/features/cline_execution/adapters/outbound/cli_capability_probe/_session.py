"""Private supervised-session probing helpers for the Cline CLI probe adapter."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard

from cline_sdlc.features.cline_execution.domain.capability import CapabilityObservation, CapabilityStatus

from ._observations import supporting
from ._subprocess import run_with_timeout

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.capability_probe import CapabilityProbeRequest

_STATUS_SIDECAR_FILENAME = ".cline-sdlc-capability-probe-status.json"


def session_observations(request: CapabilityProbeRequest) -> tuple[CapabilityObservation, ...]:
    """Return critical observations for supervised session contract behavior."""
    if not request.supervised_session_probe:
        return _unproven_session_observations()

    sidecar_path = _status_sidecar_path(request)
    _remove_stale_sidecar(sidecar_path)
    arguments = _session_arguments(request)
    result = run_with_timeout(arguments, request.session_timeout_seconds)
    if result is None:
        return (
            supporting(
                "supervised_session_writes_status_sidecar",
                CapabilityStatus.UNPROVEN,
                "Supervised session timed out before a status sidecar could be validated.",
            ),
            supporting(
                "cline_authored_interruption_recovery_metadata",
                CapabilityStatus.PROVEN,
                "The parent observed and bounded a timeout from the supervised session process.",
            ),
        )

    sidecar = _status_sidecar(sidecar_path)
    return (
        _status_sidecar_observation(sidecar),
        _sidecar_metadata_observation(
            "cline_authored_interruption_recovery_metadata",
            sidecar,
            metadata_key="interruption_recovery",
            proven_evidence="Supervised session status sidecar reported interruption recovery observability evidence.",
            unproven_evidence="Supervised session status sidecar did not prove interruption recovery observability.",
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
    arguments.append(_probe_prompt(request))
    return tuple(arguments)


def _probe_prompt(request: CapabilityProbeRequest) -> str:
    sidecar_path = _status_sidecar_path(request)
    return (
        f"{request.probe_prompt}\n\n"
        "Before exiting, write a UTF-8 JSON status sidecar file at this exact path:\n"
        f"{sidecar_path}\n"
        "The sidecar must be a single JSON object with schema_version=1, status='ok', "
        "and interruption_recovery=true."
    )


def _status_sidecar_path(request: CapabilityProbeRequest) -> Path:
    root = request.repository_root or Path.cwd()
    return root / _STATUS_SIDECAR_FILENAME


def _remove_stale_sidecar(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _status_sidecar(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def _status_sidecar_observation(sidecar: dict[str, object] | None) -> CapabilityObservation:
    if _is_status_sidecar(sidecar):
        return supporting(
            "supervised_session_writes_status_sidecar",
            CapabilityStatus.PROVEN,
            "Supervised session wrote one schema-versioned status sidecar JSON object.",
        )
    return supporting(
        "supervised_session_writes_status_sidecar",
        CapabilityStatus.UNPROVEN,
        "Supervised session did not write a valid schema-versioned status sidecar JSON object.",
    )


def _is_status_sidecar(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and value.get("schema_version") == 1 and value.get("status") == "ok"


def _sidecar_metadata_observation(
    name: str,
    sidecar: dict[str, object] | None,
    *,
    metadata_key: str,
    proven_evidence: str,
    unproven_evidence: str,
) -> CapabilityObservation:
    if _is_status_sidecar(sidecar) and sidecar.get(metadata_key) is True:
        return supporting(name, CapabilityStatus.PROVEN, proven_evidence)
    return supporting(name, CapabilityStatus.UNPROVEN, unproven_evidence)


def _unproven_session_observations() -> tuple[CapabilityObservation, ...]:
    return (
        supporting(
            "supervised_session_writes_status_sidecar",
            CapabilityStatus.UNPROVEN,
            "Help/version probes do not prove that a supervised Cline session writes a status sidecar; "
            "legacy supervised CLI compatibility relies on repository-visible checkpoint evidence.",
        ),
        supporting(
            "cline_authored_interruption_recovery_metadata",
            CapabilityStatus.UNPROVEN,
            "Help output advertises timeouts, but this spike does not prove Cline-authored interruption recovery "
            "metadata; supervised MVP recovery can be observed by the orchestrator.",
        ),
    )
