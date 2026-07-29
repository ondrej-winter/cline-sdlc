"""Fake Cline executable for capability-probe adapter tests."""

import json
import sys
import time
from pathlib import Path


def main() -> int:
    """Emit deterministic help and version output for probe tests."""
    if "--version" in sys.argv:
        sys.stdout.write("3.0.46\n")
        return 0
    if "--json" in sys.argv:
        _run_session_scenario(_argument_after("--fake-session-scenario") or "valid-session")
        return 0
    if sys.argv[-2:] == ["skill", "list"]:
        sys.stdout.write(
            "\x1b[1mProject Skills\x1b[0m\n\n"
            "\x1b[36midea-refine                               \x1b[0m /repo/.agents/skills/idea-refine\n"
            "  \x1b[38;5;102mAgents:\x1b[0m Cline, Codex, GitHub Copilot  Source: local\n"
            "\x1b[36mspec-driven-development                   \x1b[0m /repo/.agents/skills/spec-driven-development\n"
            "  \x1b[38;5;102mAgents:\x1b[0m Cline, Codex, GitHub Copilot  Source: local\n"
        )
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
    if scenario == "missing-sidecar":
        return
    if scenario == "malformed-sidecar":
        _write_sidecar("{not-json}")
        return
    if scenario == "missing-interruption-recovery":
        _write_sidecar(json.dumps({"schema_version": 1, "status": "ok"}))
        return
    if scenario == "timeout":
        time.sleep(10.0)
        return
    _write_sidecar(json.dumps(_sidecar_payload()))


def _argument_after(flag: str) -> str | None:
    try:
        return sys.argv[sys.argv.index(flag) + 1]
    except ValueError, IndexError:
        return None


def _write_sidecar(content: str) -> None:
    sidecar_path = _sidecar_path_from_prompt()
    if sidecar_path is None:
        return
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(content, encoding="utf-8")


def _sidecar_path_from_prompt() -> Path | None:
    if not sys.argv:
        return None
    lines = sys.argv[-1].splitlines()
    for index, line in enumerate(lines):
        if line == "Before exiting, write a UTF-8 JSON status sidecar file at this exact path:":
            try:
                return Path(lines[index + 1])
            except IndexError:
                return None
    return None


def _sidecar_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ok",
        "interruption_recovery": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
