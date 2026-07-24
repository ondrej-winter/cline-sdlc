"""Console entry point wiring for the Cline SDLC application."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from cline_sdlc.features.lifecycle_orchestration.adapters.inbound.cli import run_cli_invocation

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """Run one supervised lifecycle CLI invocation and return its process exit code."""
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    result = run_cli_invocation(sys.argv[1:] if argv is None else argv)

    output_stream.write(result.stdout)
    error_stream.write(result.stderr)

    return result.exit_code
