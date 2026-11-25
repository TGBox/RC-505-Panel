"""WAV-Dateien im Format der RC-505mkII lesen und schreiben (C3).

Format (aus dem Backup, byteidentisch nachgebaut):
- RIFF/WAVE, `fmt `-Chunk mit 28 Byte: IEEE-Float (3), 2 Kanäle, 44 100 Hz, 32 Bit,
  plus 12 Byte Extra `0a 00 00 …` wie im Original
- `data`-Chunk-Header bei Offset 48, Samples ab Offset 56 (interleaved float32 L/R)
- danach ein `JUNK`-Chunk, sodass die Datei ein Vielfaches von 256 KB groß ist.
  Der JUNK-Chunk wird immer geschrieben (bei exakt passender Größe mit 0 Byte Inhalt).
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

import numpy as np

from ..core.models import CHANNELS, SR

BLOCK = 262_144  # 256 KB
_FMT_EXTRA = bytes.fromhex("0a0000000000000000000000")  # 12 Byte
_DATA_OFFSET = 56


class RcWavError(ValueError):
    pass


def build_rc_wav(samples: np.ndarray) -> bytes:
    """Erzeugt die Dateibytes aus float32-Samples der Form (n, 2)."""
    x = np.asarray(samples)
    if x.ndim != 2 or x.shape[1] != CHANNELS:
        raise RcWavError(f"Erwartet (n, 2), bekommen {x.shape}")
    pcm = np.ascontiguousarray(x, dtype="<f4").tobytes()
    fmt = b"fmt " + struct.pack("<IHHIIHH", 28, 3, CHANNELS, SR, SR * CHANNELS * 4, CHANNELS * 4, 32) + _FMT_EXTRA
    body = b"WAVE" + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    pad = (-(8 + len(body) + 8)) % BLOCK
    body += b"JUNK" + struct.pack("<I", pad) + bytes(pad)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def write_rc_wav(path: Path, samples: np.ndarray) -> int:
    """Schreibt atomar (tmp + rename) und gibt die Anzahl Frames zurück."""
    path = Path(path)
    data = build_rc_wav(samples)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return int(np.asarray(samples).shape[0])


def read_rc_wav(path: Path) -> np.ndarray:
    """Liest RC-WAVs (und andere einfache float32-Stereo-WAVs) als (n, 2) float32."""
    d = Path(path).read_bytes()
    if d[:4] != b"RIFF" or d[8:12] != b"WAVE":
        raise RcWavError(f"{path}: keine WAV-Datei")
    i = 12
    fmt = None
    while i + 8 <= len(d):
        cid = d[i:i + 4]
        size = struct.unpack("<I", d[i + 4:i + 8])[0]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", d[i + 8:i + 24])
        elif cid == b"data":
            if fmt is None or fmt[0] != 3 or fmt[1] != CHANNELS or fmt[5] != 32:
                raise RcWavError(f"{path}: kein 32-Bit-Float-Stereo ({fmt})")
            return np.frombuffer(d[i + 8:i + 8 + size], dtype="<f4").reshape(-1, CHANNELS).copy()
        i += 8 + size + (size & 1)
    raise RcWavError(f"{path}: kein data-Chunk")
