"""Tests for the supervised real-Cline proof command wrapper."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import TYPE_CHECKING

from cline_sdlc.features.cline_execution.domain.capability import CapabilityStatus

if TYPE_CHECKING:
    from types import ModuleType

    import pytest


def _load_module(path: Path) -> ModuleType:
    spec = spec_from_file_location("prove_real_cline_capability", path)
    if spec is None or spec.loader is None:
        msg = f"cannot load module from {path}"
        raise RuntimeError(msg)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROOF_MODULE = Path(__file__).parents[4] / "manual" / "cline_execution" / "prove_real_cline_capability.py"
proof_module = _load_module(PROOF_MODULE)


def test_supervised_proof_uses_explicit_paths_and_reports_proven_fake_contracts(tmp_path: Path) -> None:
    fake_cline = Path(__file__).parents[1] / "adapters" / "outbound" / "cli_capability_probe" / "fake_helping_cline.py"
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    report = proof_module.run_supervised_proof(
        _parse_args(
            tmp_path,
            command=(sys.executable, str(fake_cline)),
            repository_root=repository_root,
            required_skills=("idea-refine",),
        )
    )

    statuses = {observation.name: observation.status for observation in report.observations}
    assert report.executable == f"{sys.executable} {fake_cline}"
    assert statuses["required_skill:idea-refine"] is CapabilityStatus.PROVEN
    assert statuses["supervised_session_writes_status_sidecar"] is CapabilityStatus.PROVEN
    assert report.critical_capabilities_proven


def test_report_json_includes_blocking_observations_for_failed_fake_contracts(tmp_path: Path) -> None:
    fake_cline = Path(__file__).parents[1] / "adapters" / "outbound" / "cli_capability_probe" / "fake_helping_cline.py"
    arguments = _parse_args(
        tmp_path,
        command=(sys.executable, str(fake_cline), "--fake-session-scenario", "missing-sidecar"),
        required_skills=("missing-skill",),
    )

    payload = json.loads(proof_module.report_to_json(proof_module.run_supervised_proof(arguments)))

    blocking_names = {observation["name"] for observation in payload["blocking_observations"]}
    assert payload["critical_capabilities_proven"] is False
    assert "required_skill:missing-skill" in blocking_names


def test_main_returns_non_zero_when_required_skill_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_cline = Path(__file__).parents[1] / "adapters" / "outbound" / "cli_capability_probe" / "fake_helping_cline.py"

    exit_code = proof_module.main(
        [
            "--cline-command",
            sys.executable,
            str(fake_cline),
            "--fake-session-scenario",
            "missing-sidecar",
            "--repository-root",
            str(tmp_path / "repo"),
            "--data-directory",
            str(tmp_path / "data"),
            "--hooks-directory",
            str(tmp_path / "hooks"),
            "--required-skill",
            "missing-skill",
        ]
    )

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["critical_capabilities_proven"] is False


def _parse_args(
    tmp_path: Path,
    *,
    command: tuple[str, ...],
    repository_root: Path | None = None,
    required_skills: tuple[str, ...] = (),
) -> Namespace:
    return Namespace(
        cline_command=command,
        repository_root=repository_root or (tmp_path / "repo"),
        data_directory=tmp_path / "data",
        hooks_directory=tmp_path / "hooks",
        required_skills=list(required_skills),
        session_timeout_seconds=1.0,
        probe_prompt="fake proof prompt",
    )
