"""Time-Stretching und Rendern auf exakte Taktlänge (C6, ADR-0004).

Backends:
- "wsola":      eigene WSOLA-Implementierung, nur numpy (Standard, keine Abhängigkeit)
- "rubberband": Rubber-Band-CLI, falls `rubberband` im PATH liegt (bessere Qualität)
Welches Backend klingt gut genug, entscheidet ein Hörtest (offen laut ADR-0004).
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ..core.models import SR, AudioClip, frames_per_bar, loop_frames
from .convert import load_for_rc, write_float_wav
from .rcwav import read_rc_wav
from .tempo import TempoEstimate, estimate_tempo


# ---------- Stretch ----------

def wsola(x: np.ndarray, alpha: float, frame: int = 512, hop_out: int = 256, tol: int = 128) -> np.ndarray:
    """Waveform-Similarity-Overlap-Add. alpha = Ausgabelänge / Eingabelänge (Tonhöhe bleibt).

    Kleine Fenster (512/256, Suche ±128) halten Schläge auf ≤ ~3,5 ms genau an ihrer Taktposition
    (gemessen: 1024/512/±512 verschob Schläge um bis zu 11 ms). Klangqualität: Hörtest offen (ADR-0004).
    """
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        x = x[:, None]
    n_in, ch = x.shape
    n_out = int(round(n_in * alpha))
    if n_in < frame or n_out < frame:
        idx = np.clip(np.round(np.arange(n_out) / alpha).astype(int), 0, n_in - 1)
        return x[idx]
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(frame) / frame)).astype(np.float32)  # periodisches Hann
    pad = tol + frame
    xp = np.vstack([np.zeros((pad, ch), np.float32), x, np.zeros((pad + frame, ch), np.float32)])
    mono = xp.mean(axis=1)
    hop_in = hop_out / alpha
    n_frames = int(np.ceil(n_out / hop_out)) + 1
    y = np.zeros((n_frames * hop_out + frame, ch), np.float32)
    wsum = np.zeros(len(y), np.float32)
    delta = 0
    for k in range(n_frames):
        a = pad + int(round(k * hop_in)) + delta          # Analyseposition (gepolstert)
        a = min(max(a, 0), len(xp) - frame)
        o = k * hop_out
        y[o:o + frame] += xp[a:a + frame] * win[:, None]
        wsum[o:o + frame] += win
        # nächste Position so wählen, dass sie der natürlichen Fortsetzung am ähnlichsten ist
        nat_start = a + hop_out
        if nat_start + frame > len(mono):
            break
        nat = mono[nat_start:nat_start + frame]
        nxt = pad + int(round((k + 1) * hop_in))
        lo = max(nxt - tol, 0)
        hi = min(nxt + tol + frame, len(mono))
        seg = mono[lo:hi]
        if len(seg) < frame:
            delta = 0
            continue
        corr = np.correlate(seg, nat, mode="valid")
        delta = int(np.argmax(corr)) + lo - nxt
    y /= np.maximum(wsum, 1e-3)[:, None]
    # Startposition korrigieren: Frame 0 beginnt bei Eingabe-Sample 0 (pad abgezogen)
    return y[:n_out]


def rubberband_available() -> bool:
    return shutil.which("rubberband") is not None


def rubberband(x: np.ndarray, alpha: float) -> np.ndarray:
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "in.wav", Path(td) / "out.wav"
        write_float_wav(src, x)
        subprocess.run(["rubberband", "-q", "--fine", "-t", f"{alpha:.10f}", str(src), str(dst)],
                       check=True, capture_output=True)
        return read_rc_wav(dst)


def stretch(x: np.ndarray, alpha: float, backend: str = "auto") -> np.ndarray:
    """Zeitdehnung um Faktor alpha (= neue Länge / alte Länge)."""
    if abs(alpha - 1.0) < 1e-6:
        return np.asarray(x, dtype=np.float32)
    if backend == "auto":
        backend = "rubberband" if rubberband_available() else "wsola"
    if backend == "rubberband":
        return rubberband(x, alpha)
    if backend == "wsola":
        return wsola(x, alpha)
    raise ValueError(f"Unbekanntes Stretch-Backend: {backend}")


def limit_peak(x: np.ndarray, ceiling: float = 0.98) -> tuple[np.ndarray, float]:
    """Skaliert herunter, falls Samples über 1,0 liegen (das Gerät würde sie abschneiden).

    Gibt (Samples, angewendeter Faktor) zurück; Faktor 1.0 = unverändert.
    """
    peak = float(np.abs(x).max()) if len(x) else 0.0
    if peak <= 1.0:
        return x, 1.0
    gain = ceiling / peak
    return (x * gain).astype(np.float32), gain


def fit_length(x: np.ndarray, frames: int) -> np.ndarray:
    """Auf exakt `frames` kürzen bzw. mit Stille auffüllen."""
    if len(x) >= frames:
        return np.ascontiguousarray(x[:frames], dtype=np.float32)
    out = np.zeros((frames, x.shape[1]), np.float32)
    out[: len(x)] = x
    return out


# ---------- Rendern für ein Memory ----------

def render(x: np.ndarray, src_bpm: float, target_bpm: float, bars: int | None = None,
           backend: str = "auto") -> tuple[np.ndarray, int]:
    """Stretcht x von src_bpm auf target_bpm und schneidet auf exakt `bars` Takte (wie das Gerät).

    Ohne `bars` wird die Taktzahl aus der Quelllänge gerundet (mind. 1).
    Gibt (Samples, bars) zurück; len(Samples) == loop_frames(target_bpm, bars) (AC5).
    """
    if bars is None:
        bars = max(1, int(round(len(x) / frames_per_bar(src_bpm))))
    y = stretch(x, src_bpm / target_bpm, backend)
    y, _ = limit_peak(fit_length(y, loop_frames(target_bpm, bars)))
    return y, bars


def default_cache_dir() -> Path:
    import os
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / "rc-505-panel" / "render-cache"


def render_file(src: Path, target_bpm: float, bars: int | None = None, src_bpm: float | None = None,
                backend: str = "auto", cache_dir: Path | None = None) -> tuple[AudioClip, TempoEstimate]:
    """Datei laden, Tempo bestimmen (falls nicht angegeben), rendern und als float-WAV cachen."""
    src = Path(src)
    x = load_for_rc(src)
    est = estimate_tempo(x, src.name)
    if src_bpm is not None:
        est = TempoEstimate(float(src_bpm), bars, "manual", est.onset_bpm, est.candidates)
    use_bars = bars if bars is not None else est.bars
    y, used_bars = render(x, est.bpm, target_bpm, use_bars, backend)
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{src.resolve()}|{src.stat().st_mtime_ns}|{est.bpm:.4f}|{target_bpm:.4f}|"
                       f"{used_bars}|{backend}".encode()).hexdigest()[:16]
    out = cache_dir / f"{src.stem[:40]}_{target_bpm:g}bpm_{used_bars}bar_{key}.wav"
    write_float_wav(out, y)
    return AudioClip(out, len(y), float(target_bpm), used_bars), est
