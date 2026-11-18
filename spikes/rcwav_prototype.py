"""Prototyp RC-505mkII-WAV-Writer (2026-11-18).

Baut WAVs im Format der RC-505mkII: 32-Bit Float, Stereo, 44.1 kHz,
fmt-Chunk mit 28 Byte, JUNK-Padding auf Vielfache von 256 KB.
Gegen 005_1.WAV und 002_3.WAV aus dem Backup byteidentisch verifiziert.

Aufruf: python spikes/rcwav_prototype.py <pfad/zur/xxx_y.WAV> [...]
"""
import struct
import sys

BLOCK = 262_144  # 256 KB
FMT_EXTRA = bytes.fromhex("0a0000000000000000000000")  # 12 Byte, wie im Original


def build_rc_wav(pcm_float32_interleaved: bytes) -> bytes:
    fmt = b"fmt " + struct.pack("<IHHIIHH", 28, 3, 2, 44100, 352800, 8, 32) + FMT_EXTRA
    body = b"WAVE" + fmt + b"data" + struct.pack("<I", len(pcm_float32_interleaved)) + pcm_float32_interleaved
    pad = (-(8 + len(body) + 8)) % BLOCK  # offen: Randfall pad == 0
    body += b"JUNK" + struct.pack("<I", pad) + bytes(pad)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def verify(path: str) -> bool:
    d = open(path, "rb").read()
    size = struct.unpack("<I", d[52:56])[0]  # data-Chunk-Header bei 48, Samples ab 56
    return build_rc_wav(d[56:56 + size]) == d


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, "byteidentisch" if verify(p) else "ABWEICHUNG")
