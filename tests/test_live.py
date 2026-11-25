"""Live-Kern gegen eine simulierte RC-505mkII (Clock mit Jitter, Audio mit verspäteten Callbacks)."""
import random
import sys
import threading
import time
import types

import numpy as np
import pytest

from rc_505_panel.core.config import LiveSettings, Settings
from rc_505_panel.core.models import SR, loop_frames
from rc_505_panel.live.autodrop import AutoDropEngine, DropState
from rc_505_panel.live.calibrate import make_click, measure
from rc_505_panel.live.clock import PPQN, TICKS_PER_BAR, ClockFollower

BPM = 180.0                      # schnell, damit die Tests kurz bleiben
TICK = 60 / BPM / PPQN


# ---------- ClockFollower ----------

def test_clock_fit_and_prediction():
    rng = random.Random(1)
    c = ClockFollower(now=lambda: 0.0)
    t0 = 10.0
    c.feed("start", t0)
    for k in range(150):
        c.feed("clock", t0 + k * TICK + abs(rng.gauss(0, 0.0008)))
    assert c.tick == 149 and c.ready
    assert abs(c.bpm - BPM) < 0.05
    est = c.time_of_tick(2 * TICKS_PER_BAR)
    assert abs(est.time - (t0 + 2 * TICKS_PER_BAR * TICK)) < 0.0015   # ±1,5 ms trotz Jitter
    assert c.next_bar_tick() == 2 * TICKS_PER_BAR


def test_clock_orphans_and_restart():
    c = ClockFollower(now=lambda: 0.0)
    for k in range(50):
        c.feed("clock", k * TICK)
    assert c.orphan_ticks == 50 and not c.ready
    c.feed("start", 5.0)
    c.feed("clock", 5.0)
    assert c.tick == 0 and c.starts == 1
    c.feed("stop", 5.1)
    assert not c.running and not c.ready


# ---------- Kalibrierung ----------

@pytest.mark.parametrize("shift", [-300, -86, 0, 210, 2361])
def test_measure_per_beat(shift):
    ref = make_click(104, 1)
    rec = np.zeros_like(ref)
    if shift >= 0:
        rec[shift:] = ref[: len(ref) - shift]
    else:
        rec[:shift] = ref[-shift:]          # Anfang abgeschnitten wie am Gerät
    m = measure(ref, rec, 104)
    assert m.per_beat_frames == [shift] * 3
    assert abs(m.offset_ms - shift / SR * 1000) < 1e-6 and m.length_delta == 0
    assert m.suggested_offset(-53.5) == round(-53.5 - shift / SR * 1000, 2)
    assert m.valid


def test_measure_rejects_silence_and_garbage():
    ref = make_click(104, 1)
    silent = measure(ref, np.zeros_like(ref), 104)                 # so sah die Aufnahme am 25.11. aus
    assert not silent.valid and "still" in silent.problem
    rng = np.random.default_rng(0)
    noise = measure(ref, rng.standard_normal(ref.shape).astype(np.float32) * 0.1, 104)
    assert not noise.valid
    longer = measure(ref, np.vstack([ref, np.zeros((500, 2), np.float32)]), 104)
    assert not longer.valid and "MEASURE" in longer.problem


def test_settings_roundtrip(tmp_path):
    s = Settings()
    s.live.offset_ms = -51.25
    p = s.save(tmp_path / "settings.json")
    assert Settings.load(p).live.offset_ms == -51.25
    assert Settings.load(tmp_path / "fehlt.json").live.offset_ms == LiveSettings().offset_ms


# ---------- AutoDrop gegen simulierte Geräte ----------

class FakeMidi:
    """Clock-Thread mit Jitter wie über USB; protokolliert gesendete CCs."""

    def __init__(self, start_delay=0.05, restart_after=None, jitter=0.0008):
        self.clock = ClockFollower()
        self.sent: list[tuple[float, int, int]] = []
        self.t0 = time.perf_counter() + start_delay
        self._stop = False
        self._restart_after = restart_after
        self._jitter = jitter
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        rng = random.Random(7)
        while time.perf_counter() < self.t0:
            time.sleep(0.001)
        self.clock.feed("start")
        k = 0
        while not self._stop and k < 40 * TICKS_PER_BAR:
            due = self.t0 + k * TICK
            while time.perf_counter() < due:
                time.sleep(0.0003)
            time.sleep(abs(rng.gauss(0, self._jitter)))
            if self._restart_after is not None and k == self._restart_after:
                self.clock.feed("stop")
                self.clock.feed("start")
                self.t0, k = time.perf_counter(), 0
                continue
            self.clock.feed("clock")
            k += 1

    def true_bar_time(self, tick):
        return self.t0 + tick * TICK

    def cc(self, control, value, release=False):
        self.sent.append((time.perf_counter(), control, value))
        if release:
            self.sent.append((time.perf_counter(), control, 0))

    def close(self):
        self._stop = True


class FakeAudio:
    def __init__(self):
        self.at = None
        self.cancelled = False

    def play_at(self, clip, at):
        self.at = at
        return threading.Event()

    def retime(self, at):
        self.at = at

    def cancel(self):
        self.cancelled = True


def engine(midi, audio, **kw):
    s = LiveSettings(offset_ms=-52.0, cc_lead_ms=30.0, release=True)
    return AutoDropEngine(midi, audio, s, min_lead_s=0.3, **kw)


def test_drop_timing_and_states():
    midi, audio = FakeMidi(), FakeAudio()
    states = []
    clip = np.zeros((loop_frames(BPM, 1), 2), np.float32)
    job = engine(midi, audio, on_state=lambda j: states.append(j.state)).drop(3, clip, block=True)
    midi.close()
    assert job.state == DropState.DONE, job.error
    assert states == [DropState.WAITING_CLOCK, DropState.ARMED, DropState.RECORDING, DropState.DONE]
    true_t = midi.true_bar_time(job.plan.target_tick)
    assert job.plan.target_tick % TICKS_PER_BAR == 0
    assert abs(audio.at - (true_t - 0.052)) < 0.0015          # Audio: Kalibrier-Offset, ±1,5 ms
    rec = [s for s in midi.sent if s[1] == 23]                 # Spur 3 → CC#23
    assert [v for _, _, v in rec] == [127, 0]                  # nur REC, kein Schließ-CC (ADR-0002)
    assert 0.025 < true_t - rec[0][0] < 0.035                  # CC ~30 ms vor dem Taktanfang


def test_close_by_cc_is_sent_early():
    midi, audio = FakeMidi(), FakeAudio()
    s = LiveSettings(offset_ms=-52.0, cc_lead_ms=30.0, release=False, close_by_cc=True)
    clip = np.zeros((loop_frames(BPM, 1), 2), np.float32)
    job = AutoDropEngine(midi, audio, s, min_lead_s=0.3).drop(2, clip, block=True)
    midi.close()
    assert job.state == DropState.DONE, job.error
    sends = [ts for ts, c, v in midi.sent if c == 22 and v == 127]
    assert len(sends) == 2
    end = midi.true_bar_time(job.plan.target_tick) + len(clip) / SR
    assert 0.025 < end - sends[1] < 0.035                       # Schließ-CC ~30 ms vor Taktende


def test_drop_aborts_on_restart():
    midi, audio = FakeMidi(restart_after=PPQN * 3), FakeAudio()   # Neustart nach 3 Schlägen
    clip = np.zeros((1000, 2), np.float32)
    job = engine(midi, audio).drop(1, clip, block=True)
    midi.close()
    assert job.state == DropState.FAILED and "START/STOP" in job.error
    assert audio.cancelled and not [s for s in midi.sent if s[1] == 21]


def test_drop_times_out_without_clock():
    midi, audio = FakeMidi(start_delay=60), FakeAudio()
    job = engine(midi, audio, clock_timeout_s=0.2).drop(1, np.zeros((10, 2), np.float32), block=True)
    midi.close()
    assert job.state == DropState.FAILED and "Clock" in job.error


def test_drop_cancel_and_busy():
    midi, audio = FakeMidi(), FakeAudio()
    e = engine(midi, audio)
    job1 = e.drop(1, np.zeros((10, 2), np.float32))
    time.sleep(0.05)
    job2 = e.drop(2, np.zeros((10, 2), np.float32), block=True)
    assert job2.state == DropState.FAILED and "bereits" in job2.error
    job1.cancel()
    job1.wait(5)
    midi.close()
    assert job1.state == DropState.CANCELLED and audio.cancelled


# ---------- AudioOut gegen simuliertes sounddevice ----------

@pytest.fixture
def fake_sd(monkeypatch):
    sd = types.ModuleType("sounddevice")
    OFF, LAT = 1234.5, 0.022
    first = {}

    class Info:
        pass

    class Stream:
        def __init__(self, device, samplerate, channels, dtype, latency, callback):
            self.cb, self.latency, self.run = callback, LAT, False

        @property
        def time(self):
            return time.perf_counter() - OFF

        def start(self):
            self.run = True
            threading.Thread(target=self._loop, daemon=True).start()

        def stop(self):
            self.run = False

        def close(self):
            self.run = False

        def _loop(self):
            frames, nxt = 441, time.perf_counter()
            rng = random.Random(3)
            while self.run:
                nxt += frames / SR
                while time.perf_counter() < nxt:
                    time.sleep(0.0005)
                time.sleep(rng.uniform(0, 0.004))               # verspätete Callbacks
                info = Info()
                info.outputBufferDacTime = (nxt - OFF) + LAT
                out = np.zeros((frames, 2), np.float32)
                self.cb(out, frames, info, None)
                nz = np.flatnonzero(np.abs(out).sum(1) > 0)
                if len(nz) and "dac" not in first:
                    first["dac"] = nxt + LAT + nz[0] / SR

    sd.OutputStream = Stream
    sd.query_devices = lambda: [{"name": "INST2 (2- RC-505mk2)", "hostapi": 0, "max_output_channels": 2}]
    sd.query_hostapis = lambda i: {"name": "Windows WASAPI"}
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    return first


def test_audio_out_starts_on_time(fake_sd):
    from rc_505_panel.live.audio_out import AudioOut
    out = AudioOut("RC-505mk2 INST2 WASAPI")
    assert out.device == 0
    at = time.perf_counter() + 0.3
    done = out.play_at(np.ones((2000, 2), np.float32) * 0.5, at)
    assert done.wait(2)
    out.close()
    assert abs(fake_sd["dac"] - at) < 0.0002                   # Sample 0 liegt ±0,2 ms genau an
