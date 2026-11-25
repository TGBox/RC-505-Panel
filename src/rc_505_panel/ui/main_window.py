"""Hauptfenster: Top-Bar, Datei-Browser, 5 Spuren, Protokoll.

Die Qt-Schicht ist bewusst dünn: Logik steckt in storage/, audio/, live/ und core/ (getestet).
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QDir, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QSplitter, QTreeView, QVBoxLayout, QWidget,
)

try:  # Qt 6: QFileSystemModel liegt in QtGui
    from PySide6.QtGui import QFileSystemModel
except ImportError:  # pragma: no cover
    from PySide6.QtWidgets import QFileSystemModel

from ..core.actions import DEFAULT_KEYS, Action, ActionBus
from ..core.config import Settings
from ..core.device_watch import DeviceStatus, detect
from ..core.models import DeviceMode, TrackRef
from .track_strip import AUDIO_EXT, TrackStrip
from .workers import run_in_background


class _Bridge(QObject):
    """Bringt Zustandsmeldungen aus dem Drop-Thread sicher in den UI-Thread."""
    drop_state = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RC-505 Panel")
        self.resize(1280, 760)
        self.settings = Settings.load()
        self.bus = ActionBus()
        self.bus.subscribe(self._on_action)
        self.status = DeviceStatus(DeviceMode.OFFLINE)
        self.midi = None
        self.audio = None
        self.engine = None
        self.slots: dict[int, tuple] = {}          # Spur -> (Samples, Beschreibung)
        self.pending_calibration: tuple[int, int, float] | None = None   # (Memory, Spur, BPM)
        self._last_measured: str | None = None                            # Hash der zuletzt gemessenen WAV
        self._bridge = _Bridge()
        self._bridge.drop_state.connect(self._on_drop_state)
        self._build()
        self._bind_keys()

        self.watch = QTimer(self)
        self.watch.setInterval(1000)
        self.watch.timeout.connect(self._poll_device)
        self.watch.start()
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(250)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start()
        self._poll_device()
        from ..audio.stretch import rubberband_available
        self.log("Stretch: " + ("Rubber Band gefunden" if rubberband_available()
                                else "WSOLA (Rubber Band nicht im PATH – klingt schlechter, siehe ADR-0004)"))
        self.log(f"Einstellungen: Offset {self.settings.live.offset_ms:+.1f} ms, "
                 f"Ausgang „{self.settings.live.audio_device}“")

    # ---------- Aufbau ----------

    def _build(self) -> None:
        top = QFrame()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        self.badge = QLabel("OFFLINE")
        self.badge.setObjectName("ModeBadge")
        self.mem = QSpinBox()
        self.mem.setRange(1, 99)
        self.mem.setPrefix("Memory ")
        self.mem.setValue(98)
        self.mem.valueChanged.connect(self._on_memory_changed)
        self.mem_name = QLabel("")
        self.mem_name.setObjectName("Muted")
        self.bpm = QDoubleSpinBox()
        self.bpm.setDecimals(1)
        self.bpm.setRange(40.0, 250.0)
        self.bpm.setSingleStep(0.1)
        self.bpm.setSuffix(" BPM")
        self.bpm.setValue(120.0)
        self.bpm.setToolTip("Tempo des Memory – darauf werden Samples gestreckt")
        self.clock = QLabel("Clock: –")
        self.clock.setObjectName("Muted")
        self.offset = QDoubleSpinBox()
        self.offset.setDecimals(1)
        self.offset.setRange(-500.0, 500.0)
        self.offset.setSingleStep(0.5)
        self.offset.setPrefix("Offset ")
        self.offset.setSuffix(" ms")
        self.offset.setValue(self.settings.live.offset_ms)
        self.offset.setToolTip("Kalibrier-Offset: um so viel wird das Audio gegenüber dem Taktanfang verschoben "
                               "(S1: −52 ms bei WASAPI)")
        self.offset.editingFinished.connect(self._offset_edited)
        self.close_cc = QCheckBox("Loop-Schluss per CC")
        self.close_cc.setChecked(self.settings.live.close_by_cc)
        self.close_cc.setToolTip("Aus (Standard, ADR-0002): Das Gerät schließt über MEASURE der Spur – "
                                 "MEASURE muss der Taktzahl des Samples entsprechen.\n"
                                 "An: Das Tool sendet am Ende einen zweiten REC/PLAY-CC – dann MEASURE = AUTO/FREE.")
        self.close_cc.toggled.connect(self._close_cc_toggled)
        self.btn_cal = QPushButton("Kalibrieren …")
        self.btn_cal.clicked.connect(lambda: self.bus.dispatch(Action("calibrate")))
        self.btn_measure = QPushButton("Kalibrierung messen")
        self.btn_measure.clicked.connect(self._measure_calibration)
        self.btn_backup = QPushButton("Backup")
        self.btn_backup.clicked.connect(self._backup)
        for w in (self.badge, self.mem, self.mem_name, self.bpm, self.clock, self.offset, self.close_cc):
            tl.addWidget(w)
        tl.addStretch()
        for w in (self.btn_cal, self.btn_measure, self.btn_backup):
            tl.addWidget(w)

        self.strips = {t: TrackStrip(t) for t in range(1, 6)}
        tracks = QWidget()
        trl = QHBoxLayout(tracks)
        trl.setContentsMargins(0, 0, 0, 0)
        for s in self.strips.values():
            s.file_dropped.connect(self._on_file_dropped)
            s.action.connect(self.bus.dispatch)
            trl.addWidget(s)

        self.fs = QFileSystemModel(self)
        music = Path.home() / "Music"
        root = str(music if music.is_dir() else Path.home())
        self.fs.setRootPath(root)
        self.fs.setNameFilters([f"*{e}" for e in sorted(AUDIO_EXT)])
        self.fs.setNameFilterDisables(False)
        self.fs.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.tree = QTreeView()
        self.tree.setModel(self.fs)
        self.tree.setRootIndex(self.fs.index(root))
        self.tree.setDragEnabled(True)
        for col in (1, 2, 3):
            self.tree.hideColumn(col)
        self.tree.setHeaderHidden(True)

        self.logview = QPlainTextEdit()
        self.logview.setReadOnly(True)
        self.logview.setMaximumBlockCount(500)

        center = QSplitter(Qt.Orientation.Vertical)
        center.addWidget(tracks)
        center.addWidget(self.logview)
        center.setSizes([560, 160])
        main = QSplitter(Qt.Orientation.Horizontal)
        main.addWidget(self.tree)
        main.addWidget(center)
        main.setSizes([260, 1020])

        root_w = QWidget()
        lay = QVBoxLayout(root_w)
        lay.addWidget(top)
        lay.addWidget(main, 1)
        self.setCentralWidget(root_w)

    def _bind_keys(self) -> None:
        for seq, action in DEFAULT_KEYS.items():
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(lambda a=action: self.bus.dispatch(a))

    def log(self, text: str) -> None:
        self.logview.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")

    # ---------- Gerätemodus ----------

    def _poll_device(self) -> None:
        st = detect(self.settings.live.midi_port_hint)
        if st == self.status:
            return
        old, self.status = self.status, st
        self.badge.setText(st.label)
        self.badge.setProperty("mode", st.mode.name)
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)
        self.log(f"Gerät: {st.label}")
        if old.mode is DeviceMode.LIVE:
            self._close_live()
        for s in self.strips.values():
            s.set_mode(st.mode)
        self.slots.clear()
        if st.mode is DeviceMode.LIVE:
            self._open_live()
        elif st.mode is DeviceMode.STORAGE:
            self._load_memory()
        self.btn_cal.setEnabled(st.mode is DeviceMode.LIVE)
        self.btn_measure.setEnabled(st.mode is DeviceMode.STORAGE and self.pending_calibration is not None)
        self.btn_backup.setEnabled(st.mode is DeviceMode.STORAGE)

    def _open_live(self) -> None:
        from ..live.autodrop import AutoDropEngine
        from ..live.midi import MidiLink
        s = self.settings.live
        try:
            self.midi = MidiLink(s.midi_port_hint, s.midi_channel)
        except Exception as e:  # noqa: BLE001
            self.log(f"MIDI konnte nicht geöffnet werden: {e}")
            return
        try:
            from ..live.audio_out import AudioOut
            self.audio = AudioOut(s.audio_device)
            self.log(f"Audio: Gerät {self.audio.device}, Latenz {self.audio.latency_ms:.1f} ms")
        except Exception as e:  # noqa: BLE001
            self.audio = None
            self.log(f"Audio-Ausgang „{s.audio_device}“ nicht verfügbar ({e}) – nur MIDI-Steuerung möglich")
        if self.audio:
            self.engine = AutoDropEngine(self.midi, self.audio, s, on_state=self._bridge.drop_state.emit)
        for s_ in self.strips.values():
            s_.set_content("Live – Inhalt unbekannt")

    def _close_live(self) -> None:
        for obj in (self.audio, self.midi):
            if obj:
                try:
                    obj.close()
                except Exception:  # noqa: BLE001
                    pass
        self.midi = self.audio = self.engine = None

    def _update_clock(self) -> None:
        if not self.midi:
            self.clock.setText("Clock: –")
            return
        c = self.midi.clock
        if not c.ready:
            self.clock.setText("Clock: wartet auf START" if c.orphan_ticks else "Clock: steht")
            return
        bpm = c.bpm or 0
        warn = "  ⚠ ≠ Memory-Tempo" if abs(bpm - self.bpm.value()) / self.bpm.value() > 0.005 else ""
        self.clock.setText(f"Clock: {bpm:.2f} BPM · Takt {c.tick // 96 + 1}{warn}")

    # ---------- Memory (Storage) ----------

    def _on_memory_changed(self, mem: int) -> None:
        if self.status.mode is DeviceMode.STORAGE:
            self._load_memory()
        elif self.status.mode is DeviceMode.LIVE and self.midi:
            self.midi.program_change(mem)
            self.slots.clear()
            for s in self.strips.values():
                s.set_slot(None)
            self.log(f"Memory {mem:03d} per Program Change gewählt")

    def _load_memory(self) -> None:
        from ..storage.rc0 import Rc0Document
        from ..storage.rc0_schema import guess_memory_tempo, track_info
        if not self.status.roland:
            return
        try:
            doc = Rc0Document.load(self.status.roland / "DATA", self.mem.value())
        except Exception as e:  # noqa: BLE001
            self.log(f"Memory {self.mem.value():03d} nicht lesbar: {e}")
            return
        self.mem_name.setText(f"„{doc.name()}“")
        tempo = guess_memory_tempo(doc)
        if tempo:
            self.bpm.setValue(tempo)
        for n, s in self.strips.items():
            i = track_info(doc, n)
            s.set_content(f"{i.bars:g} Takt(e) @ {i.tempo:g} BPM" if i.has_data else "leer")

    # ---------- Datei auf Spur ----------

    def _on_file_dropped(self, track: int, path: str) -> None:
        mode, bpm, name = self.status.mode, self.bpm.value(), Path(path).name
        strip = self.strips[track]
        if mode is DeviceMode.STORAGE:
            from ..storage.track_import import import_file
            ref = TrackRef(self.mem.value(), track)
            roland = self.status.roland
            strip.set_state("ARMED", f"Schreibe {name} …")
            self.log(f"Import {name} → Memory {ref.memory:03d} Spur {track} @ {bpm:g} BPM")

            def done(res):
                t = res.tempo
                strip.set_state("DONE", f"{res.bars} Takt(e) geschrieben")
                self.log(f"  Quelle {t.bpm:.2f} BPM ({t.source}) → {res.bars} Takt(e), Backup: {res.backup_dir}")
                self.log("  Am Gerät trennen, Memory wechseln und zurück – dann ist die Spur geladen.")
                self._load_memory()
            run_in_background(lambda: import_file(roland, ref, Path(path), bpm),
                              done, lambda e: self._failed(track, e))
        elif mode is DeviceMode.LIVE:
            from ..audio.rcwav import read_rc_wav
            from ..audio.stretch import render_file
            strip.set_slot(f"Rendere {name} …")

            def render():
                clip, est = render_file(Path(path), bpm)
                return read_rc_wav(clip.path), clip, est

            def done(res):
                samples, clip, est = res
                desc = f"{name}: {clip.bars} Takt(e) @ {bpm:g} (Quelle {est.bpm:.1f}, {est.source})"
                self.slots[track] = (samples, desc)
                strip.set_slot(desc, ready=True)
                self.log(f"Slot Spur {track} bereit – {desc}. Auslösen mit DROP oder F{track}.")
            run_in_background(render, done, lambda e: self._failed(track, e))

    def _failed(self, track: int, err: str) -> None:
        self.strips[track].set_state("FAILED", err)
        self.log(f"Fehler Spur {track}: {err}")

    # ---------- Aktionen (Buttons, Tasten) ----------

    def _on_action(self, a: Action) -> None:
        if self.status.mode is not DeviceMode.LIVE or not self.midi:
            if a.name in ("drop", "rec_play", "stop", "calibrate"):
                self.log("Nur im Live-Modus (USB VENDOR) möglich")
            return
        s = self.settings.live
        if a.name == "rec_play":
            self.midi.cc(s.rec_play_cc[str(a.track)], 127, release=s.release)
        elif a.name == "stop":
            self.midi.cc(s.stop_cc[str(a.track)], 127, release=s.release)
        elif a.name == "drop":
            if a.track not in self.slots:
                self.log(f"Spur {a.track}: kein Sample vorbereitet – Datei auf die Spur ziehen")
                return
            self._start_drop(a.track, self.slots[a.track][0])
        elif a.name == "calibrate":
            self._start_calibration()

    def _offset_edited(self) -> None:
        v = round(self.offset.value(), 2)
        if v != self.settings.live.offset_ms:
            self.settings.live.offset_ms = v
            self.settings.save()
            self.log(f"Offset auf {v:+.1f} ms gesetzt")

    def _close_cc_toggled(self, on: bool) -> None:
        self.settings.live.close_by_cc = on
        self.settings.save()
        self.log("Loop-Schluss: " + ("per CC (Spur-MEASURE = AUTO/FREE)" if on
                                      else "durch das Gerät (Spur-MEASURE = Taktzahl des Samples)"))

    def _start_drop(self, track: int, samples, tag: str = "") -> None:
        if not self.engine:
            self.log("Kein Audio-Ausgang – Drop nicht möglich")
            return
        self.engine.drop(track, samples, tag=tag)
        if not self.midi.clock.ready:
            self.log("Warte auf Clock – am Gerät STOP und dann ALL START drücken")

    def _on_drop_state(self, job) -> None:
        from ..live.autodrop import DropState
        strip = self.strips[job.track]
        texts = {
            DropState.WAITING_CLOCK: "wartet auf Clock …",
            DropState.ARMED: (f"scharf: Takt {job.plan.target_tick // 96 + 1}, Jitter {job.plan.jitter_ms:.1f} ms"
                              if job.plan else "scharf"),
            DropState.RECORDING: f"nimmt auf (CC {job.cc_early_ms:.1f} ms vorher)" if job.cc_early_ms else "nimmt auf",
            DropState.DONE: ("fertig – Spur spielt" if job.audio_played is not False
                             else "fertig, aber das Audio wurde NICHT abgespielt (Ausgabe prüfen)"),
            DropState.FAILED: f"Fehler: {job.error}",
            DropState.CANCELLED: "abgebrochen",
        }
        strip.set_state(job.state.name, texts[job.state])
        if job.state in (DropState.DONE, DropState.FAILED, DropState.CANCELLED):
            self.log(f"Drop Spur {job.track}: {texts[job.state]}")
            if job.state is DropState.DONE and job.tag == "calibration":
                self.log("Kalibrier-Click gedroppt. Prüfen: Läuft auf der Spur ein Click (Rhythmus aus)? "
                         "Dann WRITE, STORAGE → CONNECT und „Kalibrierung messen“ klicken.")

    # ---------- Kalibrierung ----------

    def _start_calibration(self) -> None:
        from ..live.calibrate import make_click
        track = 1
        bpm = self.bpm.value()
        r = QMessageBox.question(
            self, "Kalibrieren",
            f"Ein 1-Takt-Click wird bei {bpm:g} BPM auf Spur {track} gedroppt.\n\n"
            f"Voraussetzung: Spur {track} leer, MEASURE = 1, INPUT nur INST2, REC QUANTIZE = MEASURE.\n"
            "Nach dem Start am Gerät STOP und dann ALL START drücken.")
        if r != QMessageBox.StandardButton.Yes:
            return
        self.pending_calibration = (self.mem.value(), track, bpm)
        self._start_drop(track, make_click(bpm, 1), tag="calibration")

    def _measure_calibration(self) -> None:
        if not (self.pending_calibration and self.status.roland):
            return
        from ..audio.rcwav import read_rc_wav
        from ..live.calibrate import make_click, measure
        import hashlib
        mem, track, bpm = self.pending_calibration
        wav = self.status.roland / "WAVE" / f"{mem:03d}_{track}" / f"{mem:03d}_{track}.WAV"
        try:
            digest = hashlib.sha1(wav.read_bytes()).hexdigest()
            if digest == self._last_measured:
                raise ValueError("Die Datei ist unverändert seit der letzten Messung – nach dem Drop WRITE vergessen?")
            m = measure(make_click(bpm, 1), read_rc_wav(wav), bpm)
        except Exception as e:  # noqa: BLE001
            self.log(f"Messung fehlgeschlagen: {e}")
            QMessageBox.warning(self, "Kalibrierung", str(e))
            return
        self._last_measured = digest
        if not m.valid:
            self.log(f"Messung verworfen: {m.problem}")
            QMessageBox.warning(self, "Kalibrierung", f"Messung verworfen:\n{m.problem}\n\nDer Offset bleibt unverändert.")
            return
        cur = self.settings.live.offset_ms
        new = m.suggested_offset(cur)
        self.log(f"Kalibrierung: pro Schlag {m.per_beat_frames} Frames, Versatz {m.offset_ms:+.2f} ms, "
                 f"Längen-Δ {m.length_delta:+d}")
        r = QMessageBox.question(self, "Kalibrierung",
                                 f"Versatz {m.offset_ms:+.2f} ms (Streuung {m.spread_ms:.2f} ms).\n\n"
                                 f"Offset {cur:+.2f} ms → {new:+.2f} ms übernehmen?")
        if r == QMessageBox.StandardButton.Yes:
            self.settings.live.offset_ms = new
            self.offset.setValue(new)
            self.log(f"Offset gespeichert: {new:+.2f} ms ({self.settings.save()})")

    # ---------- Backup ----------

    def _backup(self) -> None:
        if not self.status.roland:
            return
        from ..storage.backup import backup_memory
        mem = self.mem.value()
        run_in_background(lambda: backup_memory(self.status.roland, mem, label="manuell"),
                          lambda p: self.log(f"Backup Memory {mem:03d}: {p}"),
                          lambda e: self.log(f"Backup fehlgeschlagen: {e}"))

    def closeEvent(self, event) -> None:
        self._close_live()
        super().closeEvent(event)
