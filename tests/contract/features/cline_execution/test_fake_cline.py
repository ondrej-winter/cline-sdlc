"""Contract tests for the deterministic fake-Cline executable."""

import json
import signal
import subprocess
from typing import TYPE_CHECKING, cast

import pytest

from tests.contract.features.cline_execution.conftest import FakeClineFactory, FakeClineRequest

if TYPE_CHECKING:
    from pathlib import Path

DUPLICATE_OUTCOME_COUNT = 2
NONZERO_EXIT_CODE = 23


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, check=False, text=True)  # noqa: S603


def _json_lines(stdout: str) -> list[dict[str, object]]:
    return [cast("dict[str, object]", json.loads(line)) for line in stdout.splitlines()]


def test_valid_scenario_emits_one_terminal_outcome(fake_cline: FakeClineFactory) -> None:
    result = _run(fake_cline(FakeClineRequest(scenario="valid")))

    assert result.returncode == 0
    assert result.stderr == ""
    outcomes = _json_lines(result.stdout)
    assert len(outcomes) == 1
    assert outcomes[0]["schema_version"] == 1
    assert outcomes[0]["status"] == "completed"


@pytest.mark.parametrize(
    ("scenario", "expected_stdout"),
    [("missing", ""), ("malformed", "{not-json}\n")],
)
def test_invalid_stream_scenarios_are_explicit(
    fake_cline: FakeClineFactory,
    scenario: str,
    expected_stdout: str,
) -> None:
    result = _run(fake_cline(FakeClineRequest(scenario=scenario)))

    assert result.returncode == 0
    assert result.stdout == expected_stdout


def test_duplicate_scenario_emits_two_terminal_outcomes(fake_cline: FakeClineFactory) -> None:
    result = _run(fake_cline(FakeClineRequest(scenario="duplicate")))

    outcomes = _json_lines(result.stdout)
    assert len(outcomes) == DUPLICATE_OUTCOME_COUNT
    assert outcomes[0] == outcomes[1]


def test_controlled_write_can_match_reported_changed_paths(
    fake_cline: FakeClineFactory,
    tmp_path: Path,
) -> None:
    changed_path = "src/generated.txt"
    result = _run(
        fake_cline(
            FakeClineRequest(
                scenario="valid",
                repository_root=tmp_path,
                write_paths=(changed_path,),
                reported_changed_paths=(changed_path,),
                write_content="controlled content\n",
            )
        )
    )

    assert (tmp_path / changed_path).read_text(encoding="utf-8") == "controlled content\n"
    assert _json_lines(result.stdout)[0]["changed_paths"] == [changed_path]


def test_conflicting_scenario_reports_a_path_that_was_not_written(
    fake_cline: FakeClineFactory,
    tmp_path: Path,
) -> None:
    written_path = "src/actual.txt"
    result = _run(
        fake_cline(FakeClineRequest(scenario="conflicting", repository_root=tmp_path, write_paths=(written_path,)))
    )

    assert (tmp_path / written_path).is_file()
    assert _json_lines(result.stdout)[0]["changed_paths"] == ["unexpected/conflicting-path.txt"]


def test_approval_required_scenario_has_a_specific_operation(fake_cline: FakeClineFactory) -> None:
    result = _run(fake_cline(FakeClineRequest(scenario="approval-required")))

    outcome = _json_lines(result.stdout)[0]
    assert outcome["status"] == "approval_required"
    blocker = cast("dict[str, object]", outcome["blocker"])
    assert blocker["proposed_operation"] == ["curl", "https://example.invalid"]


def test_delayed_scenario_can_be_timed_out(fake_cline: FakeClineFactory) -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(  # noqa: S603
            fake_cline(FakeClineRequest(scenario="delayed", delay_seconds=10.0)),
            capture_output=True,
            check=False,
            text=True,
            timeout=0.1,
        )


@pytest.mark.skipif(not hasattr(signal, "SIGTERM"), reason="SIGTERM is required")
def test_interrupted_scenario_terminates_by_signal(fake_cline: FakeClineFactory) -> None:
    result = _run(fake_cline(FakeClineRequest(scenario="interrupted")))

    assert result.returncode == -signal.SIGTERM
    assert result.stdout == ""


def test_explicit_nonzero_exit_is_observable(fake_cline: FakeClineFactory) -> None:
    result = _run(fake_cline(FakeClineRequest(scenario="valid", exit_code=NONZERO_EXIT_CODE)))

    assert result.returncode == NONZERO_EXIT_CODE
    assert len(_json_lines(result.stdout)) == 1


def test_fixture_returns_an_argument_array(fake_cline: FakeClineFactory) -> None:
    arguments = fake_cline(FakeClineRequest(scenario="valid"))

    assert isinstance(arguments, list)
    assert all(isinstance(argument, str) for argument in arguments)
    assert "--scenario" in arguments
