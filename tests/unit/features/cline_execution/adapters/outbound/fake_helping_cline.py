"""Fake Cline executable for capability-probe adapter tests."""

import sys


def main() -> int:
    """Emit deterministic help and version output for probe tests."""
    if "--version" in sys.argv:
        sys.stdout.write("3.0.46\n")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
