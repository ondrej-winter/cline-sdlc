"""Process-signal adapter for cooperative orchestration interruption."""

from __future__ import annotations

import signal
from contextlib import AbstractContextManager
from threading import Event
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from signal import _HANDLER
    from types import TracebackType


class SignalInterruption(AbstractContextManager["SignalInterruption"]):
    """Translate SIGINT and SIGTERM into a reusable cooperative stop token."""

    def __init__(self) -> None:
        self._event = Event()
        self._previous: dict[signal.Signals, _HANDLER] = {}

    def is_set(self) -> bool:
        """Return whether a handled process signal requested shutdown."""
        return self._event.is_set()

    def __enter__(self) -> Self:
        for handled_signal in (signal.SIGINT, signal.SIGTERM):
            self._previous[handled_signal] = signal.getsignal(handled_signal)
            signal.signal(handled_signal, self._handle)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for handled_signal, previous_handler in self._previous.items():
            signal.signal(handled_signal, previous_handler)
        self._previous.clear()

    def _handle(self, _signum: int, _frame: object) -> None:
        self._event.set()
