"""Tests for operation-policy application use case."""

from __future__ import annotations

import pytest

from cline_sdlc.features.operation_policy.application.dtos.operation import (
    ClassifyOperationRequest,
    PlannedOperationAuthorization,
    PlannedOperationKind,
)
from cline_sdlc.features.operation_policy.application.use_cases.classify_operation import ClassifyOperation


def test_classifies_structured_command_request() -> None:
    decision = ClassifyOperation().execute(
        ClassifyOperationRequest(executable="uv", arguments=("run", "pytest", "tests/unit/features/operation_policy/"))
    )

    assert decision.is_allowed is True
    assert decision.rule_id == "allow_local_validation"


def test_authorizes_exact_planned_dependency_operation_with_coordinated_files() -> None:
    authorization = PlannedOperationAuthorization(
        kind=PlannedOperationKind.DEPENDENCY,
        material_requirement="Task 7 requires adding the approved parser dependency.",
        executable="uv",
        arguments=("add", "example-parser"),
        owned_paths=("pyproject.toml", "uv.lock"),
    )

    decision = ClassifyOperation().execute(
        ClassifyOperationRequest(
            executable="uv",
            arguments=("add", "example-parser"),
            authorization=authorization,
        )
    )

    assert decision.is_allowed is True
    assert decision.rule_id == "allow_planned_dependency_operation"
    assert decision.accepted_material_requirement == authorization.material_requirement


def test_authorizes_exact_planned_bounded_network_operation() -> None:
    destination = "https://example.com/schema.json"
    authorization = PlannedOperationAuthorization(
        kind=PlannedOperationKind.NETWORK,
        material_requirement="Task 8 requires downloading the public schema.",
        executable="curl",
        arguments=("--fail", "--silent", destination),
        destination=destination,
    )

    decision = ClassifyOperation().execute(
        ClassifyOperationRequest(
            executable="curl",
            arguments=("--fail", "--silent", destination),
            authorization=authorization,
        )
    )

    assert decision.is_allowed is True
    assert decision.rule_id == "allow_planned_network_operation"


@pytest.mark.parametrize(
    ("executable", "request_arguments", "owned_paths", "rule_id"),
    [
        ("uv", ("add", "different-package"), ("pyproject.toml", "uv.lock"), "deny_planned_operation_mismatch"),
        ("uv", ("add", "example-parser"), ("pyproject.toml",), "deny_incomplete_dependency_ownership"),
        ("pip", ("install", "example-parser"), ("pyproject.toml", "uv.lock"), "deny_planned_operation_mismatch"),
    ],
)
def test_denies_mismatched_or_incompletely_owned_planned_dependency_operation(
    executable: str,
    request_arguments: tuple[str, ...],
    owned_paths: tuple[str, ...],
    rule_id: str,
) -> None:
    planned_arguments = ("add", "example-parser")
    authorization = PlannedOperationAuthorization(
        kind=PlannedOperationKind.DEPENDENCY,
        material_requirement="Task 7 requires adding the approved parser dependency.",
        executable="uv",
        arguments=planned_arguments,
        owned_paths=owned_paths,
    )

    decision = ClassifyOperation().execute(
        ClassifyOperationRequest(executable=executable, arguments=request_arguments, authorization=authorization)
    )

    assert decision.is_allowed is False
    assert decision.rule_id == rule_id


def test_secret_reference_remains_denied_despite_plan_authorization() -> None:
    destination = "https://example.com/private.json"
    arguments = ("--token", "secret-value", destination)
    authorization = PlannedOperationAuthorization(
        kind=PlannedOperationKind.NETWORK,
        material_requirement="Task 8 requires downloading a schema.",
        executable="curl",
        arguments=arguments,
        destination=destination,
    )

    decision = ClassifyOperation().execute(
        ClassifyOperationRequest(executable="curl", arguments=arguments, authorization=authorization)
    )

    assert decision.is_allowed is False
    assert decision.rule_id == "deny_secret_access"
    assert "secret-value" not in decision.proposed_operation


def test_dependency_operation_stays_denied_without_plan_authorization() -> None:
    decision = ClassifyOperation().execute(
        ClassifyOperationRequest(executable="uv", arguments=("add", "example-parser"))
    )

    assert decision.is_allowed is False
    assert decision.rule_id == "deny_dependency_operation"


@pytest.mark.parametrize("write_argument", ["--request=POST", "-d", "--post-file=payload.json"])
def test_network_write_remains_denied_despite_plan_authorization(write_argument: str) -> None:
    destination = "https://example.com/release"
    arguments = (write_argument, destination)
    authorization = PlannedOperationAuthorization(
        kind=PlannedOperationKind.NETWORK,
        material_requirement="Task 8 requires a bounded network read.",
        executable="curl",
        arguments=arguments,
        destination=destination,
    )

    decision = ClassifyOperation().execute(
        ClassifyOperationRequest(executable="curl", arguments=arguments, authorization=authorization)
    )

    assert decision.is_allowed is False
    assert decision.rule_id == "deny_network_external_effect"


def test_rejects_unsafe_planned_operation_metadata() -> None:
    with pytest.raises(ValueError, match="owned_paths"):
        PlannedOperationAuthorization(
            kind=PlannedOperationKind.DEPENDENCY,
            material_requirement="Task 7 requires a dependency change.",
            executable="uv",
            arguments=("lock",),
            owned_paths=("../pyproject.toml", "uv.lock"),
        )
