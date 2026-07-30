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


class SdkRuntimeCapability(StrEnum):
    """SDK execution capabilities required by the SDLC adapter gate."""

    NODE_RUNTIME = "node_runtime"
    SDK_PACKAGE = "sdk_package"
    BOUNDED_SESSION = "bounded_session"
    EXPLICIT_SESSION_CONTEXT = "explicit_session_context"
    EVENT_EVIDENCE_STREAM = "event_evidence_stream"
    STRUCTURED_TERMINAL_OUTCOME = "structured_terminal_outcome"
    TIMEOUT_INTERRUPTION = "timeout_interruption"
    DIAGNOSTIC_REFERENCES = "diagnostic_references"
    AGENT_RUN = "agent_run"
    CLINECORE_SESSION = "clinecore_session"
    PROGRAMMATIC_MODE_SWITCH = "programmatic_mode_switch"
    TOOL_POLICY_COVERAGE = "tool_policy_coverage"
    PERMISSION_APPROVAL = "permission_approval"
    PLAN_ACT_OBSERVATION = "plan_act_observation"
    ACT_AUTHORIZATION = "act_authorization"
    CLI_PROBE_EXCLUDED = "cli_probe_excluded"


class SdkRuntimeCapabilityStatus(StrEnum):
    """Evidence status for one SDK runtime capability."""

    PROVEN = "proven"
    UNPROVEN = "unproven"
    BLOCKED = "blocked"


class SdkRuntimeCapabilitySource(StrEnum):
    """Source category for a capability claim."""

    ADAPTER_CONTRACT = "adapter_contract"
    AGENT_SMOKE = "agent_smoke"
    CLINECORE_SMOKE = "clinecore_smoke"
    FAKE_SDK_TEST = "fake_sdk_test"
    OFFICIAL_DOCS = "official_docs"
    CLI_PROBE = "cli_probe"


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
class SdkRuntimeCapabilityEvidence:
    """Safe evidence for one SDK execution capability."""

    capability: SdkRuntimeCapability
    status: SdkRuntimeCapabilityStatus
    source: SdkRuntimeCapabilitySource
    summary: str

    def __post_init__(self) -> None:
        if not self.summary.strip():
            message = "SDK runtime capability evidence summary must not be empty"
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
    capabilities: tuple[SdkRuntimeCapabilityEvidence, ...] = field(default_factory=tuple)
    blockers: tuple[SdkRuntimeBlocker, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SdkRuntimePreflightResult:
    """Typed SDK runtime readiness result for adapter gate checks."""

    status: SdkRuntimePreflightStatus
    node_executable: str | None
    node_version: str | None
    sdk_package_name: str
    capabilities: tuple[SdkRuntimeCapabilityEvidence, ...] = field(default_factory=tuple)
    blockers: tuple[SdkRuntimeBlocker, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        """Return whether the SDK adapter runtime prerequisites are satisfied."""
        return self.status is SdkRuntimePreflightStatus.READY
