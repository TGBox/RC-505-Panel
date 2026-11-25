"""Benutzereinstellungen (JSON) – u. a. Kalibrierung und Live-Profil."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "rc-505-panel" / "settings.json"


@dataclass
class LiveSettings:
    midi_port_hint: str = "RC-505"
    midi_channel: int = 0                       # 0 = Kanal 1
    audio_device: str = "RC-505mk2 INST2 WASAPI"  # ADR-0006
    offset_ms: float = -52.0                     # S1-Kalibrierung (WASAPI, 2026-11-25)
    cc_lead_ms: float = 30.0                     # REC-CC vor dem Downbeat (QUANTIZE = MEASURE)
    release: bool = True                         # CC 127 → 0 (MOMENT-Assigns)
    rec_play_cc: dict[str, int] = field(default_factory=lambda: {str(t): 20 + t for t in range(1, 6)})  # CC21–25
    stop_cc: dict[str, int] = field(default_factory=lambda: {str(t): 25 + t for t in range(1, 6)})      # CC26–30
    close_by_cc: bool = False                    # ADR-0002: Standard = Gerät schließt (MEASURE)


@dataclass
class Settings:
    live: LiveSettings = field(default_factory=LiveSettings)

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = Path(path) if path else default_config_path()
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = LiveSettings.__dataclass_fields__
        live = LiveSettings(**{k: v for k, v in raw.get("live", {}).items() if k in known})
        return cls(live=live)

    def save(self, path: Path | None = None) -> Path:
        path = Path(path) if path else default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path
