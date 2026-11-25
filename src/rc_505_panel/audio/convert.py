"""Audio laden und ins RC-Format bringen: 44,1 kHz, Stereo, float32 (C4)."""
from __future__ import annotations

import struct
from math import gcd
from pathlib import Path

import numpy as np

from ..core.models import CHANNELS, SR


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Lädt WAV/FLAC/OGG/MP3 (über soundfile/libsndfile) als float32 (n, ch)."""
    path = Path(path)
    try:
        import soundfile as sf
    except ImportError:  # Fallback nur für float32-WAVs (z. B. Testumgebung ohne soundfile)
        from .rcwav import read_rc_wav
        return read_rc_wav(path), SR
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x, int(sr)


def to_stereo(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        x = x[:, None]
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    if x.shape[1] > 2:  # Mehrkanal: auf die ersten beiden Kanäle reduzieren
        return x[:, :2].copy()
    return x


def resample(x: np.ndarray, sr_from: int, sr_to: int = SR) -> np.ndarray:
    """Abtastraten-Wandlung. Mit scipy polyphasig, sonst per FFT (nur Fallback)."""
    if sr_from == sr_to:
        return x
    try:
        from scipy.signal import resample_poly
        g = gcd(sr_from, sr_to)
        return resample_poly(x, sr_to // g, sr_from // g, axis=0).astype(np.float32)
    except ImportError:
        n_out = int(round(len(x) * sr_to / sr_from))
        spec = np.fft.rfft(x, axis=0)
        n_bins = n_out // 2 + 1
        if n_bins <= spec.shape[0]:
            spec = spec[:n_bins]
        else:
            spec = np.vstack([spec, np.zeros((n_bins - spec.shape[0], x.shape[1]), spec.dtype)])
        return (np.fft.irfft(spec, n_out, axis=0) * (n_out / len(x))).astype(np.float32)


def load_for_rc(path: Path) -> np.ndarray:
    """Beliebige Audiodatei → (n, 2) float32 bei 44,1 kHz."""
    x, sr = load_audio(path)
    return resample(to_stereo(x), sr, SR)


def write_float_wav(path: Path, x: np.ndarray, sr: int = SR) -> None:
    """Schlichtes 32-Bit-Float-WAV (für Cache und externe Tools wie Rubber Band)."""
    x = np.ascontiguousarray(to_stereo(x), dtype="<f4")
    pcm = x.tobytes()
    fmt = struct.pack("<HHIIHH", 3, CHANNELS, sr, sr * CHANNELS * 4, CHANNELS * 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    Path(path).write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
