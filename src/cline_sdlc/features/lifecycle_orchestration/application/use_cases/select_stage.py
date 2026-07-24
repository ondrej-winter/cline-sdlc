"""Use case for mapping explicit inputs to lifecycle stages."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.domain.stage import stage_for_input_kind

if TYPE_CHECKING:
    from cline_sdlc.features.lifecycle_orchestration.application.dtos.invocation import InvocationRequest


class SelectLifecycleStage:
    """Map one explicit invocation input to its bounded lifecycle stage."""

    def execute(self, request: InvocationRequest) -> InvocationRequest:
        """Return the request enriched with the selected lifecycle stage."""
        return replace(request, stage=stage_for_input_kind(request.source.kind))
