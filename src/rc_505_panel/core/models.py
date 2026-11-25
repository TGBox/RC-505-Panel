"""Gemeinsame Datenklassen (Qt-frei)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

SR = 44_100          # Abtastrate der RC-505mkII
CHANNELS = 2
MEMORIES = range(1, 100)
TRACKS = range(1, 6)


class DeviceMode(Enum):
    OFFLINE = auto()   # kein Gerät, nur lokale Bearbeitung
    STORAGE = auto()   # Laufwerk mit ROLAND/DATA + ROLAND/WAVE
    LIVE = auto()      # MIDI-Port "RC-505MK2" + Audio-Device vorhanden


@dataclass(frozen=True)
class TrackRef:
    memory: int        # 1..99
    track: int         # 1..5

    def __post_init__(self) -> None:
        if self.memory not in MEMORIES:
            raise ValueError(f"Memory muss 1–99 sein, nicht {self.memory}")
        if self.track not in TRACKS:
            raise ValueError(f"Spur muss 1–5 sein, nicht {self.track}")

    @property
    def wave_dir_name(self) -> str:
        return f"{self.memory:03d}_{self.track}"


@dataclass(frozen=True)
class AudioClip:
    """Ein fertig gerendertes Sample: 44,1 kHz, Stereo, float32, exakt `bars` Takte bei `bpm`."""
    path: Path
    frames: int
    bpm: float
    bars: int


def frames_per_bar(bpm: float, beats_per_bar: int = 4) -> int:
    """Frames pro Takt so, wie die RC-505mkII sie speichert (abgerundet).

    Belegt durch das Backup: 91 BPM -> 116307 (116307,69), 104 BPM -> 101769 (101769,23).
    """
    return int(beats_per_bar * 60 * SR / bpm)


def loop_frames(bpm: float, bars: int, beats_per_bar: int = 4) -> int:
    """Loop-Länge in Frames wie am Gerät: Takte × abgerundete Taktlänge.

    Belegt: 4 Takte @ 91 BPM -> 465228 = 4 × 116307 (nicht floor(4 × 116307,69) = 465230).
    """
    return bars * frames_per_bar(bpm, beats_per_bar)
