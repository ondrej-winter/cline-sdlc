"""Tests for operation-policy application use case."""

from __future__ import annotations

from cline_sdlc.features.operation_policy.application.dtos.operation import ClassifyOperationRequest
from cline_sdlc.features.operation_policy.application.use_cases.classify_operation import ClassifyOperation


def test_classifies_structured_command_request() -> None:
    decision = ClassifyOperation().execute(
        ClassifyOperationRequest(executable="uv", arguments=("run", "pytest", "tests/unit/features/operation_policy/"))
    )

    assert decision.is_allowed is True
    assert decision.rule_id == "allow_local_validation"
