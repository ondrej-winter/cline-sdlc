"""Use case for Cline SDK adapter runtime preflight."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import (
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
        return SdkRuntimePreflightResult(
            status=SdkRuntimePreflightStatus.READY if not observation.blockers else SdkRuntimePreflightStatus.FAILED,
            node_executable=observation.node_executable,
            node_version=observation.node_version,
            sdk_package_name=observation.sdk_package_name,
            blockers=observation.blockers,
        )
