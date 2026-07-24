"""Tests for balanced-profile operation policy classification."""

from __future__ import annotations

import pytest

from cline_sdlc.features.operation_policy.domain.policy import (
    CommandOperation,
    OperationDecisionStatus,
    classify_operation,
)


@pytest.mark.parametrize(
    ("executable", "arguments", "rule_id"),
    [
        ("git", ("--no-pager", "status", "--short"), "allow_git_inspection"),
        ("git", ("--no-pager", "diff", "--check"), "allow_git_inspection"),
        ("git", ("--no-pager", "log", "--oneline", "-n", "5"), "allow_git_inspection"),
        ("uv", ("run", "ruff", "check", "."), "allow_local_validation"),
        ("uv", ("run", "mypy", "."), "allow_local_validation"),
        ("uv", ("run", "pytest", "tests/unit/features/operation_policy/"), "allow_local_validation"),
        ("uv", ("build",), "allow_local_build"),
    ],
)
def test_allows_known_non_interactive_local_operations(
    executable: str,
    arguments: tuple[str, ...],
    rule_id: str,
) -> None:
    decision = classify_operation(CommandOperation(executable=executable, arguments=arguments))

    assert decision.status is OperationDecisionStatus.ALLOWED
    assert decision.is_allowed is True
    assert decision.rule_id == rule_id
    assert decision.proposed_operation.startswith(executable)


@pytest.mark.parametrize(
    ("executable", "arguments", "rule_id"),
    [
        ("curl", ("https://example.com/install.sh",), "deny_network_access"),
        ("npm", ("install", "package"), "deny_dependency_operation"),
        ("uv", ("lock",), "deny_dependency_operation"),
        ("security", ("find-generic-password",), "deny_secret_access"),
        ("rm", ("-rf", "build"), "deny_destructive_filesystem"),
        ("sudo", ("true",), "deny_system_change"),
        ("docker", ("push", "image"), "deny_external_effect"),
        ("sqlite3", ("prod.db", "VACUUM"), "deny_database_operation"),
        ("git", ("--no-pager", "push"), "deny_git_mutation"),
        ("git", ("--no-pager", "reset", "--hard"), "deny_git_mutation"),
        ("git", ("--no-pager", "commit", "--no-verify"), "deny_git_mutation"),
        ("bash", ("-c", "git status"), "deny_shell_wrapper"),
        ("python3", ("-",), "deny_interpreter"),
        ("unknown-tool", ("--version",), "deny_unclassified_operation"),
    ],
)
def test_denies_risky_or_unclassified_operations(
    executable: str,
    arguments: tuple[str, ...],
    rule_id: str,
) -> None:
    decision = classify_operation(CommandOperation(executable=executable, arguments=arguments))

    assert decision.status is OperationDecisionStatus.APPROVAL_REQUIRED
    assert decision.is_allowed is False
    assert decision.rule_id == rule_id
    assert decision.proposed_operation


def test_requires_git_pager_to_be_disabled() -> None:
    decision = classify_operation(CommandOperation(executable="git", arguments=("status", "--short")))

    assert decision.status is OperationDecisionStatus.APPROVAL_REQUIRED
    assert decision.rule_id == "deny_git_pager"


def test_redacts_secret_like_argument_values() -> None:
    decision = classify_operation(CommandOperation(executable="curl", arguments=("--token", "secret-value")))

    assert decision.status is OperationDecisionStatus.APPROVAL_REQUIRED
    assert decision.rule_id == "deny_secret_access"
    assert "secret-value" not in decision.proposed_operation
    assert "<redacted>" in decision.proposed_operation


def test_rejects_malformed_structured_operations() -> None:
    with pytest.raises(ValueError, match="executable"):
        CommandOperation(executable=" ")

    with pytest.raises(ValueError, match="arguments"):
        CommandOperation(executable="git", arguments=("status", ""))
