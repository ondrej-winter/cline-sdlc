"""Deterministic test double for the external Cline command."""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1


def _repository_path(repository_root: Path, relative_path: str) -> Path:
    normalized = PurePosixPath(relative_path)
    if normalized.is_absolute() or ".." in normalized.parts:
        msg = f"unsafe repository-relative path: {relative_path}"
        raise argparse.ArgumentTypeError(msg)
    return repository_root.joinpath(*normalized.parts)


def _write_files(repository_root: Path, write_paths: list[str], content: str) -> None:
    for relative_path in write_paths:
        destination = _repository_path(repository_root, relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


def _outcome(status: str, changed_paths: list[str]) -> dict[str, object]:
    blocker: dict[str, object] | None = None
    reason = "fixture_completed"
    if status == "approval_required":
        reason = "operation_requires_approval"
        blocker = {
            "code": "approval_required",
            "summary": "The fixture requested a prohibited operation.",
            "proposed_operation": ["curl", "https://example.invalid"],
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "session_role": "implementation",
        "status": status,
        "reason": reason,
        "artifact_paths": [],
        "changed_paths": changed_paths,
        "validation": [],
        "findings": [],
        "finding_ids": [],
        "risk": None,
        "blocker": blocker,
        "retryable": False,
    }


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        required=True,
        choices=(
            "valid",
            "missing",
            "malformed",
            "duplicate",
            "conflicting",
            "approval-required",
            "delayed",
            "interrupted",
        ),
    )
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--write-path", action="append", default=[])
    parser.add_argument("--reported-changed-path", action="append", default=[])
    parser.add_argument("--write-content", default="fake Cline write\n")
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--exit-code", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    """Execute the explicitly selected fake-Cline scenario."""
    arguments = _parse_arguments()
    repository_root: Path = arguments.repository_root
    write_paths: list[str] = arguments.write_path
    reported_paths: list[str] = arguments.reported_changed_path or write_paths
    scenario: str = arguments.scenario
    exit_code: int = arguments.exit_code

    _write_files(repository_root, write_paths, arguments.write_content)

    if scenario == "delayed":
        time.sleep(arguments.delay_seconds)
    elif scenario == "interrupted":
        os.kill(os.getpid(), signal.SIGTERM)
    elif scenario == "missing":
        return exit_code
    elif scenario == "malformed":
        sys.stdout.write("{not-json}\n")
        return exit_code

    if scenario == "conflicting" and not arguments.reported_changed_path:
        reported_paths = ["unexpected/conflicting-path.txt"]

    status = "approval_required" if scenario == "approval-required" else "completed"
    serialized = json.dumps(_outcome(status, reported_paths), sort_keys=True)
    sys.stdout.write(f"{serialized}\n")
    if scenario == "duplicate":
        sys.stdout.write(f"{serialized}\n")
    sys.stdout.flush()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
