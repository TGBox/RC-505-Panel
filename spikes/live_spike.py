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
        self.lock = threading.Lock()

    def feed(self, msg_type: str, t: float | None = None) -> None:
        t = self.now() if t is None else t
        with self.lock:
            if msg_type == "start":
                self.running, self.tick, self.last_tick_time = True, 0, None
                self.intervals.clear()
            elif msg_type == "stop":
                self.running = False
            elif msg_type == "continue":
                self.running = True
            elif msg_type == "clock" and self.running:
                if self.last_tick_time is not None:
                    self.intervals.append(t - self.last_tick_time)
                    self.intervals = self.intervals[-PPQN * 2:]
                    self.tick += 1
                self.last_tick_time = t

    @property
    def tick_interval(self) -> float | None:
        with self.lock:
            return sum(self.intervals) / len(self.intervals) if len(self.intervals) >= PPQN else None

    @property
    def bpm(self) -> float | None:
        ti = self.tick_interval
        return 60.0 / (ti * PPQN) if ti else None

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
    import numpy as np
    import sounddevice as sd

    clip = read_any_wav(a.wav)
    f = ClockFollower()
    out, inp = open_midi(a.port, f)
    print("Warte auf laufende Clock… (ALL START am Gerät, falls noch nicht gestartet)")
    while f.next_downbeat() is None:
        time.sleep(0.05)
    print(f"Clock läuft: {f.bpm:.2f} BPM")

    # Ziel: übernächster Downbeat (genug Vorlauf für Stream-Start)
    target = f.next_downbeat()
    if target - time.perf_counter() < 0.5:
        target += TICKS_PER_BAR * f.tick_interval
    audio_target = target + a.offset_ms / 1000.0

    pos = {"i": None}
    clock_map = {}  # Zuordnung Stream-Zeit -> perf_counter, beim ersten Callback

    def callback(outdata, frames, tinfo, status):
        if status:
            print("Audio-Status:", status, file=sys.stderr)
        if "delta" not in clock_map:
            clock_map["delta"] = time.perf_counter() - tinfo.currentTime
        outdata.fill(0)
        dac = tinfo.outputBufferDacTime + clock_map["delta"]  # perf_counter-Zeit des 1. Samples
        if pos["i"] is None:
            start = round((audio_target - dac) * SR)
            if start >= frames:
                return
            pos["i"] = -start  # negativ = Startoffset innerhalb dieses Puffers
        i = pos["i"]
        dst0 = max(0, -i)
        src0 = max(0, i)
        n = min(frames - dst0, len(clip) - src0)
        if n > 0:
            outdata[dst0:dst0 + n, a.ch0:a.ch0 + 2] = clip[src0:src0 + n]
        pos["i"] = i + frames
        if src0 + n >= len(clip):
            raise sd.CallbackStop

    nch = a.ch0 + 2
    with sd.OutputStream(device=a.device, samplerate=SR, channels=nch, dtype="float32",
                         latency=a.latency, callback=callback) as stream:
        print(f"Stream-Latenz laut PortAudio: {stream.latency * 1000:.1f} ms")
        # CC zum Downbeat senden, optional früher (bei REC QUANTIZE = MEASURE nötig,
        # sonst wartet das Gerät bei minimaler Verspätung einen ganzen Takt)
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


def cmd_xcorr(a):
    import numpy as np
    ref = read_any_wav(a.ref).mean(axis=1)
    rec = read_any_wav(a.rec).mean(axis=1)
    # Loops sind zyklisch: zirkuläre Kreuzkorrelation über die Länge der Aufnahme
    L = len(rec)
    ref_l = np.zeros(L, dtype=ref.dtype)
    ref_l[: min(L, len(ref))] = ref[:L]
    c = np.fft.irfft(np.fft.rfft(rec) * np.conj(np.fft.rfft(ref_l)), L)
    lag = int(np.argmax(c))
    lag = ((lag + L // 2) % L) - L // 2  # auf ±halbe Loop-Länge abbilden
    print(f"Längen: ref={len(ref)} rec={len(rec)} Frames (Δ {len(rec) - len(ref):+d})")
    print(f"Versatz: {lag:+d} Frames = {lag / SR * 1000:+.2f} ms "
          f"({'Aufnahme kommt zu spät' if lag > 0 else 'Aufnahme kommt zu früh' if lag < 0 else 'exakt'})")
    print(f"→ nächster Versuch mit --offset-ms {-lag / SR * 1000:.2f} (relativ zum bisherigen Wert)")


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
    a = p.parse_args(argv)
    if getattr(a, "device", None) is not None and str(a.device).isdigit():
        a.device = int(a.device)
    {"list": cmd_list, "clock": cmd_clock, "cc": cmd_cc, "click": cmd_click,
     "drop": cmd_drop, "xcorr": cmd_xcorr}[a.cmd](a)


if __name__ == "__main__":
    main()
