"""Private subprocess helpers for the Cline CLI capability probe adapter."""

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_PROBE_TIMEOUT_SECONDS = 10.0


def run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run a bounded CLI probe command and normalize launch/timeout failures."""
    try:
        return subprocess.run(  # noqa: S603
            list(arguments),
            capture_output=True,
            check=False,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except OSError as err:
        return subprocess.CompletedProcess(args=list(arguments), returncode=127, stdout="", stderr=str(err))
    except subprocess.TimeoutExpired as err:
        return subprocess.CompletedProcess(
            args=list(arguments),
            returncode=124,
            stdout=_timeout_text(err.stdout),
            stderr=_timeout_text(err.stderr),
        )


def run_with_timeout(arguments: Sequence[str], timeout_seconds: float) -> subprocess.CompletedProcess[str] | None:
    """Run a probe command with a caller-supplied timeout, or return None on failure."""
    try:
        return subprocess.run(  # noqa: S603
            list(arguments),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except OSError, subprocess.TimeoutExpired:
        return None


def first_non_empty_line(text: str) -> str | None:
    """Return the first non-empty line from text."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
