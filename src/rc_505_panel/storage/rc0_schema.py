"""Bedeutung der anonymen `.RC0`-Tags, soweit belegt (C2).

Quellen: Diffs aus Spike S1/S2 (docs/research). Alles, was nicht belegt ist, ist als
Hypothese markiert und wird bis zur Bestätigung nicht geschrieben.
"""
from __future__ import annotations

from dataclasses import dataclass

from .rc0 import Rc0Document

# ---------- Spuren (mem/TRACKn/…) ----------
# Belegt durch echte Aufnahme und WAV-Import (S2): U, V, W, X
TRACK_TEMPO_X10 = "U"      # Spurtempo × 10 (1040 = 104,0 BPM)
TRACK_FRAMES_PER_BAR = "V"  # Frames pro Takt (abgerundet)
TRACK_HAS_DATA = "W"        # 1 = Spur hat Audio
TRACK_FRAMES = "X"          # Länge in Frames
# Hypothesen (noch nicht schreiben): S = Anzahl Takte?, J = MEASURE-Modus?, Q/R = INPUT?


@dataclass(frozen=True)
class TrackInfo:
    track: int
    has_data: bool
    frames: int
    frames_per_bar: int
    tempo: float

    @property
    def bars(self) -> float | None:
        return self.frames / self.frames_per_bar if self.has_data and self.frames_per_bar else None


def track_info(doc: Rc0Document, track: int) -> TrackInfo:
    p = f"mem/TRACK{track}/"
    return TrackInfo(
        track=track,
        has_data=doc.get(p + TRACK_HAS_DATA) == 1,
        frames=doc.get(p + TRACK_FRAMES),
        frames_per_bar=doc.get(p + TRACK_FRAMES_PER_BAR),
        tempo=doc.get(p + TRACK_TEMPO_X10) / 10,
    )


def guess_memory_tempo(doc: Rc0Document) -> float | None:
    """Tempo des Memory aus einer belegten Spur. `MASTER/A` ist nicht verlässlich (S1: 830 bei 104 BPM)."""
    for n in range(1, 6):
        info = track_info(doc, n)
        if info.has_data:
            return info.tempo
    return None


# ---------- Assigns (mem/ASSIGNn/…) ----------
# Belegt durch Diff 00-ausgang → 01-eingerichtet: A = SW, C = SOURCE, H = TARGET
ASSIGN_SW = "A"
ASSIGN_SOURCE = "C"
ASSIGN_TARGET = "H"

# TARGET-Indizes: belegt sind nur diese beiden
TARGET_TRK1_REC_PLY = 0
TARGET_TRK1_STOP = 2


def source_index_for_cc(cc: int, allow_unverified: bool = False) -> int:
    """SOURCE-Index für MIDI-CC. Belegt: CC#01–31 → 38 + cc (CC#21 → 59, CC#26 → 64).

    CC#64–95 folgen laut Parameter Guide direkt danach (→ cc + 6), das ist aber noch nicht gemessen.
    """
    if 1 <= cc <= 31:
        return 38 + cc
    if 64 <= cc <= 95:
        if not allow_unverified:
            raise ValueError(f"CC#{cc}: Kodierung für CC#64–95 noch nicht am Gerät bestätigt")
        return cc + 6
    raise ValueError(f"CC#{cc} ist keine gültige Assign-Quelle (erlaubt: 1–31, 64–95)")


@dataclass(frozen=True)
class AssignSlot:
    slot: int
    on: bool
    source: int
    target: int


def read_assign(doc: Rc0Document, slot: int) -> AssignSlot:
    p = f"mem/ASSIGN{slot}/"
    return AssignSlot(slot, doc.get(p + ASSIGN_SW) == 1, doc.get(p + ASSIGN_SOURCE), doc.get(p + ASSIGN_TARGET))


def write_assign(doc: Rc0Document, slot: AssignSlot) -> None:
    p = f"mem/ASSIGN{slot.slot}/"
    doc.set(p + ASSIGN_SW, 1 if slot.on else 0)
    doc.set(p + ASSIGN_SOURCE, slot.source)
    doc.set(p + ASSIGN_TARGET, slot.target)
