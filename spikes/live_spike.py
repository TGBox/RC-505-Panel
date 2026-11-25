# /// script
# requires-python = ">=3.12"
# dependencies = ["mido", "python-rtmidi", "sounddevice", "soundfile", "numpy"]
# ///
"""Spike S1 - Live-Machbarkeit der RC-505mkII (Wegwerf-Code, siehe Spec §6).

Aufruf (uv liest die Abhängigkeiten aus dem Kopf dieser Datei):
    uv run spikes/live_spike.py list
    uv run spikes/live_spike.py clock [--seconds 20]
    uv run spikes/live_spike.py cc --cc 21 [--value 127]
    uv run spikes/live_spike.py click --bpm 120 --bars 1 --out click.wav
    uv run spikes/live_spike.py drop --wav click.wav --cc 21 [--device "RC-505mk2 INST2 WASAPI"] [--offset-ms 0] [--cc-lead-ms 30]
    uv run spikes/live_spike.py xcorr --ref click.wav --rec "E:/ROLAND/WAVE/001_1/001_1.WAV"

ASIO: vor dem Aufruf `set SD_ENABLE_ASIO=1` (cmd) bzw. `$env:SD_ENABLE_ASIO=1` (PowerShell).
"""
from __future__ import annotations

import argparse
import struct
import sys
import threading
import time

SR = 44_100
PPQN = 24
TICKS_PER_BAR = PPQN * 4  # 4/4
PORT_HINT = "RC-505"


# ---------- MIDI ----------

def find_port(names: list[str], hint: str) -> str:
    hits = [n for n in names if hint.lower() in n.lower()]
    if not hits:
        sys.exit(f"Kein MIDI-Port mit '{hint}' gefunden. Vorhanden: {names}")
    return hits[0]


class ClockFollower:
    """Zählt MIDI-Clock-Ticks seit START und schätzt das Tempo."""

    def __init__(self, now=time.perf_counter):
        self.now = now
        self.running = False
        self.tick = 0                 # Ticks seit START (0 = Downbeat Takt 1)
        self.last_tick_time: float | None = None
        self.intervals: list[float] = []
        self.orphan_ticks = 0         # Clock-Ticks ohne vorheriges START (Position unbekannt)
        self.starts = 0               # Anzahl empfangener START-Meldungen (Diagnose)
        self.history: list[tuple[int, float]] = []  # (Tick, Ankunftszeit) seit START
        self.start_time: float | None = None
        self.lock = threading.Lock()

    def feed(self, msg_type: str, t: float | None = None) -> None:
        t = self.now() if t is None else t
        with self.lock:
            if msg_type == "start":
                self.running, self.tick, self.last_tick_time = True, 0, None
                self.starts += 1
                self.start_time = t
                self.history = []
                self.intervals.clear()
            elif msg_type == "stop":
                self.running = False
            elif msg_type == "continue":
                self.running = True
            elif msg_type == "clock" and not self.running:
                self.orphan_ticks += 1
            elif msg_type == "clock" and self.running:
                if self.last_tick_time is not None:
                    self.intervals.append(t - self.last_tick_time)
                    self.intervals = self.intervals[-PPQN * 2:]
                    self.tick += 1
                self.last_tick_time = t
                self.history.append((self.tick, t))
                self.history = self.history[-4 * TICKS_PER_BAR:]

    @property
    def tick_interval(self) -> float | None:
        with self.lock:
            return sum(self.intervals) / len(self.intervals) if len(self.intervals) >= PPQN else None

    @property
    def bpm(self) -> float | None:
        ti = self.tick_interval
        return 60.0 / (ti * PPQN) if ti else None

    def time_of_tick(self, k: int) -> tuple[float, float] | None:
        """Zeitpunkt von Tick k per Ausgleichsgerade über die letzten Ticks (glättet USB-Jitter).
        Gibt (Zeit, Residuen-Std in ms) zurück."""
        import numpy as np
        with self.lock:
            h = list(self.history)
        if len(h) < PPQN:
            return None
        ks = np.array([x[0] for x in h], dtype=float)
        ts = np.array([x[1] for x in h])
        slope, icpt = np.polyfit(ks - ks[0], ts - ts[0], 1)
        resid = (ts - ts[0]) - (slope * (ks - ks[0]) + icpt)
        return ts[0] + icpt + slope * (k - ks[0]), float(resid.std() * 1000)

    def next_downbeat(self) -> float | None:
        """Geschätzte perf_counter-Zeit des nächsten Taktanfangs."""
        ti = self.tick_interval
        with self.lock:
            if not self.running or ti is None or self.last_tick_time is None:
                return None
            remaining = TICKS_PER_BAR - (self.tick % TICKS_PER_BAR)
            return self.last_tick_time + remaining * ti


def open_midi(hint: str, follower: ClockFollower | None = None):
    import mido
    out = mido.open_output(find_port(mido.get_output_names(), hint))
    inp = None
    if follower is not None:
        def cb(msg):
            if msg.type in ("clock", "start", "stop", "continue"):
                follower.feed(msg.type)
        inp = mido.open_input(find_port(mido.get_input_names(), hint), callback=cb)
    return out, inp


def resolve_output_device(query):
    """Index oder Suchwörter (Reihenfolge und Groß-/Kleinschreibung egal) → eindeutiger Ausgabe-Index."""
    import sounddevice as sd
    if query is None or isinstance(query, int):
        return query
    words = str(query).lower().split()
    hits = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] <= 0:
            continue
        full = f"{d['name']}, {sd.query_hostapis(d['hostapi'])['name']}"
        if all(w in full.lower() for w in words):
            hits.append((i, full))
    if len(hits) != 1:
        found = "\n  ".join(f"[{i}] {n}" for i, n in hits) or "(keins)"
        sys.exit(f"Ausgabegerät '{query}' nicht eindeutig gefunden:\n  {found}")
    print(f"Ausgabegerät: [{hits[0][0]}] {hits[0][1]}")
    return hits[0][0]


def send_cc(out, cc: int, value: int, channel: int) -> None:
    import mido
    out.send(mido.Message("control_change", control=cc, value=value, channel=channel))


# ---------- WAV-Hilfen ----------

def read_any_wav(path: str):
    """Liest Standard-WAVs (soundfile) und RC-WAVs (fmt mit 28 Byte, JUNK) als float32 (n, 2)."""
    import numpy as np
    d = open(path, "rb").read()
    if d[12:16] == b"fmt " and struct.unpack("<I", d[16:20])[0] == 28 and d[48:52] == b"data":
        n = struct.unpack("<I", d[52:56])[0]
        return np.frombuffer(d[56:56 + n], dtype="<f4").reshape(-1, 2).copy()
    import soundfile as sf
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    if sr != SR:
        sys.exit(f"{path}: {sr} Hz – bitte vorher auf 44.1 kHz bringen")
    return np.repeat(x, 2, axis=1) if x.shape[1] == 1 else x[:, :2]


def make_click(bpm: float, bars: int):
    import numpy as np
    frames = round(bars * 4 * 60 / bpm * SR)
    x = np.zeros((frames, 2), dtype="float32")
    beat = 60 / bpm * SR
    burst = (np.sin(2 * np.pi * 1000 * np.arange(441) / SR) * np.hanning(441)).astype("float32")
    for i in range(bars * 4):
        s = round(i * beat)
        amp = 0.9 if i % 4 == 0 else 0.4
        x[s:s + 441] += (amp * burst)[: frames - s, None]
    return x


# ---------- Befehle ----------

def cmd_list(_a):
    import mido
    import sounddevice as sd
    print("MIDI IN :", mido.get_input_names())
    print("MIDI OUT:", mido.get_output_names())
    print("\nHost-APIs:", [h["name"] for h in sd.query_hostapis()])
    for i, d in enumerate(sd.query_devices()):
        api = sd.query_hostapis(d["hostapi"])["name"]
        print(f"[{i:2}] {api:<22} in={d['max_input_channels']:<2} out={d['max_output_channels']:<2} "
              f"sr={d['default_samplerate']:.0f}  {d['name']}")


def cmd_clock(a):
    f = ClockFollower()
    _out, inp = open_midi(a.port, f)
    print("Warte auf MIDI-Clock… (am Gerät ALL START drücken)")
    t_end = time.time() + a.seconds
    while time.time() < t_end:
        time.sleep(0.5)
        bpm = f.bpm
        print(f"running={f.running!s:<5} tick={f.tick:<6} bar={f.tick // TICKS_PER_BAR + 1:<4} "
              f"bpm={bpm:.2f}" if bpm else f"running={f.running} (noch keine stabile Clock)")
    inp.close()


def cmd_cc(a):
    out, _ = open_midi(a.port)
    send_cc(out, a.cc, a.value, a.channel)
    print(f"CC#{a.cc}={a.value} auf Kanal {a.channel + 1} gesendet")
    if a.release:
        time.sleep(0.05)
        send_cc(out, a.cc, 0, a.channel)


def cmd_click(a):
    import soundfile as sf
    x = make_click(a.bpm, a.bars)
    sf.write(a.out, x, SR, subtype="FLOAT")
    print(f"{a.out}: {len(x)} Frames = {a.bars} Takt(e) @ {a.bpm} BPM")


def cmd_drop(a):
    import sounddevice as sd

    clip = read_any_wav(a.wav)
    device = resolve_output_device(a.device)  # vor dem Warten prüfen, nicht erst am Downbeat
    f = ClockFollower()
    out, inp = open_midi(a.port, f)
    print("Warte auf laufende Clock… (ALL START am Gerät, falls noch nicht gestartet)")
    warned = False
    while f.next_downbeat() is None or f.time_of_tick(0) is None:
        if f.orphan_ticks > PPQN and not warned:
            print("Clock läuft, aber das START-Signal kam vor dem Skriptstart – Taktposition unbekannt.\n"
                  "→ Am Gerät STOP drücken und dann erneut ALL START.")
            warned = True
        time.sleep(0.05)
    print(f"Clock läuft: {f.bpm:.2f} BPM")
    starts_at_plan = f.starts  # kommt danach ein weiteres START/STOP, ist das Ziel ungültig

    # Ziel = Taktanfang als Tick-Nummer festlegen; die Zeit dazu wird bis kurz vorher nachgeschärft
    target_tick = (f.tick // TICKS_PER_BAR + 1) * TICKS_PER_BAR
    if f.time_of_tick(target_tick)[0] - time.perf_counter() < 0.8:
        target_tick += TICKS_PER_BAR

    state = {"audio_target": None, "delta": None, "i": None}

    def callback(outdata, frames, tinfo, status):
        if status:
            print("Audio-Status:", status, file=sys.stderr)
        outdata.fill(0)
        at, delta = state["audio_target"], state["delta"]
        if at is None or delta is None:
            return
        dac = tinfo.outputBufferDacTime + delta  # perf_counter-Zeit des 1. Samples dieses Puffers
        if state["i"] is None:
            start = round((at - dac) * SR)
            if start >= frames:
                return
            state["i"] = -start  # negativ = Startoffset innerhalb dieses Puffers
        i = state["i"]
        dst0 = max(0, -i)
        src0 = max(0, i)
        n = min(frames - dst0, len(clip) - src0)
        if n > 0:
            outdata[dst0:dst0 + n, a.ch0:a.ch0 + 2] = clip[src0:src0 + n]
        state["i"] = i + frames
        if src0 + n >= len(clip):
            raise sd.CallbackStop

    def abort_if_restarted(stream):
        if f.starts != starts_at_plan or not f.running:
            stream.abort()
            sys.exit("Abbruch: START/STOP am Gerät während der Wartezeit – Taktposition hat sich geändert.\n"
                     "Spur prüfen/leeren und den Drop neu starten (STOP + ALL START nur einmal drücken).")

    nch = a.ch0 + 2
    with sd.OutputStream(device=device, samplerate=SR, channels=nch, dtype="float32",
                         latency=a.latency, callback=callback) as stream:
        print(f"Stream-Latenz laut PortAudio: {stream.latency * 1000:.1f} ms")
        # PC-Uhr ↔ Audio-Uhr: viele Paare im Hauptthread lesen, die schnellsten Lesungen mitteln
        pairs = []
        for _ in range(40):
            t1 = time.perf_counter(); st = stream.time; t2 = time.perf_counter()
            pairs.append((t2 - t1, (t1 + t2) / 2 - st))
            time.sleep(0.002)
        pairs.sort()
        best = [d for _, d in pairs[:10]]
        state["delta"] = sum(best) / len(best)
        delta_spread = (max(best) - min(best)) * 1000

        # Taktanfang laufend per Ausgleichsgerade neu schätzen, 150 ms vor Audiostart einfrieren
        while True:
            abort_if_restarted(stream)
            target, jitter = f.time_of_tick(target_tick)
            at = target + a.offset_ms / 1000.0
            if at - time.perf_counter() < 0.15:
                break
            state["audio_target"] = at
            time.sleep(0.01)
        state["audio_target"] = at
        print(f"Diagnose: Clock-Jitter (Std der Ticks um die Gerade) {jitter:.2f} ms, "
              f"Uhrenabgleich-Streuung {delta_spread:.3f} ms, Ziel-Tick {target_tick} "
              f"(Takt {target_tick // TICKS_PER_BAR + 1}), START empfangen {f.starts}x")

        # CC zum Downbeat senden, optional früher (bei REC QUANTIZE = MEASURE nötig)
        cc_at = target - a.cc_lead_ms / 1000.0
        while (rest := cc_at - time.perf_counter()) > 0.003:
            time.sleep(min(rest - 0.002, 0.05))
        while time.perf_counter() < cc_at:
            pass
        send_cc(out, a.cc, 127, a.channel)
        t_sent = time.perf_counter()
        if a.release:
            send_cc(out, a.cc, 0, a.channel)
        print(f"REC-CC gesendet {(target - t_sent) * 1000:.2f} ms vor dem Downbeat "
              f"(Soll: {a.cc_lead_ms:.1f} ms)")
        dur = len(clip) / SR
        if a.close_cc:
            # Fallback (ADR-0002): Aufnahme per zweitem CC schließen
            close_at = target + dur
            while (rest := close_at - time.perf_counter()) > 0.003:
                time.sleep(min(rest - 0.002, 0.05))
            while time.perf_counter() < close_at:
                pass
            send_cc(out, a.cc, 127, a.channel)
            if a.release:
                send_cc(out, a.cc, 0, a.channel)
            print("Schließ-CC gesendet")
        time.sleep(max(0.0, target + dur + 0.5 - time.perf_counter()))
    inp.close()
    print("Fertig. Jetzt Spur am Gerät prüfen, dann für 'xcorr' in den STORAGE-Modus wechseln.")


def beat_offsets(ref, rec, bpm: float):
    """Versatz pro Schlag (Frames, + = Aufnahme später). Schlag 1 wird übersprungen,
    weil er bei zu frühem Audio am Loop-Anfang abgeschnitten wird."""
    import numpy as np
    beat = 60.0 / bpm * SR
    half = int(beat / 2)
    n_beats = int(round(len(ref) / beat))
    out = []
    for k in range(1, n_beats):
        c = int(round(k * beat))
        lo, hi = c - half, c + half
        if lo < 0 or hi > len(ref) or hi > len(rec):
            continue
        r, x = ref[lo:hi], rec[lo:hi]
        n = 1 << int(np.ceil(np.log2(2 * len(r))))
        cc = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(r, n)), n)
        lag = int(np.argmax(cc))
        if lag > n // 2:
            lag -= n
        if abs(lag) < half:
            out.append(lag)
    return out


def cmd_xcorr(a):
    import numpy as np
    ref = read_any_wav(a.ref).mean(axis=1)
    rec = read_any_wav(a.rec).mean(axis=1)
    print(f"Längen: ref={len(ref)} rec={len(rec)} Frames (Δ {len(rec) - len(ref):+d})")
    bpm = a.bpm
    if bpm is None:  # aus der Click-Länge schätzen: ganze Takte à 4 Schläge
        for bars in range(1, 17):
            cand = bars * 4 * 60 * SR / len(ref)
            if 40 <= cand <= 250:
                bpm = cand
                break
    lags = beat_offsets(ref, rec, bpm)
    if not lags:
        sys.exit("Keine Schläge auswertbar – passt die Aufnahme zur Click-Datei?")
    med = float(np.median(lags))
    print(f"Tempo (aus Click-Länge): {bpm:.2f} BPM, ausgewertet: Schläge 2–{len(lags) + 1}")
    print("Pro Schlag: " + ", ".join(f"{l:+d}" for l in lags) + " Frames")
    print(f"Versatz: {med:+.0f} Frames = {med / SR * 1000:+.2f} ms "
          f"({'Aufnahme kommt zu spät' if med > 0 else 'Aufnahme kommt zu früh' if med < 0 else 'exakt'}), "
          f"Streuung innerhalb der Aufnahme {(max(lags) - min(lags)) / SR * 1000:.2f} ms")
    print(f"→ nächster Versuch mit --offset-ms {-med / SR * 1000:.2f} (relativ zum bisherigen Wert)")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", default=PORT_HINT, help="Teilstring des MIDI-Portnamens")
    p.add_argument("--channel", type=int, default=0, help="MIDI-Kanal 0–15 (Standard 0 = Kanal 1)")
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("list")
    c = s.add_parser("clock"); c.add_argument("--seconds", type=float, default=20)
    c = s.add_parser("cc"); c.add_argument("--cc", type=int, required=True)
    c.add_argument("--value", type=int, default=127); c.add_argument("--release", action="store_true")
    c = s.add_parser("click"); c.add_argument("--bpm", type=float, required=True)
    c.add_argument("--bars", type=int, default=1); c.add_argument("--out", default="click.wav")
    c = s.add_parser("drop"); c.add_argument("--wav", required=True); c.add_argument("--cc", type=int, required=True)
    c.add_argument("--device", default=None, help="Index oder Name aus 'list'")
    c.add_argument("--ch0", type=int, default=0, help="erster Ausgangskanal (0 = USB 1/2)")
    c.add_argument("--latency", default="low"); c.add_argument("--offset-ms", type=float, default=0.0)
    c.add_argument("--close-cc", action="store_true", help="Aufnahme per 2. CC schließen (Fallback)")
    c.add_argument("--cc-lead-ms", type=float, default=0.0,
                   help="REC-CC so viele ms vor dem Downbeat senden (z. B. 30 bei QUANTIZE=MEASURE)")
    c.add_argument("--release", action="store_true", help="nach jedem CC sofort Wert 0 senden (MOMENT-Assigns)")
    c = s.add_parser("xcorr"); c.add_argument("--ref", required=True); c.add_argument("--rec", required=True)
    c.add_argument("--bpm", type=float, default=None, help="Tempo des Clicks (Standard: aus der Länge geschätzt)")
    a = p.parse_args(argv)
    if getattr(a, "device", None) is not None and str(a.device).isdigit():
        a.device = int(a.device)
    {"list": cmd_list, "clock": cmd_clock, "cc": cmd_cc, "click": cmd_click,
     "drop": cmd_drop, "xcorr": cmd_xcorr}[a.cmd](a)


if __name__ == "__main__":
    main()
