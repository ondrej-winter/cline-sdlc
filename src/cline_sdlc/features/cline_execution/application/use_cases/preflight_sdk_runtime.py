"""Use case for Cline SDK adapter runtime preflight."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import (
    SdkRuntimeBlocker,
    SdkRuntimeCapability,
    SdkRuntimeCapabilityEvidence,
    SdkRuntimeCapabilitySource,
    SdkRuntimeCapabilityStatus,
    SdkRuntimePreflightResult,
    SdkRuntimePreflightStatus,
)

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import SdkRuntimePreflightRequest
    from cline_sdlc.features.cline_execution.application.ports.sdk_runtime import SdkRuntimeProbePort


class PreflightSdkRuntime:
    """Verify adapter-local Node.js and Cline SDK prerequisites."""

    def __init__(self, probe: SdkRuntimeProbePort) -> None:
        self._probe = probe

    def execute(self, request: SdkRuntimePreflightRequest) -> SdkRuntimePreflightResult:
        """Return actionable readiness or blockers for the SDK adapter runtime."""
        observation = self._probe.inspect(request)
        capability_blockers = _capability_blockers(observation.capabilities)
        blockers = (*observation.blockers, *capability_blockers)
        return SdkRuntimePreflightResult(
            status=SdkRuntimePreflightStatus.READY if not blockers else SdkRuntimePreflightStatus.FAILED,
            node_executable=observation.node_executable,
            node_version=observation.node_version,
            sdk_package_name=observation.sdk_package_name,
            capabilities=observation.capabilities,
            blockers=blockers,
        )


_FULL_CONTRACT_CAPABILITIES = frozenset(
    {
        SdkRuntimeCapability.NODE_RUNTIME,
        SdkRuntimeCapability.SDK_PACKAGE,
        SdkRuntimeCapability.BOUNDED_SESSION,
        SdkRuntimeCapability.EXPLICIT_SESSION_CONTEXT,
        SdkRuntimeCapability.EVENT_EVIDENCE_STREAM,
        SdkRuntimeCapability.STRUCTURED_TERMINAL_OUTCOME,
        SdkRuntimeCapability.TIMEOUT_INTERRUPTION,
        SdkRuntimeCapability.DIAGNOSTIC_REFERENCES,
        SdkRuntimeCapability.AGENT_RUN,
        SdkRuntimeCapability.CLINECORE_SESSION,
        SdkRuntimeCapability.PROGRAMMATIC_MODE_SWITCH,
        SdkRuntimeCapability.TOOL_POLICY_COVERAGE,
        SdkRuntimeCapability.PERMISSION_APPROVAL,
        SdkRuntimeCapability.PLAN_ACT_OBSERVATION,
        SdkRuntimeCapability.ACT_AUTHORIZATION,
        SdkRuntimeCapability.CLI_PROBE_EXCLUDED,
    }
)


def _capability_blockers(capabilities: tuple[SdkRuntimeCapabilityEvidence, ...]) -> tuple[SdkRuntimeBlocker, ...]:
    evidence_by_capability = {evidence.capability: evidence for evidence in capabilities}
    blockers: list[SdkRuntimeBlocker] = []
    for capability in sorted(_FULL_CONTRACT_CAPABILITIES, key=lambda item: item.value):
        evidence = evidence_by_capability.get(capability)
        if evidence is None:
            blockers.append(_missing_capability_blocker(capability))
            continue
        if evidence.status is not SdkRuntimeCapabilityStatus.PROVEN:
            blockers.append(_unproven_capability_blocker(evidence))
            continue
        if evidence.source is SdkRuntimeCapabilitySource.CLI_PROBE:
            blockers.append(_cli_probe_blocker(evidence))
    return tuple(blockers)


def _missing_capability_blocker(capability: SdkRuntimeCapability) -> SdkRuntimeBlocker:
    return SdkRuntimeBlocker(
        code=f"sdk_capability_missing_{capability.value}",
        summary="Required Cline SDK execution capability evidence is missing.",
        evidence=f"capability={capability.value}",
    )


def _unproven_capability_blocker(evidence: SdkRuntimeCapabilityEvidence) -> SdkRuntimeBlocker:
    return SdkRuntimeBlocker(
        code=f"sdk_capability_unproven_{evidence.capability.value}",
        summary="Required Cline SDK execution capability is not proven.",
        evidence=f"capability={evidence.capability.value};source={evidence.source.value};status={evidence.status.value}",
    )


def _cli_probe_blocker(evidence: SdkRuntimeCapabilityEvidence) -> SdkRuntimeBlocker:
    return SdkRuntimeBlocker(
        code=f"sdk_capability_cli_probe_{evidence.capability.value}",
        summary="CLI probing is not accepted as production-equivalent SDK readiness evidence.",
        evidence=f"capability={evidence.capability.value}",
    )
