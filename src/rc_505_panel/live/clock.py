"""MIDI-Clock der RC-505mkII mitlesen und Taktanfänge vorhersagen (C9).

Spike S1 hat gezeigt: Den Zeitpunkt eines künftigen Ticks aus *einem* Tick hochzurechnen
streut um ±5 ms; eine Ausgleichsgerade über die letzten Ticks drückt das auf ±1 ms.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

PPQN = 24
TICKS_PER_BAR = PPQN * 4  # 4/4


@dataclass(frozen=True)
class TickEstimate:
    time: float          # perf_counter-Zeit des Ticks
    jitter_ms: float     # Std der Ankunftszeiten um die Gerade


class ClockFollower:
    """Zählt Ticks seit START. Thread-sicher; `feed` wird vom MIDI-Thread aufgerufen."""

    def __init__(self, now: Callable[[], float] = time.perf_counter, history_bars: int = 4) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._max_hist = history_bars * TICKS_PER_BAR
        self.running = False
        self.tick = -1                  # -1 = noch kein Tick seit START
        self.starts = 0                 # Anzahl START-Meldungen (Erkennung von Neustarts)
        self.stops = 0
        self.orphan_ticks = 0           # Ticks ohne gesehenes START → Position unbekannt
        self._hist: list[tuple[int, float]] = []

    # ---------- Eingang ----------

    def feed(self, msg_type: str, t: float | None = None) -> None:
        t = self._now() if t is None else t
        with self._lock:
            if msg_type == "start":
                self.running, self.tick, self._hist = True, -1, []
                self.starts += 1
            elif msg_type == "stop":
                self.running = False
                self.stops += 1
            elif msg_type == "continue":
                # Position nach CONTINUE ist ohne Song Position Pointer unbekannt
                self.running = False
            elif msg_type == "clock":
                if not self.running:
                    self.orphan_ticks += 1
                    return
                self.tick += 1          # erster Tick nach START = Tick 0 = Schlag 1
                self._hist.append((self.tick, t))
                if len(self._hist) > self._max_hist:
                    del self._hist[: len(self._hist) - self._max_hist]

    # ---------- Abfragen ----------

    @property
    def ready(self) -> bool:
        """Genug Ticks für eine stabile Schätzung (mind. ein Schlag)."""
        with self._lock:
            return self.running and len(self._hist) > PPQN

    def _fit(self) -> tuple[float, float, float] | None:
        with self._lock:
            h = list(self._hist)
        if len(h) <= PPQN:
            return None
        k = np.array([x[0] for x in h], dtype=float)
        t = np.array([x[1] for x in h])
        k0, t0 = k[0], t[0]
        slope, icpt = np.polyfit(k - k0, t - t0, 1)
        resid = (t - t0) - (slope * (k - k0) + icpt)
        return float(slope), float(t0 + icpt - slope * k0), float(resid.std() * 1000)

    @property
    def bpm(self) -> float | None:
        f = self._fit()
        return 60.0 / (f[0] * PPQN) if f else None

    def time_of_tick(self, k: int) -> TickEstimate | None:
        f = self._fit()
        if not f:
            return None
        slope, offset, jitter = f
        return TickEstimate(offset + slope * k, jitter)

    def next_bar_tick(self, min_lead_s: float = 0.0) -> int | None:
        """Tick-Nummer des nächsten Taktanfangs, der mindestens `min_lead_s` in der Zukunft liegt."""
        if not self.ready:
            return None
        with self._lock:
            cur = self.tick
        k = (cur // TICKS_PER_BAR + 1) * TICKS_PER_BAR
        while True:
            est = self.time_of_tick(k)
            if est is None:
                return None
            if est.time - self._now() >= min_lead_s:
                return k
            k += TICKS_PER_BAR
