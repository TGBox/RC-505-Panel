"""Kommandozeile für den Offline-Kern (bis die GUI aus Phase 3 steht).

    uv run rc-505-panel import --drive J: --mem 98 --track 4 --src loop.mp3 --bpm 104 [--bars 2]
    uv run rc-505-panel info --drive J: --mem 98
    uv run rc-505-panel backup --drive J: --mem 98
    uv run rc-505-panel restore --drive J: --backup <Ordner>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core.models import TrackRef


def _cmd_import(a: argparse.Namespace) -> None:
    from .storage.track_import import import_file
    res = import_file(a.drive, TrackRef(a.mem, a.track), Path(a.src), a.bpm, a.bars, a.src_bpm, a.backend)
    t = res.tempo
    print(f"Quelle: {t.bpm:.2f} BPM ({t.source}" + (f", Onset {t.onset_bpm:.1f}" if t and t.onset_bpm else "") + ")")
    print(f"Geschrieben: {res.wav_path} – {res.bars} Takt(e) @ {res.target_bpm:g} BPM = {res.frames} Frames")
    print(f"Backup: {res.backup_dir}")
    print("Am Gerät trennen, Memory wechseln und zurück – dann ist die Spur geladen.")


def _cmd_info(a: argparse.Namespace) -> None:
    from .storage.backup import find_roland_root
    from .storage.rc0 import Rc0Document
    from .storage.rc0_schema import guess_memory_tempo, read_assign, track_info
    doc = Rc0Document.load(find_roland_root(a.drive) / "DATA", a.mem)
    print(f"Memory {a.mem:03d} „{doc.name()}“ – Datei {doc.source.name}, count {doc.count:04X}")
    print(f"Tempo (aus belegter Spur): {guess_memory_tempo(doc) or '–'}")
    for n in range(1, 6):
        i = track_info(doc, n)
        print(f"  Spur {n}: " + (f"{i.frames} Frames, {i.bars:g} Takt(e) @ {i.tempo:g} BPM" if i.has_data else "leer"))
    for s in range(1, 17):
        asg = read_assign(doc, s)
        if asg.on:
            print(f"  ASSIGN{s}: SOURCE {asg.source}, TARGET {asg.target}")


def _cmd_backup(a: argparse.Namespace) -> None:
    from .storage.backup import backup_memory, find_roland_root
    print(backup_memory(find_roland_root(a.drive), a.mem, label="manuell"))


def _cmd_restore(a: argparse.Namespace) -> None:
    from .storage.backup import find_roland_root, restore_memory
    for c in restore_memory(Path(a.backup), find_roland_root(a.drive)):
        print(" ", c)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="rc-505-panel", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    c = s.add_parser("import", help="Sample auf eine Spur schreiben")
    c.add_argument("--drive", required=True)
    c.add_argument("--mem", type=int, required=True)
    c.add_argument("--track", type=int, required=True)
    c.add_argument("--src", required=True)
    c.add_argument("--bpm", type=float, required=True, help="Tempo des Memory")
    c.add_argument("--bars", type=int, help="Takte (Standard: aus dem Sample geschätzt)")
    c.add_argument("--src-bpm", type=float, help="Tempo des Samples (Standard: geschätzt)")
    c.add_argument("--backend", default="auto", choices=["auto", "wsola", "rubberband"])
    c = s.add_parser("info", help="Memory-Übersicht")
    c.add_argument("--drive", required=True)
    c.add_argument("--mem", type=int, required=True)
    c = s.add_parser("backup", help="Memory sichern")
    c.add_argument("--drive", required=True)
    c.add_argument("--mem", type=int, required=True)
    c = s.add_parser("restore", help="Memory aus Backup wiederherstellen")
    c.add_argument("--drive", required=True)
    c.add_argument("--backup", required=True)
    a = p.parse_args(argv)
    try:
        {"import": _cmd_import, "info": _cmd_info, "backup": _cmd_backup, "restore": _cmd_restore}[a.cmd](a)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"Fehler: {e}")
