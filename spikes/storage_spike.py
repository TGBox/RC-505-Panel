# /// script
# requires-python = ">=3.12"
# dependencies = ["soundfile", "numpy"]
# ///
"""Spike S2 - Storage-Werkzeuge für die RC-505mkII (Wegwerf-Code, siehe Spec §6).

Das Gerät muss im STORAGE-Modus verbunden sein (MENU > USB > STORAGE: CONNECT).

    uv run spikes/storage_spike.py backup --drive E: --name 00-ausgang
    uv run spikes/storage_spike.py diff backups/00-ausgang backups/01-eingerichtet --mem 98 --out diff-01.txt
    uv run spikes/storage_spike.py write-wav --drive E: --mem 98 --track 3 --src click.wav [--set-frames]

Backups landen in ./backups/<name>/ROLAND/DATA (alle .RC0) und ./backups/<name>/ROLAND/WAVE/<mem>_*.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path


def _load_rcwav():
    """Lädt spikes/rcwav_prototype.py über den Dateipfad (für Pyrefly/Pylance ohne sys.path-Trick)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("rcwav_prototype", Path(__file__).with_name("rcwav_prototype.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_rc_wav


build_rc_wav = _load_rcwav()

SR = 44_100
VALUE = re.compile(r"^\s*<(\w+)>(-?\d+)</\1>\s*$")
OPEN = re.compile(r"^\s*<(\w+)(?:\s+id=\"(\d+)\")?[^>/]*>\s*$")
CLOSE = re.compile(r"^\s*</(\w+)>\s*$")
COUNT = re.compile(r"<count>([0-9A-Fa-f]+)</count>")  # hexadezimal, z. B. 000F


# ---------- RC0 ----------

def rc0_values(path: Path) -> tuple[dict[str, int], int | None]:
    """Liest alle Zahlenwerte als {'mem/TRACK1/X': 83535, ...} plus <count>."""
    text = path.read_text(encoding="utf-8", errors="replace")
    vals: dict[str, int] = {}
    stack: list[str] = []
    for line in text.splitlines():
        if m := VALUE.match(line):
            if m[1] != "count":  # <count> ist hexadezimal und wird separat gelesen
                vals["/".join(stack + [m[1]])] = int(m[2])
        elif m := CLOSE.match(line):
            if stack and stack[-1].split("#")[0] == m[1]:
                stack.pop()
        elif (m := OPEN.match(line)) and not line.lstrip().startswith("<?"):
            if m[1] == "database":
                continue
            stack.append(m[1])
    c = COUNT.search(text)
    return vals, int(c[1], 16) if c else None


def current_rc0(data_dir: Path, mem: int) -> tuple[Path, int | None]:
    """Gibt die aktuelle Datei (höherer <count>) aus A/B zurück."""
    best = None
    for ab in "AB":
        p = data_dir / f"MEMORY{mem:03d}{ab}.RC0"
        if p.exists():
            _, c = rc0_values(p)
            if best is None or (c or -1) > (best[1] or -1):
                best = (p, c)
    if best is None:
        sys.exit(f"Keine MEMORY{mem:03d}A/B.RC0 in {data_dir}")
    return best


def set_value(path: Path, section_path: str, value: int) -> int:
    """Setzt z. B. 'mem/TRACK3/X' textuell (Rest der Datei bleibt Byte für Byte gleich)."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    stack: list[str] = []
    want = section_path.split("/")
    for i, line in enumerate(lines):
        if m := VALUE.match(line):
            if stack + [m[1]] == want:
                old = int(m[2])
                lines[i] = line.replace(f">{m[2]}<", f">{value}<", 1)
                path.write_bytes(nl.join(lines).encode("utf-8"))
                return old
        elif m := CLOSE.match(line):
            if stack and stack[-1] == m[1]:
                stack.pop()
        elif (m := OPEN.match(line)) and not line.lstrip().startswith("<?") and m[1] != "database":
            stack.append(m[1])
    sys.exit(f"{section_path} nicht gefunden in {path}")


# ---------- Befehle ----------

def roland(drive: str) -> Path:
    base = Path(drive if drive.endswith(("/", "\\")) else drive + "/")
    r = base / "ROLAND" if (base / "ROLAND").exists() else base
    if not (r / "DATA").exists():
        sys.exit(f"Kein ROLAND/DATA unter {drive} – ist das Gerät im STORAGE-Modus verbunden?")
    return r


def do_backup(drive: str, name: str, mems: list[int]) -> Path:
    src = roland(drive)
    dst = Path("backups") / name / "ROLAND"
    if dst.exists():
        sys.exit(f"{dst} existiert schon – anderen Namen wählen")
    shutil.copytree(src / "DATA", dst / "DATA")
    for mem in mems:
        for t in range(1, 6):
            d = src / "WAVE" / f"{mem:03d}_{t}"
            if d.exists():
                shutil.copytree(d, dst / "WAVE" / d.name)
    print(f"Backup: {dst} ({len(list((dst / 'DATA').glob('*.RC0')))} RC0-Dateien)")
    return dst


def cmd_backup(a):
    do_backup(a.drive, a.name, a.mem or [])


def cmd_diff(a):
    if a.out:
        import contextlib
        with open(a.out, "w", encoding="utf-8") as fh, contextlib.redirect_stdout(fh):
            _diff(a)
        print(f"Diff geschrieben: {a.out}")
    else:
        _diff(a)


def _diff(a):
    def base(p: str) -> Path:
        q = Path(p)
        for c in (q / "ROLAND", q):
            if (c / "DATA").exists():
                return c
        sys.exit(f"Kein DATA-Ordner in {p}")
    A, B = base(a.before), base(a.after)
    for mem in a.mem:
        print(f"\n===== Memory {mem:03d} =====")
        for ab in "AB":
            fa, fb = A / "DATA" / f"MEMORY{mem:03d}{ab}.RC0", B / "DATA" / f"MEMORY{mem:03d}{ab}.RC0"
            ca = rc0_values(fa)[1] if fa.exists() else None
            cb = rc0_values(fb)[1] if fb.exists() else None
            same = fa.exists() and fb.exists() and fa.read_bytes() == fb.read_bytes()
            fmt = lambda c: "-" if c is None else f"{c:04X}"  # noqa: E731
            print(f"{ab}: count {fmt(ca)} -> {fmt(cb)}  {'(unverändert)' if same else '(geändert)'}")
        pa, _ = current_rc0(A / "DATA", mem)
        pb, _ = current_rc0(B / "DATA", mem)
        va, _ = rc0_values(pa)
        vb, _ = rc0_values(pb)
        print(f"Vergleiche aktuelle Dateien: {pa.name} -> {pb.name}")
        changed = [k for k in sorted(set(va) | set(vb)) if va.get(k) != vb.get(k)]
        for k in changed:
            print(f"  {k:<40} {va.get(k)!s:>10} -> {vb.get(k)!s:<10}")
        print(f"  ({len(changed)} Werte geändert)")
        for t in range(1, 6):
            wa = A / "WAVE" / f"{mem:03d}_{t}" / f"{mem:03d}_{t}.WAV"
            wb = B / "WAVE" / f"{mem:03d}_{t}" / f"{mem:03d}_{t}.WAV"
            sa = wa.stat().st_size if wa.exists() else None
            sb = wb.stat().st_size if wb.exists() else None
            if sa != sb:
                print(f"  WAV Spur {t}: {sa} -> {sb} Bytes")


def cmd_write_wav(a):
    import numpy as np
    import soundfile as sf
    r = roland(a.drive)
    ts = time.strftime("%Y%m%d-%H%M%S")
    do_backup(a.drive, f"auto-vor-write-{ts}", [a.mem])
    x, sr = sf.read(a.src, dtype="float32", always_2d=True)
    if sr != SR:
        sys.exit(f"{a.src}: {sr} Hz – bitte 44.1 kHz verwenden")
    x = np.repeat(x, 2, axis=1) if x.shape[1] == 1 else x[:, :2]
    frames = len(x)
    folder = r / "WAVE" / f"{a.mem:03d}_{a.track}"
    folder.mkdir(exist_ok=True)
    out = folder / f"{a.mem:03d}_{a.track}.WAV"
    out.write_bytes(build_rc_wav(np.ascontiguousarray(x, dtype="<f4").tobytes()))
    print(f"WAV geschrieben: {out} ({frames} Frames, {out.stat().st_size} Bytes)")
    if a.set_frames:
        for ab in "AB":
            p = r / "DATA" / f"MEMORY{a.mem:03d}{ab}.RC0"
            old = set_value(p, f"mem/TRACK{a.track}/X", frames)
            print(f"{p.name}: mem/TRACK{a.track}/X {old} -> {frames}")
    print("Jetzt am Gerät die Verbindung trennen (EXIT/WRITE) und die Spur prüfen.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    c = s.add_parser("backup"); c.add_argument("--drive", required=True); c.add_argument("--name", required=True)
    c.add_argument("--mem", type=int, nargs="*", help="Memories, deren WAVs mitgesichert werden")
    c = s.add_parser("diff"); c.add_argument("before"); c.add_argument("after")
    c.add_argument("--mem", type=int, nargs="+", required=True)
    c.add_argument("--out", help="Ergebnis als UTF-8-Datei schreiben (statt PowerShell-Umleitung >)")
    c = s.add_parser("write-wav"); c.add_argument("--drive", required=True)
    c.add_argument("--mem", type=int, required=True); c.add_argument("--track", type=int, required=True)
    c.add_argument("--src", required=True); c.add_argument("--set-frames", action="store_true",
                                                         help="auch mem/TRACKn/X in A und B setzen")
    a = p.parse_args(argv)
    {"backup": cmd_backup, "diff": cmd_diff, "write-wav": cmd_write_wav}[a.cmd](a)


if __name__ == "__main__":
    main()
