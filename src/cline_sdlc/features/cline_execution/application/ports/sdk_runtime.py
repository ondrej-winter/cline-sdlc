"""Outbound port for Cline SDK adapter runtime inspection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import (
        SdkRuntimeObservation,
        SdkRuntimePreflightRequest,
    )


class SdkRuntimeProbePort(Protocol):
    """Inspect adapter-local Node.js and SDK package prerequisites."""

    def inspect(self, request: SdkRuntimePreflightRequest) -> SdkRuntimeObservation:
        """Return observed SDK runtime facts and fail-closed blockers."""
