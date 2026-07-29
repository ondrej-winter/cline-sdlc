"""DTOs for SDK adapter runtime preflight."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

MINIMUM_NODE_MAJOR_VERSION = 22
DEFAULT_SDK_PACKAGE_NAME = "@cline/sdk"
DEFAULT_NODE_RUNNER_DIRECTORY = Path("src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner")


class SdkRuntimePreflightStatus(StrEnum):
    """Terminal status for SDK runtime prerequisite checks."""

    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class SdkRuntimeBlocker:
    """Actionable reason that prevents using the Cline SDK adapter."""

    code: str
    summary: str
    evidence: str

    def __post_init__(self) -> None:
        if not self.code.strip():
            message = "SDK runtime blocker code must not be empty"
            raise ValueError(message)
        if not self.summary.strip():
            message = "SDK runtime blocker summary must not be empty"
            raise ValueError(message)
        if not self.evidence.strip():
            message = "SDK runtime blocker evidence must not be empty"
            raise ValueError(message)


@dataclass(frozen=True)
class SdkRuntimePreflightRequest:
    """Application request to verify adapter-local Cline SDK runtime readiness."""

    node_command: tuple[str, ...] = ("node",)
    runner_directory: Path = DEFAULT_NODE_RUNNER_DIRECTORY
    sdk_package_name: str = DEFAULT_SDK_PACKAGE_NAME
    minimum_node_major_version: int = MINIMUM_NODE_MAJOR_VERSION

    def __post_init__(self) -> None:
        if not self.node_command:
            message = "SDK runtime node command must not be empty"
            raise ValueError(message)
        if any(not argument for argument in self.node_command):
            message = "SDK runtime node command arguments must not be empty"
            raise ValueError(message)
        if not self.sdk_package_name.strip():
            message = "SDK package name must not be empty"
            raise ValueError(message)
        if self.minimum_node_major_version <= 0:
            message = "minimum Node.js major version must be positive"
            raise ValueError(message)


@dataclass(frozen=True)
class SdkRuntimeObservation:
    """Observed adapter runtime facts returned by an outbound runtime probe."""

    node_executable: str | None
    node_version: str | None
    sdk_package_name: str = DEFAULT_SDK_PACKAGE_NAME
    sdk_resolved: bool = False
    blockers: tuple[SdkRuntimeBlocker, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SdkRuntimePreflightResult:
    """Typed SDK runtime readiness result for adapter gate checks."""

    status: SdkRuntimePreflightStatus
    node_executable: str | None
    node_version: str | None
    sdk_package_name: str
    blockers: tuple[SdkRuntimeBlocker, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        """Return whether the SDK adapter runtime prerequisites are satisfied."""
        return self.status is SdkRuntimePreflightStatus.READY
