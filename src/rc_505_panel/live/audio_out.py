"""Audio-Ausgabe zur RC-505mkII mit zeitgenauem Start (C10).

Der Stream bleibt offen; `play_at` setzt einen Clip, der exakt zur angegebenen perf_counter-Zeit
am Ausgang anliegen soll. Die Umrechnung PC-Uhr ↔ Audio-Uhr wird im Hauptthread gemessen
(schnellste von N Lesungen) – im Callback gemessen streute sie in S1 um mehrere ms.
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

import numpy as np

from ..core.models import SR

DEFAULT_DEVICE = "RC-505mk2 INST2 WASAPI"   # ADR-0006: Drop-Kanal INST2


class AudioError(RuntimeError):
    pass


def resolve_output_device(query: str | int | None) -> int | None:
    """Index oder Suchwörter (Reihenfolge, Groß-/Kleinschreibung egal) → eindeutiger Ausgabe-Index."""
    import sounddevice as sd
    if query is None or isinstance(query, int):
        return query
    if str(query).isdigit():
        return int(query)
    words = str(query).lower().split()
    hits = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] <= 0:
            continue
        full = f"{d['name']}, {sd.query_hostapis(d['hostapi'])['name']}"
        if all(w in full.lower() for w in words):
            hits.append((i, full))
    if len(hits) != 1:
        found = "; ".join(f"[{i}] {n}" for i, n in hits) or "keins"
        raise AudioError(f"Ausgabegerät „{query}“ nicht eindeutig: {found}")
    return hits[0][0]


@dataclass
class _Pending:
    clip: np.ndarray
    at: float                 # perf_counter-Zeit, zu der Sample 0 am Ausgang anliegen soll
    pos: int | None = None    # nächster Clip-Index; None = noch nicht gestartet
    started_at: float | None = None
    done: threading.Event = None  # type: ignore[assignment]


class AudioOut:
    def __init__(self, device: str | int | None = DEFAULT_DEVICE, channel_offset: int = 0,
                 latency: str | float = "low") -> None:
        import sounddevice as sd
        self._sd = sd
        self.device = resolve_output_device(device)
        self.ch0 = channel_offset
        self._lock = threading.Lock()
        self._pending: _Pending | None = None
        self._delta: float | None = None
        self.status_errors = 0
        self._stream = sd.OutputStream(device=self.device, samplerate=SR, channels=channel_offset + 2,
                                       dtype="float32", latency=latency, callback=self._callback)
        self._stream.start()
        self.sync_clocks()

    @property
    def latency_ms(self) -> float:
        return float(self._stream.latency) * 1000

    def sync_clocks(self, reads: int = 40) -> float:
        """Misst perf_counter − Stream-Zeit; gibt die Streuung der besten Lesungen (ms) zurück."""
        pairs = []
        for _ in range(reads):
            t1 = time.perf_counter()
            st = self._stream.time
            t2 = time.perf_counter()
            pairs.append((t2 - t1, (t1 + t2) / 2 - st))
            time.sleep(0.001)
        pairs.sort()
        best = [d for _, d in pairs[: max(3, reads // 4)]]
        self._delta = sum(best) / len(best)
        return (max(best) - min(best)) * 1000

    def play_at(self, clip: np.ndarray, at: float) -> threading.Event:
        """Plant `clip` ((n, 2) float32) für perf_counter-Zeit `at`. Ersetzt einen laufenden Clip."""
        clip = np.ascontiguousarray(clip, dtype=np.float32)
        p = _Pending(clip, at, done=threading.Event())
        with self._lock:
            self._pending = p
        return p.done

    def retime(self, at: float) -> None:
        """Startzeit nachschärfen, solange der Clip noch nicht begonnen hat."""
        with self._lock:
            if self._pending and self._pending.pos is None:
                self._pending.at = at

    def cancel(self) -> None:
        with self._lock:
            if self._pending:
                self._pending.done.set()
            self._pending = None

    def _callback(self, outdata, frames, tinfo, status) -> None:
        if status:
            self.status_errors += 1
        outdata.fill(0)
        with self._lock:
            p = self._pending
        if p is None or self._delta is None:
            return
        dac = tinfo.outputBufferDacTime + self._delta
        if p.pos is None:
            start = round((p.at - dac) * SR)
            if start >= frames:
                return
            p.pos = -start
            p.started_at = dac + max(start, 0) / SR
        i = p.pos
        dst0, src0 = max(0, -i), max(0, i)
        n = min(frames - dst0, len(p.clip) - src0)
        if n > 0:
            outdata[dst0:dst0 + n, self.ch0:self.ch0 + 2] = p.clip[src0:src0 + n]
        p.pos = i + frames
        if src0 + n >= len(p.clip):
            p.done.set()
            with self._lock:
                if self._pending is p:
                    self._pending = None

    def close(self) -> None:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception as e:  # pragma: no cover
            print("Audio-Stream schließen:", e, file=sys.stderr)

    def __enter__(self) -> "AudioOut":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
