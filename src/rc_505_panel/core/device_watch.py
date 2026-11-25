"""Erkennt, in welchem Modus die RC-505mkII gerade angeschlossen ist (C8).

- STORAGE: ein Laufwerk mit ROLAND/DATA und ROLAND/WAVE
- LIVE:    ein MIDI-Port, dessen Name „RC-505“ enthält (USB-Modus VENDOR/GENERIC)
- OFFLINE: nichts davon
Die Funktionen sind Qt-frei und billig genug für ein Polling im Sekundentakt.
"""
from __future__ import annotations

import os
import string
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import DeviceMode


@dataclass(frozen=True)
class DeviceStatus:
    mode: DeviceMode
    roland: Path | None = None      # bei STORAGE
    midi_port: str | None = None    # bei LIVE

    @property
    def label(self) -> str:
        if self.mode is DeviceMode.STORAGE and self.roland:
            return f"STORAGE ({self.roland.anchor.rstrip(os.sep) or self.roland})"
        if self.mode is DeviceMode.LIVE:
            return "LIVE (MIDI + Audio)"
        return "OFFLINE"


def _removable_drives() -> list[Path]:
    if sys.platform != "win32":
        return [Path(p) for p in ("/media", "/mnt", "/Volumes") if Path(p).is_dir()]
    import ctypes
    drives = []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << i):
            root = f"{letter}:\\"
            # 2 = DRIVE_REMOVABLE; Netzlaufwerke/CD-Laufwerke ohne Medium nicht anfassen
            if ctypes.windll.kernel32.GetDriveTypeW(root) == 2:
                drives.append(Path(root))
    return drives


def find_storage(extra: list[Path] | None = None) -> Path | None:
    """Erstes Laufwerk mit ROLAND/DATA + ROLAND/WAVE (bzw. Unterordner davon unter /media u. ä.)."""
    for base in list(extra or []) + _removable_drives():
        try:
            if (base / "ROLAND").is_dir():
                cands = [base / "ROLAND"]
            else:  # z. B. /media/<user>/<Laufwerk>/ROLAND
                cands = [p / "ROLAND" for p in base.iterdir() if p.is_dir()]
        except OSError:
            continue
        for r in cands:
            if (r / "DATA").is_dir() and (r / "WAVE").is_dir():
                return r
    return None


def find_midi_port(hint: str = "RC-505") -> str | None:
    try:
        import mido
        names = mido.get_input_names()
    except Exception:
        return None
    return next((n for n in names if hint.lower() in n.lower()), None)


def detect(midi_hint: str = "RC-505", extra_storage: list[Path] | None = None) -> DeviceStatus:
    roland = find_storage(extra_storage)
    if roland:
        return DeviceStatus(DeviceMode.STORAGE, roland=roland)
    port = find_midi_port(midi_hint)
    if port:
        return DeviceStatus(DeviceMode.LIVE, midi_port=port)
    return DeviceStatus(DeviceMode.OFFLINE)
