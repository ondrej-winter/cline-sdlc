"""Tests for cooperative process-signal interruption."""

from __future__ import annotations

import os
import signal

import pytest

from cline_sdlc.bootstrap.signals import SignalInterruption


@pytest.mark.skipif(not hasattr(signal, "SIGTERM"), reason="SIGTERM is required")
def test_signal_interruption_records_sigterm_and_restores_handler() -> None:
    previous = signal.getsignal(signal.SIGTERM)

    with SignalInterruption() as interruption:
        os.kill(os.getpid(), signal.SIGTERM)
        assert interruption.is_set()

    assert signal.getsignal(signal.SIGTERM) is previous
