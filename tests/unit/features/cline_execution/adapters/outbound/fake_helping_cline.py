"""Fake Cline executable for capability-probe adapter tests."""

import sys


def main() -> int:
    """Emit deterministic help and version output for probe tests."""
    if "--version" in sys.argv:
        sys.stdout.write("3.0.46\n")
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


if __name__ == "__main__":
    raise SystemExit(main())
