"""Tests for SDK adapter runtime preflight."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import (
    DEFAULT_NODE_RUNNER_DIRECTORY,
    DEFAULT_SDK_PACKAGE_NAME,
    MINIMUM_NODE_MAJOR_VERSION,
    SdkRuntimeBlocker,
    SdkRuntimeObservation,
    SdkRuntimePreflightRequest,
    SdkRuntimePreflightStatus,
)
from cline_sdlc.features.cline_execution.application.use_cases.preflight_sdk_runtime import PreflightSdkRuntime


@dataclass
class RecordingSdkRuntimeProbe:
    """Fake SDK runtime probe that records preflight requests."""

    observation: SdkRuntimeObservation
    request: SdkRuntimePreflightRequest | None = None

    def inspect(self, request: SdkRuntimePreflightRequest) -> SdkRuntimeObservation:
        self.request = request
        return self.observation


def test_preflight_is_ready_when_node_and_sdk_are_available() -> None:
    probe = RecordingSdkRuntimeProbe(
        SdkRuntimeObservation(
            node_executable="/opt/homebrew/bin/node",
            node_version="v22.11.0",
            sdk_resolved=True,
        )
    )

    result = PreflightSdkRuntime(probe).execute(SdkRuntimePreflightRequest())

    assert result.status is SdkRuntimePreflightStatus.READY
    assert result.ready
    assert result.node_executable == "/opt/homebrew/bin/node"
    assert result.node_version == "v22.11.0"
    assert result.sdk_package_name == DEFAULT_SDK_PACKAGE_NAME
    assert result.blockers == ()
    assert probe.request == SdkRuntimePreflightRequest()


@pytest.mark.parametrize(
    ("blocker", "expected_code"),
    [
        (
            SdkRuntimeBlocker(
                code="node_missing",
                summary="Node.js executable was not found.",
                evidence="node command failed to start",
            ),
            "node_missing",
        ),
        (
            SdkRuntimeBlocker(
                code="node_version_unsupported",
                summary="Node.js 22 or newer is required.",
                evidence="observed v20.19.0",
            ),
            "node_version_unsupported",
        ),
        (
            SdkRuntimeBlocker(
                code="cline_sdk_missing",
                summary="@cline/sdk is not resolvable from the adapter runner directory.",
                evidence="npm dependencies have not been installed",
            ),
            "cline_sdk_missing",
        ),
    ],
)
def test_preflight_fails_closed_for_runtime_blockers(blocker: SdkRuntimeBlocker, expected_code: str) -> None:
    probe = RecordingSdkRuntimeProbe(
        SdkRuntimeObservation(
            node_executable=None,
            node_version=None,
            sdk_resolved=False,
            blockers=(blocker,),
        )
    )

    result = PreflightSdkRuntime(probe).execute(SdkRuntimePreflightRequest())

    assert result.status is SdkRuntimePreflightStatus.FAILED
    assert not result.ready
    assert result.blockers[0].code == expected_code


def test_preflight_request_defaults_to_adapter_local_runner_contract() -> None:
    request = SdkRuntimePreflightRequest()

    assert request.node_command == ("node",)
    assert request.runner_directory == DEFAULT_NODE_RUNNER_DIRECTORY
    assert request.sdk_package_name == DEFAULT_SDK_PACKAGE_NAME
    assert request.minimum_node_major_version == MINIMUM_NODE_MAJOR_VERSION


def test_preflight_request_rejects_invalid_runtime_contract_values() -> None:
    with pytest.raises(ValueError, match="node command"):
        SdkRuntimePreflightRequest(node_command=())

    with pytest.raises(ValueError, match="arguments"):
        SdkRuntimePreflightRequest(node_command=("node", ""))

    with pytest.raises(ValueError, match="package"):
        SdkRuntimePreflightRequest(sdk_package_name=" ")

    with pytest.raises(ValueError, match="version"):
        SdkRuntimePreflightRequest(minimum_node_major_version=0)


def test_preflight_request_accepts_explicit_adapter_runner_directory() -> None:
    request = SdkRuntimePreflightRequest(runner_directory=Path("custom/node_runner"))

    assert request.runner_directory == Path("custom/node_runner")
