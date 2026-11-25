"""Tempo eines Samples schätzen (C5).

Reihenfolge der Quellen:
1. BPM-Angabe im Dateinamen ("…_120bpm…", "128 BPM")
2. Loop-Länge: Loops sind meist ganze Takte → BPM = Takte × 4 × 60 / Dauer
3. Onset-Autokorrelation als Plausibilisierung bzw. für Nicht-Loops

Halbes/doppeltes Tempo ist typisch falsch erkannt; die UI bietet ×2/÷2 an (Discovery J4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from ..core.models import SR

_BPM_IN_NAME = re.compile(r"(?<![\d.])(\d{2,3}(?:[.,]\d+)?)\s*[-_ ]?\s*bpm", re.IGNORECASE)


@dataclass
class TempoEstimate:
    bpm: float
    bars: int | None          # bei Loops: Anzahl Takte, sonst None
    source: str               # "filename" | "loop" | "onset" | "default"
    onset_bpm: float | None = None
    candidates: list[tuple[float, int]] = field(default_factory=list)


def bpm_from_filename(name: str) -> float | None:
    m = _BPM_IN_NAME.search(name)
    if not m:
        return None
    bpm = float(m[1].replace(",", "."))
    return bpm if 40 <= bpm <= 300 else None


def loop_candidates(frames: int, lo: float = 70, hi: float = 180, max_bars: int = 32) -> list[tuple[float, int]]:
    """Alle (BPM, Takte) im Bereich lo–hi, unter der Annahme ganzer 4/4-Takte."""
    dur = frames / SR
    out = []
    for bars in range(1, max_bars + 1):
        bpm = bars * 4 * 60 / dur
        if lo <= bpm <= hi:
            out.append((bpm, bars))
    return out


def onset_bpm(x: np.ndarray, lo: float = 60, hi: float = 200) -> float | None:
    """Tempo per Autokorrelation der Onset-Kurve (Energie-Zuwachs pro 512er-Block)."""
    mono = np.asarray(x, dtype=np.float64)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    hop = 512
    n = len(mono) // hop
    if n < 32:
        return None
    rms = np.sqrt((mono[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)
    env = np.log1p(1000 * rms)
    nov = np.maximum(np.diff(env), 0)
    nov -= nov.mean()
    if not np.any(nov):
        return None
    m = 1 << int(np.ceil(np.log2(2 * len(nov))))
    ac = np.fft.irfft(np.abs(np.fft.rfft(nov, m)) ** 2, m)[: len(nov)]
    fps = SR / hop
    lag_min = int(np.floor(60 * fps / hi))
    lag_max = min(int(np.ceil(60 * fps / lo)), len(ac) - 2)
    if lag_max <= lag_min + 1:
        return None
    lags = np.arange(lag_min, lag_max + 1)
    bpms = 60 * fps / lags
    prior = np.exp(-0.5 * (np.log2(bpms / 120) / 0.9) ** 2)  # leichte Vorliebe für ~120 BPM
    score = ac[lags] * prior
    i = int(np.argmax(score))
    lag = float(lags[i])
    if 0 < i < len(lags) - 1:  # parabolische Verfeinerung
        a, b, c = score[i - 1], score[i], score[i + 1]
        den = a - 2 * b + c
        if den != 0:
            lag += 0.5 * (a - c) / den
    return 60 * fps / lag


def _rel_err(a: float, b: float) -> float:
    return min(abs(a - b * k) / a for k in (0.5, 1.0, 2.0))


def estimate_tempo(x: np.ndarray, filename: str | None = None, is_loop: bool = True) -> TempoEstimate:
    frames = len(x)
    cands = loop_candidates(frames) if is_loop else []
    onset = onset_bpm(x)

    if filename and (fb := bpm_from_filename(filename)):
        bars = None
        if is_loop:
            exact = [(b, n) for b, n in loop_candidates(frames, 40, 300) if abs(b - fb) / fb < 0.01]
            bars = exact[0][1] if exact else None
        return TempoEstimate(fb, bars, "filename", onset, cands)

    if cands:
        if onset:
            best = min(cands, key=lambda c: _rel_err(c[0], onset))
            if _rel_err(best[0], onset) < 0.04:
                return TempoEstimate(best[0], best[1], "loop", onset, cands)
        best = min(cands, key=lambda c: abs(np.log2(c[0] / 120)))
        return TempoEstimate(best[0], best[1], "loop", onset, cands)

    if onset:
        return TempoEstimate(onset, None, "onset", onset, cands)
    return TempoEstimate(120.0, None, "default", None, cands)
