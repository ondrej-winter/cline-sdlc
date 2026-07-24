"""Use case for classifying proposed command operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.operation_policy.domain.policy import CommandOperation, OperationDecision, classify_operation

if TYPE_CHECKING:
    from cline_sdlc.features.operation_policy.application.dtos.operation import ClassifyOperationRequest


class ClassifyOperation:
    """Classify command operations before execution under the balanced profile."""

    def execute(self, request: ClassifyOperationRequest) -> OperationDecision:
        """Return a fail-closed operation-policy decision."""
        return classify_operation(CommandOperation(executable=request.executable, arguments=request.arguments))
