"""Backup und Wiederherstellung einzelner Memories vor jedem Schreibzugriff (AC4)."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from ..core.models import TRACKS


def default_backup_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "rc-505-panel" / "backups"


def find_roland_root(drive: str | Path) -> Path:
    """Akzeptiert 'J:', 'J:/', '…/ROLAND' oder einen Ordner, der ROLAND enthält."""
    p = Path(drive if str(drive).endswith(("/", "\\")) or len(str(drive)) != 2 else f"{drive}/")
    for cand in (p, p / "ROLAND"):
        if (cand / "DATA").is_dir() and (cand / "WAVE").is_dir():
            return cand
    raise FileNotFoundError(f"Kein ROLAND/DATA + ROLAND/WAVE unter {drive} – Gerät im STORAGE-Modus verbunden?")


def backup_memory(roland: Path, memory: int, backup_root: Path | None = None, label: str = "") -> Path:
    """Kopiert MEMORYnnnA/B.RC0 und WAVE/nnn_1–5 (auch leere Ordner) in einen Zeitstempel-Ordner."""
    roland = Path(roland)
    root = Path(backup_root) if backup_root else default_backup_root()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = root / f"{stamp}_mem{memory:03d}{'_' + label if label else ''}"
    (dest / "DATA").mkdir(parents=True)
    files = []
    for ab in "AB":
        src = roland / "DATA" / f"MEMORY{memory:03d}{ab}.RC0"
        if src.exists():
            shutil.copy2(src, dest / "DATA" / src.name)
            files.append(f"DATA/{src.name}")
    for t in TRACKS:
        name = f"{memory:03d}_{t}"
        src = roland / "WAVE" / name
        (dest / "WAVE" / name).mkdir(parents=True)
        if src.is_dir():
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, dest / "WAVE" / name / f.name)
                    files.append(f"WAVE/{name}/{f.name}")
    manifest = {"memory": memory, "created": stamp, "source": str(roland), "files": files}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dest


def restore_memory(backup_dir: Path, roland: Path) -> list[str]:
    """Stellt den gesicherten Stand exakt wieder her (inkl. Entfernen später hinzugekommener WAVs)."""
    backup_dir, roland = Path(backup_dir), Path(roland)
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    memory = manifest["memory"]
    changed = []
    for ab in "AB":
        src = backup_dir / "DATA" / f"MEMORY{memory:03d}{ab}.RC0"
        if src.exists():
            shutil.copy2(src, roland / "DATA" / src.name)
            changed.append(src.name)
    for t in TRACKS:
        name = f"{memory:03d}_{t}"
        dst = roland / "WAVE" / name
        dst.mkdir(parents=True, exist_ok=True)
        wanted = {f.name for f in (backup_dir / "WAVE" / name).iterdir() if f.is_file()}
        for f in dst.iterdir():
            if f.is_file() and f.name not in wanted:
                f.unlink()
                changed.append(f"-{name}/{f.name}")
        for fname in wanted:
            shutil.copy2(backup_dir / "WAVE" / name / fname, dst / fname)
            changed.append(f"{name}/{fname}")
    return changed
