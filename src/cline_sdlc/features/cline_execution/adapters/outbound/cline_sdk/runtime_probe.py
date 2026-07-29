"""Runtime probe for the adapter-local Cline SDK runner."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import SdkRuntimeBlocker, SdkRuntimeObservation

if TYPE_CHECKING:
    from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import SdkRuntimePreflightRequest

_VERSION_PATTERN = re.compile(r"v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)")
_COMMAND_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class CommandResult:
    """Captured result for one runtime probe command."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


class CommandRunnerPort(Protocol):
    """Run a bounded command for SDK runtime inspection."""

    def run(self, command: tuple[str, ...], *, cwd: str | None = None) -> CommandResult:
        """Execute the command and return safe captured output."""


class SubprocessCommandRunner:
    """Run SDK runtime probe commands without shell interpolation."""

    def run(self, command: tuple[str, ...], *, cwd: str | None = None) -> CommandResult:
        """Execute a bounded subprocess command and capture output."""
        try:
            completed = subprocess.run(  # noqa: S603
                list(command),
                cwd=cwd,
                capture_output=True,
                check=False,
                text=True,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as err:
            return CommandResult(exit_code=1, stderr=str(err))
        return CommandResult(exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


class ClineSdkRuntimeProbe:
    """Inspect Node.js and adapter-local `@cline/sdk` package availability."""

    def __init__(self, command_runner: CommandRunnerPort | None = None) -> None:
        self._command_runner = command_runner or SubprocessCommandRunner()

    def inspect(self, request: SdkRuntimePreflightRequest) -> SdkRuntimeObservation:
        """Return SDK runtime facts and fail-closed blockers for the runner directory."""
        executable = shutil.which(request.node_command[0])
        if executable is None:
            return SdkRuntimeObservation(
                node_executable=None,
                node_version=None,
                sdk_package_name=request.sdk_package_name,
                blockers=(
                    SdkRuntimeBlocker(
                        code="node_missing",
                        summary="Node.js executable was not found for the Cline SDK adapter.",
                        evidence=f"command={request.node_command[0]}",
                    ),
                ),
            )

        version_result = self._command_runner.run((*request.node_command, "--version"))
        node_version = version_result.stdout.strip() or version_result.stderr.strip() or None
        version_blocker = _version_blocker(
            node_version=node_version,
            minimum_major_version=request.minimum_node_major_version,
        )
        if version_blocker is not None:
            return SdkRuntimeObservation(
                node_executable=executable,
                node_version=node_version,
                sdk_package_name=request.sdk_package_name,
                blockers=(version_blocker,),
            )

        package_result = self._command_runner.run(
            (
                *request.node_command,
                "--input-type=module",
                "--eval",
                f"import.meta.resolve('{request.sdk_package_name}')",
            ),
            cwd=request.runner_directory.as_posix(),
        )
        if package_result.exit_code != 0:
            return SdkRuntimeObservation(
                node_executable=executable,
                node_version=node_version,
                sdk_package_name=request.sdk_package_name,
                blockers=(
                    SdkRuntimeBlocker(
                        code="cline_sdk_missing",
                        summary="@cline/sdk is not resolvable from the adapter runner directory.",
                        evidence=f"runner_directory={request.runner_directory.as_posix()}",
                    ),
                ),
            )

        return SdkRuntimeObservation(
            node_executable=executable,
            node_version=node_version,
            sdk_package_name=request.sdk_package_name,
            sdk_resolved=True,
        )


def _version_blocker(*, node_version: str | None, minimum_major_version: int) -> SdkRuntimeBlocker | None:
    if node_version is None:
        return SdkRuntimeBlocker(
            code="node_version_unknown",
            summary="Node.js version could not be detected for the Cline SDK adapter.",
            evidence="node --version produced no version output",
        )
    match = _VERSION_PATTERN.fullmatch(node_version.strip())
    if match is None:
        return SdkRuntimeBlocker(
            code="node_version_unknown",
            summary="Node.js version output was not recognized for the Cline SDK adapter.",
            evidence=f"observed={node_version}",
        )
    major = int(match.group("major"))
    if major < minimum_major_version:
        return SdkRuntimeBlocker(
            code="node_version_unsupported",
            summary=f"Node.js {minimum_major_version} or newer is required for the Cline SDK adapter.",
            evidence=f"observed={node_version}",
        )
    return None
