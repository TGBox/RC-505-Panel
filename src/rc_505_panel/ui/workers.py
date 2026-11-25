"""Hintergrundarbeit (Rendern, Import, Messen) ohne den UI-Thread zu blockieren (AC7)."""
from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:  # läuft im Thread-Pool
        try:
            res = self.fn()
        except Exception as e:  # noqa: BLE001 – Fehler gehen an die UI
            traceback.print_exc()
            self.signals.failed.emit(f"{type(e).__name__}: {e}")
        else:
            self.signals.done.emit(res)


_active: set[_Job] = set()   # Referenzen halten, bis die Signale zugestellt sind


def run_in_background(fn: Callable[[], Any], on_done: Callable[[Any], None],
                      on_failed: Callable[[str], None]) -> None:
    job = _Job(fn)
    job.setAutoDelete(False)
    _active.add(job)

    def _finish(handler, value):
        _active.discard(job)
        handler(value)

    job.signals.done.connect(lambda v: _finish(on_done, v))
    job.signals.failed.connect(lambda m: _finish(on_failed, m))
    QThreadPool.globalInstance().start(job)
