"""Auto-Drop: ein gerendertes Sample taktgenau auf eine Spur der laufenden RC-505mkII legen (C11).

Ablauf (validiert in Spike S1, ADR-0002/0006):
  1. Warten, bis die MIDI-Clock seit einem START läuft.
  2. Ziel = nächster Taktanfang mit genug Vorlauf; Zeit per Ausgleichsgerade über die Ticks.
  3. Audio über INST2 so planen, dass es um `offset_ms` (Kalibrierung) versetzt am Gerät ankommt;
     die Zielzeit wird bis kurz vor Audiostart nachgeschärft.
  4. REC/PLAY-CC `cc_lead_ms` vor dem Taktanfang (REC QUANTIZE = MEASURE fängt ihn auf den Takt).
  5. Das Gerät beendet die Aufnahme über MEASURE selbst; optional (Fallback) zweiter CC.
Ein START/STOP am Gerät während der Wartezeit bricht den Drop ab (sonst landet er 1–2 Schläge daneben).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np

from ..core.config import LiveSettings
from ..core.models import SR
from .clock import PPQN


class DropState(Enum):
    WAITING_CLOCK = auto()
    ARMED = auto()
    RECORDING = auto()
    DONE = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class DropPlan:
    target_tick: int
    target_time: float     # perf_counter-Zeit des Taktanfangs
    audio_at: float
    cc_at: float
    jitter_ms: float
    bpm: float


@dataclass
class DropJob:
    track: int
    frames: int
    state: DropState = DropState.WAITING_CLOCK
    plan: DropPlan | None = None
    cc_early_ms: float | None = None        # tatsächlicher Vorlauf des REC-CC
    audio_played: bool | None = None        # hat die Audio-Ausgabe den Clip vollständig abgespielt?
    tag: str = ""                           # frei für die UI, z. B. "calibration"
    error: str | None = None
    finished: threading.Event = field(default_factory=threading.Event)
    _cancel: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> "DropJob":
        self.finished.wait(timeout)
        return self


class DropAborted(Exception):
    pass


class AutoDropEngine:
    def __init__(self, midi, audio, settings: LiveSettings | None = None,
                 on_state: Callable[[DropJob], None] | None = None,
                 now: Callable[[], float] = time.perf_counter,
                 min_lead_s: float = 0.8, freeze_s: float = 0.15, clock_timeout_s: float = 15.0) -> None:
        self.midi = midi                 # .cc(control, value, release), .clock (ClockFollower)
        self.audio = audio               # .play_at(clip, at), .retime(at), .cancel()
        self.s = settings or LiveSettings()
        self.on_state = on_state
        self._now = now
        self.min_lead_s = min_lead_s
        self.freeze_s = freeze_s
        self.clock_timeout_s = clock_timeout_s
        self._busy = threading.Lock()

    # ---------- öffentlich ----------

    def drop(self, track: int, clip: np.ndarray, block: bool = False, tag: str = "") -> DropJob:
        if str(track) not in self.s.rec_play_cc:
            raise ValueError(f"Keine REC/PLAY-CC für Spur {track} konfiguriert")
        job = DropJob(track, len(clip), tag=tag)
        th = threading.Thread(target=self._run, args=(job, np.ascontiguousarray(clip, np.float32)),
                              name=f"autodrop-{track}", daemon=True)
        th.start()
        if block:
            job.wait()
        return job

    # ---------- intern ----------

    def _set(self, job: DropJob, state: DropState, error: str | None = None) -> None:
        job.state, job.error = state, error
        if self.on_state:
            self.on_state(job)
        if state in (DropState.DONE, DropState.FAILED, DropState.CANCELLED):
            job.finished.set()

    def _sleep_until(self, t: float, job: DropJob, check: Callable[[], None]) -> None:
        """Grob schlafen, die letzten ms aktiv warten; `check` darf DropAborted werfen."""
        while (rest := t - self._now()) > 0.003:
            check()
            if job._cancel.is_set():
                raise DropAborted("abgebrochen")
            time.sleep(min(rest - 0.002, 0.01))
        while self._now() < t:
            pass

    def _run(self, job: DropJob, clip: np.ndarray) -> None:
        if not self._busy.acquire(blocking=False):
            self._set(job, DropState.FAILED, "Es läuft bereits ein Drop")
            return
        clock = self.midi.clock
        try:
            self._set(job, DropState.WAITING_CLOCK)
            deadline = self._now() + self.clock_timeout_s
            while not clock.ready:
                if job._cancel.is_set():
                    raise DropAborted("abgebrochen")
                if self._now() > deadline:
                    hint = (" Die Clock läuft, aber START kam vor dem Drop – am Gerät STOP und dann ALL START."
                            if clock.orphan_ticks > PPQN else " Am Gerät ALL START drücken (SYNC OUT = ON?).")
                    raise TimeoutError("Keine laufende MIDI-Clock." + hint)
                time.sleep(0.01)

            starts0 = clock.starts

            def check_restart() -> None:
                if clock.starts != starts0 or not clock.running:
                    raise DropAborted("START/STOP am Gerät während der Wartezeit – Taktposition hat sich geändert")

            k = clock.next_bar_tick(self.min_lead_s)
            est = clock.time_of_tick(k) if k is not None else None
            if est is None:
                raise DropAborted("Clock-Schätzung nicht verfügbar")
            off = self.s.offset_ms / 1000
            lead = self.s.cc_lead_ms / 1000
            job.plan = DropPlan(k, est.time, est.time + off, est.time - lead, est.jitter_ms, clock.bpm or 0.0)
            played = self.audio.play_at(clip, job.plan.audio_at)
            self._set(job, DropState.ARMED)

            # Zielzeit nachschärfen, bis kurz vor dem Audiostart bzw. dem CC
            while True:
                check_restart()
                if job._cancel.is_set():
                    raise DropAborted("abgebrochen")
                est = clock.time_of_tick(k)
                audio_at, cc_at = est.time + off, est.time - lead
                if min(audio_at, cc_at) - self._now() < self.freeze_s:
                    break
                job.plan.target_time, job.plan.audio_at, job.plan.cc_at = est.time, audio_at, cc_at
                job.plan.jitter_ms = est.jitter_ms
                self.audio.retime(audio_at)
                time.sleep(0.01)

            rec_cc = self.s.rec_play_cc[str(job.track)]
            self._sleep_until(job.plan.cc_at, job, check_restart)
            self.midi.cc(rec_cc, 127, release=self.s.release)
            job.cc_early_ms = (job.plan.target_time - self._now()) * 1000
            self._set(job, DropState.RECORDING)

            end = job.plan.target_time + len(clip) / SR
            if self.s.close_by_cc:   # Fallback zu ADR-0002; mit QUANTIZE = MEASURE ebenfalls etwas früher
                self._sleep_until(end - lead, job, lambda: None)
                self.midi.cc(rec_cc, 127, release=self.s.release)
            while self._now() < end + 0.2:
                if job._cancel.is_set():
                    raise DropAborted("abgebrochen")
                time.sleep(0.02)
            job.audio_played = bool(played.wait(0.5)) if played is not None else None
            self._set(job, DropState.DONE)
        except DropAborted as e:
            self.audio.cancel()
            self._set(job, DropState.CANCELLED if str(e) == "abgebrochen" else DropState.FAILED, str(e))
        except Exception as e:  # noqa: BLE001 – Fehler gehen an die UI, nicht in den Thread-Tod
            self.audio.cancel()
            self._set(job, DropState.FAILED, str(e))
        finally:
            self._busy.release()
