"""Balanced-profile command operation policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath


class OperationDecisionStatus(StrEnum):
    """Allowed operation-policy decision statuses."""

    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True)
class CommandOperation:
    """Structured executable and argument-array operation proposed for execution."""

    executable: str
    arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.executable.strip():
            message = "operation executable must not be empty"
            raise ValueError(message)
        if any(not argument.strip() for argument in self.arguments):
            message = "operation arguments must not contain empty values"
            raise ValueError(message)
        if any("\x00" in value for value in (self.executable, *self.arguments)):
            message = "operation values must not contain NUL bytes"
            raise ValueError(message)

    @property
    def executable_name(self) -> str:
        """Return the basename-like executable name used for allow/deny matching."""
        return PurePosixPath(self.executable).name

    def redacted_command(self) -> str:
        """Return a safe command summary without known secret-like argument values."""
        values = (self.executable, *self.arguments)
        redacted_values: list[str] = []
        redact_next = False
        for value in values:
            if redact_next:
                redacted_values.append("<redacted>")
                redact_next = False
                continue
            lower_value = value.lower()
            if any(token in lower_value for token in _SECRET_TOKENS):
                redacted_values.append(_redact_inline_secret(value))
                if "=" not in value:
                    redact_next = True
            else:
                redacted_values.append(value)
        return " ".join(redacted_values)


@dataclass(frozen=True)
class OperationDecision:
    """Balanced-profile classification decision for one command operation."""

    status: OperationDecisionStatus
    rule_id: str
    summary: str
    proposed_operation: str

    @property
    def is_allowed(self) -> bool:
        """Return whether the operation may proceed automatically."""
        return self.status is OperationDecisionStatus.ALLOWED


_SECRET_TOKENS = frozenset(("token", "secret", "password", "passwd", "credential", "keychain"))
_NETWORK_EXECUTABLES = frozenset(("curl", "wget", "ssh", "scp", "rsync", "nc", "ncat", "ftp", "sftp"))
_PACKAGE_EXECUTABLES = frozenset(("npm", "npx", "pnpm", "yarn", "pip", "pipx", "brew"))
_SYSTEM_EXECUTABLES = frozenset(("sudo", "su", "chmod", "chown", "launchctl", "systemctl"))
_SHELL_EXECUTABLES = frozenset(("sh", "bash", "zsh", "fish", "osascript"))
_DESTRUCTIVE_EXECUTABLES = frozenset(("rm", "rmdir", "mv"))
_DATABASE_EXECUTABLES = frozenset(("psql", "mysql", "sqlite3", "alembic", "django-admin"))
_REMOTE_OR_DEPLOY_EXECUTABLES = frozenset(("docker", "kubectl", "gh", "twine", "semantic-release"))
_INTERPRETER_EXECUTABLES = frozenset(("python", "python3", "node", "ruby", "perl"))

_ALLOWED_GIT_SUBCOMMANDS = frozenset(("status", "diff", "log", "show", "branch", "rev-parse"))
_DENIED_GIT_SUBCOMMANDS = frozenset(
    (
        "add",
        "am",
        "bisect",
        "checkout",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "fetch",
        "merge",
        "pull",
        "push",
        "rebase",
        "reset",
        "restore",
        "revert",
        "rm",
        "stash",
        "switch",
        "tag",
        "worktree",
    ),
)
_ALLOWED_UV_RUN_TOOLS = frozenset(("ruff", "mypy", "pytest"))
_MINIMUM_UV_RUN_ARGUMENTS = 2
_DANGEROUS_GIT_FLAGS = frozenset(("--force", "-f", "--hard", "--delete", "-D", "--no-verify"))

type _ExecutablePolicy = tuple[frozenset[str], str, str]
_EXECUTABLE_POLICIES: tuple[_ExecutablePolicy, ...] = (
    (_NETWORK_EXECUTABLES, "deny_network_access", "network-capable commands require manual approval"),
    (_PACKAGE_EXECUTABLES, "deny_dependency_operation", "dependency commands require manual approval"),
    (_SYSTEM_EXECUTABLES, "deny_system_change", "system or privilege operations require manual approval"),
    (_SHELL_EXECUTABLES, "deny_shell_wrapper", "shell wrappers are not classified as safe operations"),
    (_DESTRUCTIVE_EXECUTABLES, "deny_destructive_filesystem", "destructive commands require manual approval"),
    (_DATABASE_EXECUTABLES, "deny_database_operation", "database commands require manual approval"),
    (_REMOTE_OR_DEPLOY_EXECUTABLES, "deny_external_effect", "external-effect commands require manual approval"),
    (_INTERPRETER_EXECUTABLES, "deny_interpreter", "interpreter commands are not allowed by this policy slice"),
)


def classify_operation(operation: CommandOperation) -> OperationDecision:
    """Classify one structured operation according to the balanced profile."""
    secret_decision = _deny_if_contains_secret_reference(operation)
    if secret_decision is not None:
        return secret_decision

    executable = operation.executable_name
    policy_decision = _deny_by_executable_policy(operation, executable=executable)
    if policy_decision is not None:
        return policy_decision
    if executable == "git":
        return _classify_git(operation)
    if executable == "uv":
        return _classify_uv(operation)
    return _deny(
        operation,
        rule_id="deny_unclassified_operation",
        summary="operation risk could not be classified confidently",
    )


def _classify_git(operation: CommandOperation) -> OperationDecision:
    args = operation.arguments
    if "--no-pager" not in args:
        return _deny(operation, rule_id="deny_git_pager", summary="git inspection must disable pagers")
    subcommand = _git_subcommand(args)
    subcommand_decision = _deny_by_git_subcommand(operation, subcommand=subcommand)
    if subcommand_decision is not None:
        return subcommand_decision
    if any(arg in _DANGEROUS_GIT_FLAGS for arg in args):
        return _deny(
            operation,
            rule_id="deny_git_dangerous_flag",
            summary="dangerous Git flags require manual approval",
        )
    return _allow(operation, rule_id="allow_git_inspection", summary="non-interactive Git inspection is allowed")


def _classify_uv(operation: CommandOperation) -> OperationDecision:
    args = operation.arguments
    if not args:
        return _deny(operation, rule_id="deny_unclassified_uv", summary="uv operation must include a subcommand")
    if args[0] == "build" and len(args) == 1:
        return _allow(operation, rule_id="allow_local_build", summary="local project build is allowed")
    if args[0] != "run" or len(args) < _MINIMUM_UV_RUN_ARGUMENTS:
        return _deny(
            operation,
            rule_id="deny_dependency_operation",
            summary="uv dependency operations require approval",
        )
    tool = PurePosixPath(args[1]).name
    if tool in _ALLOWED_UV_RUN_TOOLS:
        return _allow(
            operation,
            rule_id="allow_local_validation",
            summary="configured local validation command is allowed",
        )
    return _deny(operation, rule_id="deny_unclassified_uv_run", summary="uv run tool is not automatically allowed")


def _git_subcommand(args: tuple[str, ...]) -> str | None:
    for arg in args:
        if arg == "--no-pager" or arg.startswith(("-c", "-")):
            continue
        return arg
    return None


def _deny_by_executable_policy(operation: CommandOperation, *, executable: str) -> OperationDecision | None:
    for executables, rule_id, summary in _EXECUTABLE_POLICIES:
        if executable in executables:
            return _deny(operation, rule_id=rule_id, summary=summary)
    return None


def _deny_by_git_subcommand(operation: CommandOperation, *, subcommand: str | None) -> OperationDecision | None:
    if subcommand is None:
        return _deny(operation, rule_id="deny_unclassified_git", summary="git operation must include a subcommand")
    if subcommand in _DENIED_GIT_SUBCOMMANDS:
        return _deny(operation, rule_id="deny_git_mutation", summary="mutating Git operations require manual approval")
    if subcommand not in _ALLOWED_GIT_SUBCOMMANDS:
        return _deny(operation, rule_id="deny_unclassified_git", summary="git subcommand is not automatically allowed")
    return None


def _deny_if_contains_secret_reference(operation: CommandOperation) -> OperationDecision | None:
    values = (operation.executable, *operation.arguments)
    if any(any(token in value.lower() for token in _SECRET_TOKENS) for value in values):
        return _deny(operation, rule_id="deny_secret_access", summary="credential references require manual approval")
    return None


def _allow(operation: CommandOperation, *, rule_id: str, summary: str) -> OperationDecision:
    return OperationDecision(
        status=OperationDecisionStatus.ALLOWED,
        rule_id=rule_id,
        summary=summary,
        proposed_operation=operation.redacted_command(),
    )


def _deny(operation: CommandOperation, *, rule_id: str, summary: str) -> OperationDecision:
    return OperationDecision(
        status=OperationDecisionStatus.APPROVAL_REQUIRED,
        rule_id=rule_id,
        summary=summary,
        proposed_operation=operation.redacted_command(),
    )


def _redact_inline_secret(value: str) -> str:
    if "=" not in value:
        return value
    key, _separator, _secret = value.partition("=")
    return f"{key}=<redacted>"
