"""Discover validation commands without executing repository configuration."""

from __future__ import annotations

from cline_sdlc.features.lifecycle_orchestration.application.dtos.validation import (
    ValidationCommand,
    ValidationCommandCandidate,
    ValidationCommandSource,
    ValidationDiscoveryBlocker,
    ValidationDiscoveryRequest,
    ValidationDiscoveryResult,
    ValidationEvidence,
    ValidationEvidenceStatus,
    ValidationScope,
    normalized_validation_path,
)

BROAD_VALIDATION_COMMANDS = (
    ValidationCommand(executable="uv", arguments=("run", "ruff", "format", "--check", ".")),
    ValidationCommand(executable="uv", arguments=("run", "ruff", "check", ".")),
    ValidationCommand(executable="uv", arguments=("run", "mypy", ".")),
    ValidationCommand(executable="uv", arguments=("run", "pytest")),
)
BUILD_VALIDATION_COMMAND = ValidationCommand(executable="uv", arguments=("build",))


class DiscoverValidationCommands:
    """Select focused and broad validation command candidates for later execution."""

    def execute(self, request: ValidationDiscoveryRequest) -> ValidationDiscoveryResult:
        """Return command candidates and not-run evidence without running subprocesses."""
        blockers = _path_blockers(request.changed_paths)
        if blockers:
            return ValidationDiscoveryResult(
                evidence=(
                    ValidationEvidence(
                        scope=ValidationScope.FOCUSED,
                        command=None,
                        status=ValidationEvidenceStatus.BLOCKED,
                        summary="validation path discovery failed before command execution",
                    ),
                ),
                blockers=blockers,
            )

        commands = [
            *_focused_commands(request),
            *_broad_commands(request),
        ]
        evidence = tuple(
            ValidationEvidence(
                scope=candidate.scope,
                command=candidate.command,
                status=ValidationEvidenceStatus.NOT_RUN,
                summary="validation command discovered but not run in discovery slice",
            )
            for candidate in commands
        )
        return ValidationDiscoveryResult(commands=tuple(commands), evidence=evidence)


def _focused_commands(request: ValidationDiscoveryRequest) -> tuple[ValidationCommandCandidate, ...]:
    if request.explicit_focused_commands:
        return tuple(
            ValidationCommandCandidate(
                scope=ValidationScope.FOCUSED,
                command=command,
                source=ValidationCommandSource.EXPLICIT,
                reason="explicit focused validation command supplied by caller",
            )
            for command in request.explicit_focused_commands
        )

    pytest_targets = _pytest_targets(request.changed_paths)
    if not pytest_targets:
        return ()
    return (
        ValidationCommandCandidate(
            scope=ValidationScope.FOCUSED,
            command=ValidationCommand(executable="uv", arguments=("run", "pytest", *pytest_targets)),
            source=ValidationCommandSource.DISCOVERED,
            reason="changed Python paths map to focused pytest targets",
        ),
    )


def _broad_commands(request: ValidationDiscoveryRequest) -> tuple[ValidationCommandCandidate, ...]:
    if not request.include_broad_commands:
        return ()
    commands = (
        (*BROAD_VALIDATION_COMMANDS, BUILD_VALIDATION_COMMAND)
        if request.include_build_command
        else BROAD_VALIDATION_COMMANDS
    )
    return tuple(
        ValidationCommandCandidate(
            scope=ValidationScope.BROAD,
            command=command,
            source=ValidationCommandSource.DEFAULT,
            reason="default uv-backed repository quality gate command",
        )
        for command in commands
    )


def _pytest_targets(changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    targets: list[str] = []
    for path in changed_paths:
        normalized = normalized_validation_path(path)
        if normalized.startswith("tests/") and normalized.endswith(".py"):
            targets.append(normalized)
        elif normalized.startswith("src/") and normalized.endswith(".py"):
            targets.append(_source_path_to_test_target(normalized))
    return tuple(dict.fromkeys(targets))


def _source_path_to_test_target(path: str) -> str:
    without_src = path.removeprefix("src/cline_sdlc/").removesuffix(".py")
    if without_src.startswith("features/"):
        return f"tests/unit/{without_src}"
    return "tests/unit/"


def _path_blockers(changed_paths: tuple[str, ...]) -> tuple[ValidationDiscoveryBlocker, ...]:
    blockers: list[ValidationDiscoveryBlocker] = []
    for path in changed_paths:
        try:
            normalized_validation_path(path)
        except ValueError as err:
            blockers.append(
                ValidationDiscoveryBlocker(
                    code="invalid_validation_path",
                    summary="validation discovery paths must be repository-relative and non-traversing",
                    evidence=str(err),
                )
            )
    return tuple(blockers)
