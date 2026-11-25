"""Kommandozeile. Ohne Argumente startet die GUI: `uv run rc-505-panel`.

    uv run rc-505-panel import --drive J: --mem 98 --track 4 --src loop.mp3 --bpm 104 [--bars 2]
    uv run rc-505-panel info --drive J: --mem 98
    uv run rc-505-panel backup --drive J: --mem 98
    uv run rc-505-panel restore --drive J: --backup <Ordner>

Live (Gerät im Modus VENDOR, Clock läuft, Assigns CC21–25 → TRK1–5 REC/PLY):
    uv run rc-505-panel live monitor
    uv run rc-505-panel live drop --track 1 --src loop.wav --bpm 104
    uv run rc-505-panel live calibrate --track 1 --bpm 104
    uv run rc-505-panel calibrate-measure --drive J: --mem 98 --track 1 --bpm 104 [--save]
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


def _live_session(settings):
    from .live.audio_out import AudioOut
    from .live.midi import MidiLink
    s = settings.live
    midi = MidiLink(s.midi_port_hint, s.midi_channel)
    audio = AudioOut(s.audio_device)
    return midi, audio


def _run_drop(settings, track: int, clip, bpm: float) -> None:
    from .live.autodrop import AutoDropEngine, DropState
    midi, audio = _live_session(settings)
    try:
        print(f"Ausgabe: Gerät {audio.device}, Latenz laut PortAudio {audio.latency_ms:.1f} ms, "
              f"Offset {settings.live.offset_ms:+.1f} ms")
        print("Warte auf Clock … (erst jetzt am Gerät STOP und ALL START drücken)")

        def report(job):
            if job.state == DropState.ARMED and job.plan:
                clock_bpm = job.plan.bpm
                warn = "  ⚠ weicht vom Memory-Tempo ab!" if clock_bpm and abs(clock_bpm - bpm) / bpm > 0.005 else ""
                print(f"Geplant: Takt {job.plan.target_tick // 96 + 1}, Clock {clock_bpm:.2f} BPM{warn}, "
                      f"Jitter {job.plan.jitter_ms:.2f} ms")
            elif job.state == DropState.RECORDING:
                print(f"REC-CC gesendet {job.cc_early_ms:.1f} ms vor dem Taktanfang")
            elif job.state in (DropState.FAILED, DropState.CANCELLED):
                print(f"Abbruch: {job.error}")
            elif job.state == DropState.DONE:
                print("Fertig.")
        job = AutoDropEngine(midi, audio, settings.live, on_state=report).drop(track, clip, block=True)
        if job.state != DropState.DONE:
            sys.exit(1)
    finally:
        audio.close()
        midi.close()


def _cmd_live(a: argparse.Namespace) -> None:
    import time
    from .core.config import Settings
    settings = Settings.load()
    if a.live_cmd == "monitor":
        from .live.midi import MidiLink
        with MidiLink(settings.live.midi_port_hint, settings.live.midi_channel) as midi:
            end = time.time() + a.seconds
            while time.time() < end:
                c = midi.clock
                est = c.time_of_tick(c.tick) if c.ready else None
                print(f"running={c.running!s:<5} Takt {max(c.tick, 0) // 96 + 1:<4} "
                      + (f"{c.bpm:.2f} BPM, Jitter {est.jitter_ms:.2f} ms" if est else "(keine stabile Clock)"))
                time.sleep(0.5)
    elif a.live_cmd == "drop":
        from .audio.rcwav import read_rc_wav
        from .audio.stretch import render_file
        clip, est = render_file(Path(a.src), a.bpm, a.bars, a.src_bpm, a.backend)
        print(f"Sample: {est.bpm:.2f} BPM ({est.source}) → {clip.bars} Takt(e) @ {a.bpm:g} BPM, {clip.frames} Frames")
        _run_drop(settings, a.track, read_rc_wav(clip.path), a.bpm)
    elif a.live_cmd == "calibrate":
        from .live.calibrate import make_click
        print(f"Kalibrier-Click: 1 Takt @ {a.bpm:g} BPM auf Spur {a.track} (MEASURE = 1, INPUT nur INST2)")
        _run_drop(settings, a.track, make_click(a.bpm, 1), a.bpm)
        print("Jetzt WRITE, dann STORAGE → CONNECT und:")
        print(f"  uv run rc-505-panel calibrate-measure --drive J: --mem <Memory> --track {a.track} --bpm {a.bpm:g} --save")


def _cmd_calibrate_measure(a: argparse.Namespace) -> None:
    from .audio.rcwav import read_rc_wav
    from .core.config import Settings
    from .live.calibrate import make_click, measure
    from .storage.backup import find_roland_root
    wav = find_roland_root(a.drive) / "WAVE" / f"{a.mem:03d}_{a.track}" / f"{a.mem:03d}_{a.track}.WAV"
    m = measure(make_click(a.bpm, 1), read_rc_wav(wav), a.bpm)
    settings = Settings.load()
    new = m.suggested_offset(settings.live.offset_ms)
    print(f"Pro Schlag: {', '.join(f'{x:+d}' for x in m.per_beat_frames)} Frames; Längen-Δ {m.length_delta:+d}")
    print(f"Versatz {m.offset_ms:+.2f} ms ({'zu spät' if m.offset_ms > 0 else 'zu früh' if m.offset_ms < 0 else 'exakt'}), "
          f"Streuung {m.spread_ms:.2f} ms")
    print(f"Offset bisher {settings.live.offset_ms:+.2f} ms → empfohlen {new:+.2f} ms")
    if a.save:
        settings.live.offset_ms = new
        print("Gespeichert:", settings.save())


def main(argv: list[str] | None = None) -> None:
    if argv is None and len(sys.argv) == 1:      # ohne Argumente → GUI
        from .ui.app import run
        sys.exit(run())
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
    live = s.add_parser("live", help="Live-Modus (VENDOR): Clock, Drop, Kalibrierung")
    ls = live.add_subparsers(dest="live_cmd", required=True)
    c = ls.add_parser("monitor", help="MIDI-Clock anzeigen")
    c.add_argument("--seconds", type=float, default=20)
    c = ls.add_parser("drop", help="Sample taktgenau auf eine Spur legen")
    c.add_argument("--track", type=int, required=True)
    c.add_argument("--src", required=True)
    c.add_argument("--bpm", type=float, required=True, help="Tempo des Memory")
    c.add_argument("--bars", type=int)
    c.add_argument("--src-bpm", type=float)
    c.add_argument("--backend", default="auto", choices=["auto", "wsola", "rubberband"])
    c = ls.add_parser("calibrate", help="Kalibrier-Click droppen")
    c.add_argument("--track", type=int, required=True)
    c.add_argument("--bpm", type=float, required=True)
    c = s.add_parser("calibrate-measure", help="Versatz der Kalibrier-Aufnahme messen (STORAGE)")
    c.add_argument("--drive", required=True)
    c.add_argument("--mem", type=int, required=True)
    c.add_argument("--track", type=int, required=True)
    c.add_argument("--bpm", type=float, required=True)
    c.add_argument("--save", action="store_true", help="empfohlenen Offset speichern")
    a = p.parse_args(argv)
    cmds = {"import": _cmd_import, "info": _cmd_info, "backup": _cmd_backup, "restore": _cmd_restore,
            "live": _cmd_live, "calibrate-measure": _cmd_calibrate_measure}
    try:
        cmds[a.cmd](a)
    except (FileNotFoundError, ValueError, RuntimeError, TimeoutError) as e:
        sys.exit(f"Fehler: {e}")
