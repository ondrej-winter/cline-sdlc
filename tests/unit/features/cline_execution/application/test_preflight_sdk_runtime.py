"""Tests for SDK adapter runtime preflight."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from cline_sdlc.features.cline_execution.application.dtos.sdk_runtime import (
    DEFAULT_NODE_RUNNER_DIRECTORY,
    DEFAULT_SDK_PACKAGE_NAME,
    MINIMUM_NODE_MAJOR_VERSION,
    SdkRuntimeBlocker,
    SdkRuntimeCapability,
    SdkRuntimeCapabilityEvidence,
    SdkRuntimeCapabilitySource,
    SdkRuntimeCapabilityStatus,
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
            capabilities=_full_contract_capabilities(),
        )
    )

    result = PreflightSdkRuntime(probe).execute(SdkRuntimePreflightRequest())

    assert result.status is SdkRuntimePreflightStatus.READY
    assert result.ready
    assert result.node_executable == "/opt/homebrew/bin/node"
    assert result.node_version == "v22.11.0"
    assert result.sdk_package_name == DEFAULT_SDK_PACKAGE_NAME
    assert result.capabilities == _full_contract_capabilities()
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
            capabilities=_full_contract_capabilities(),
            blockers=(blocker,),
        )
    )

    result = PreflightSdkRuntime(probe).execute(SdkRuntimePreflightRequest())

    assert result.status is SdkRuntimePreflightStatus.FAILED
    assert not result.ready
    assert result.blockers[0].code == expected_code


def test_preflight_fails_closed_when_full_contract_capability_evidence_is_missing() -> None:
    capabilities = tuple(
        evidence
        for evidence in _full_contract_capabilities()
        if evidence.capability is not SdkRuntimeCapability.PLAN_ACT_OBSERVATION
    )
    probe = RecordingSdkRuntimeProbe(
        SdkRuntimeObservation(
            node_executable="/opt/homebrew/bin/node",
            node_version="v22.11.0",
            sdk_resolved=True,
            capabilities=capabilities,
        )
    )

    result = PreflightSdkRuntime(probe).execute(SdkRuntimePreflightRequest())

    assert result.status is SdkRuntimePreflightStatus.FAILED
    assert not result.ready
    assert result.blockers[-1].code == "sdk_capability_missing_plan_act_observation"


def test_preflight_fails_closed_when_plan_act_permission_or_approval_is_unproven() -> None:
    capabilities = tuple(
        SdkRuntimeCapabilityEvidence(
            capability=evidence.capability,
            status=SdkRuntimeCapabilityStatus.UNPROVEN,
            source=SdkRuntimeCapabilitySource.OFFICIAL_DOCS,
            summary="not proven by official references and local smoke evidence",
        )
        if evidence.capability
        in {
            SdkRuntimeCapability.PERMISSION_APPROVAL,
            SdkRuntimeCapability.PLAN_ACT_OBSERVATION,
            SdkRuntimeCapability.ACT_AUTHORIZATION,
        }
        else evidence
        for evidence in _full_contract_capabilities()
    )
    probe = RecordingSdkRuntimeProbe(
        SdkRuntimeObservation(
            node_executable="/opt/homebrew/bin/node",
            node_version="v22.11.0",
            sdk_resolved=True,
            capabilities=capabilities,
        )
    )

    result = PreflightSdkRuntime(probe).execute(SdkRuntimePreflightRequest())

    assert result.status is SdkRuntimePreflightStatus.FAILED
    assert {blocker.code for blocker in result.blockers if blocker.code.startswith("sdk_capability_unproven_")} == {
        "sdk_capability_unproven_permission_approval",
        "sdk_capability_unproven_plan_act_observation",
        "sdk_capability_unproven_act_authorization",
    }


def test_preflight_does_not_accept_agent_proof_as_clinecore_or_permission_proof() -> None:
    capabilities = tuple(
        evidence
        for evidence in _full_contract_capabilities()
        if evidence.capability
        not in {
            SdkRuntimeCapability.CLINECORE_SESSION,
            SdkRuntimeCapability.TOOL_POLICY_COVERAGE,
            SdkRuntimeCapability.PERMISSION_APPROVAL,
        }
    )
    probe = RecordingSdkRuntimeProbe(
        SdkRuntimeObservation(
            node_executable="/opt/homebrew/bin/node",
            node_version="v22.11.0",
            sdk_resolved=True,
            capabilities=capabilities,
        )
    )

    result = PreflightSdkRuntime(probe).execute(SdkRuntimePreflightRequest())

    assert result.status is SdkRuntimePreflightStatus.FAILED
    assert {
        "sdk_capability_missing_clinecore_session",
        "sdk_capability_missing_tool_policy_coverage",
        "sdk_capability_missing_permission_approval",
    }.issubset({blocker.code for blocker in result.blockers})


def test_preflight_rejects_cli_probe_as_sdk_readiness_evidence() -> None:
    capabilities = tuple(
        SdkRuntimeCapabilityEvidence(
            capability=evidence.capability,
            status=SdkRuntimeCapabilityStatus.PROVEN,
            source=SdkRuntimeCapabilitySource.CLI_PROBE,
            summary="terminal probe observed this behavior",
        )
        if evidence.capability is SdkRuntimeCapability.PLAN_ACT_OBSERVATION
        else evidence
        for evidence in _full_contract_capabilities()
    )
    probe = RecordingSdkRuntimeProbe(
        SdkRuntimeObservation(
            node_executable="/opt/homebrew/bin/node",
            node_version="v22.11.0",
            sdk_resolved=True,
            capabilities=capabilities,
        )
    )

    result = PreflightSdkRuntime(probe).execute(SdkRuntimePreflightRequest())

    assert result.status is SdkRuntimePreflightStatus.FAILED
    assert result.blockers[-1].code == "sdk_capability_cli_probe_plan_act_observation"


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


def _full_contract_capabilities() -> tuple[SdkRuntimeCapabilityEvidence, ...]:
    return tuple(
        SdkRuntimeCapabilityEvidence(
            capability=capability,
            status=SdkRuntimeCapabilityStatus.PROVEN,
            source=SdkRuntimeCapabilitySource.ADAPTER_CONTRACT,
            summary=f"{capability.value} is proven for the full SDK execution contract",
        )
        for capability in SdkRuntimeCapability
    )
