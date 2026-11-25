"""Latenz-Kalibrierung (C12): Click droppen, Aufnahme im Storage-Modus zurücklesen, Versatz messen.

Gemessen wird pro Schlag (Schlag 1 wird übersprungen, weil er bei zu frühem Audio am Loop-Anfang
abgeschnitten wird). Eine Korrelation über den ganzen Loop lag in S1 zweimal um ganze Schläge daneben.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.models import SR, loop_frames


def make_click(bpm: float, bars: int = 1) -> np.ndarray:
    """Click mit lautem Schlag 1 und leiseren Schlägen 2–4, exakt in Gerätelänge."""
    n = loop_frames(bpm, bars)
    x = np.zeros((n, 2), np.float32)
    burst = (np.sin(2 * np.pi * 1000 * np.arange(441) / SR) * np.hanning(441)).astype(np.float32)
    beat = 60 / bpm * SR
    for i in range(bars * 4):
        s = int(round(i * beat))
        x[s:s + 441] += ((0.9 if i % 4 == 0 else 0.4) * burst)[: n - s, None]
    return x


@dataclass(frozen=True)
class Measurement:
    per_beat_frames: list[int]
    offset_ms: float           # + = Aufnahme kommt zu spät
    spread_ms: float
    length_delta: int          # Frames Aufnahme − Referenz

    def suggested_offset(self, current_offset_ms: float) -> float:
        """Neuer `offset_ms`: kommt die Aufnahme zu spät, muss das Audio früher starten."""
        return round(current_offset_ms - self.offset_ms, 2)


def measure(ref: np.ndarray, rec: np.ndarray, bpm: float) -> Measurement:
    r = np.asarray(ref, np.float64).mean(axis=1) if np.ndim(ref) == 2 else np.asarray(ref, np.float64)
    x = np.asarray(rec, np.float64).mean(axis=1) if np.ndim(rec) == 2 else np.asarray(rec, np.float64)
    beat = 60.0 / bpm * SR
    half = int(beat / 2)
    lags = []
    for k in range(1, int(round(len(r) / beat))):
        c = int(round(k * beat))
        lo, hi = c - half, c + half
        if lo < 0 or hi > len(r) or hi > len(x):
            continue
        a, b = r[lo:hi], x[lo:hi]
        if not np.any(b):
            continue
        n = 1 << int(np.ceil(np.log2(2 * len(a))))
        cc = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
        lag = int(np.argmax(cc))
        if lag > n // 2:
            lag -= n
        if abs(lag) < half:
            lags.append(lag)
    if not lags:
        raise ValueError("Keine Schläge auswertbar – passt die Aufnahme zum Click (Tempo, Spur)?")
    med = float(np.median(lags))
    return Measurement(lags, med / SR * 1000, (max(lags) - min(lags)) / SR * 1000, len(x) - len(r))
