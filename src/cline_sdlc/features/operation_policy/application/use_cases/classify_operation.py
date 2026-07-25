"""Use case for classifying proposed command operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.operation_policy.domain.policy import (
    CommandOperation,
    OperationDecision,
    PlannedOperation,
    classify_operation,
)

if TYPE_CHECKING:
    from cline_sdlc.features.operation_policy.application.dtos.operation import ClassifyOperationRequest


class ClassifyOperation:
    """Classify command operations before execution under the balanced profile."""

    def execute(self, request: ClassifyOperationRequest) -> OperationDecision:
        """Return a fail-closed operation-policy decision."""
        authorization = request.authorization
        return classify_operation(
            CommandOperation(executable=request.executable, arguments=request.arguments),
            authorization=(
                PlannedOperation(
                    kind=authorization.kind.value,
                    executable=authorization.executable,
                    arguments=authorization.arguments,
                    material_requirement=authorization.material_requirement,
                    destination=authorization.destination,
                    owned_paths=authorization.owned_paths,
                )
                if authorization is not None
                else None
            ),
        )
