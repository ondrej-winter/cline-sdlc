"""Fake Cline executable for capability-probe adapter tests."""

import json
import sys
import time


def main() -> int:
    """Emit deterministic help and version output for probe tests."""
    if "--version" in sys.argv:
        sys.stdout.write("3.0.46\n")
        return 0
    if "--json" in sys.argv:
        _run_session_scenario(_argument_after("--fake-session-scenario") or "valid-session")
        return 0
    if sys.argv[-2:] == ["skill", "list"]:
        sys.stdout.write("idea-refine\nspec-driven-development\n")
        return 0
    if "--help" in sys.argv:
        sys.stdout.write(
            "Usage: cline [options] [command] [prompt]\n"
            "  --json\n"
            "  --timeout <seconds>\n"
            "  --data-dir <path>\n"
            "  --hooks-dir <path>\n"
            "  --cwd <path>\n"
            "Commands:\n"
            "  skill [args...]\n"
        )
        return 0
    if sys.argv[-2:] == ["skill", "fail"]:
        sys.stderr.write("skill command failed\n")
        return 1
    return 0


def _run_session_scenario(scenario: str) -> None:
    if scenario == "missing-outcome":
        return
    if scenario == "malformed-outcome":
        sys.stdout.write("{not-json}\n")
        return
    if scenario == "duplicate-outcome":
        _write_outcome()
        _write_outcome()
        return
    if scenario == "timeout":
        time.sleep(10.0)
        return
    _write_outcome()


def _argument_after(flag: str) -> str | None:
    try:
        return sys.argv[sys.argv.index(flag) + 1]
    except ValueError, IndexError:
        return None


def _write_outcome() -> None:
    sys.stdout.write(
        json.dumps(
            {
                "schema_version": 1,
                "status": "completed",
                "changed_paths": [],
                "permission_mediation": True,
                "interruption_recovery": True,
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
