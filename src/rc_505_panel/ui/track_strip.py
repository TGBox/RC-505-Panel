"""Ein Kanalzug pro Spur: Status, Drop-Zone für Dateien und die Spur-Tasten."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..core.actions import Action
from ..core.models import DeviceMode

AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".aif", ".aiff"}


class TrackStrip(QFrame):
    file_dropped = Signal(int, str)       # Spur, Pfad
    action = Signal(object)               # Action

    def __init__(self, track: int) -> None:
        super().__init__()
        self.track = track
        self.setObjectName("Track")
        self.setAcceptDrops(True)
        self.setMinimumWidth(170)

        self.title = QLabel(f"SPUR {track}")
        self.title.setObjectName("TrackTitle")
        self.led = QLabel()
        self.led.setObjectName("Led")
        head = QHBoxLayout()
        head.addWidget(self.title)
        head.addStretch()
        head.addWidget(self.led)

        self.content = QLabel("–")
        self.content.setWordWrap(True)
        self.slot = QLabel("")
        self.slot.setObjectName("Muted")
        self.slot.setWordWrap(True)
        self.dropzone = QLabel()
        self.dropzone.setObjectName("Dropzone")
        self.dropzone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dropzone.setWordWrap(True)
        self.dropzone.setMinimumHeight(110)
        self.state = QLabel("")
        self.state.setObjectName("Muted")
        self.state.setWordWrap(True)

        self.btn_drop = QPushButton(f"DROP  (F{track})")
        self.btn_drop.setObjectName("Drop")
        self.btn_rec = QPushButton("● REC/PLAY")
        self.btn_rec.setObjectName("Rec")
        self.btn_stop = QPushButton("■ STOP")
        self.btn_drop.clicked.connect(lambda: self.action.emit(Action("drop", track)))
        self.btn_rec.clicked.connect(lambda: self.action.emit(Action("rec_play", track)))
        self.btn_stop.clicked.connect(lambda: self.action.emit(Action("stop", track)))
        keys = QHBoxLayout()
        keys.addWidget(self.btn_rec)
        keys.addWidget(self.btn_stop)

        lay = QVBoxLayout(self)
        lay.addLayout(head)
        lay.addWidget(self.content)
        lay.addWidget(self.dropzone, 1)
        lay.addWidget(self.slot)
        lay.addWidget(self.btn_drop)
        lay.addLayout(keys)
        lay.addWidget(self.state)
        self.set_mode(DeviceMode.OFFLINE)

    # ---------- Anzeige ----------

    def set_mode(self, mode: DeviceMode) -> None:
        self.mode = mode
        live = mode is DeviceMode.LIVE
        self.btn_rec.setEnabled(live)
        self.btn_stop.setEnabled(live)
        self.btn_drop.setVisible(live)
        self.slot.setVisible(live)
        self.dropzone.setText({
            DeviceMode.STORAGE: "Datei hierher ziehen\n→ wird auf die Spur geschrieben",
            DeviceMode.LIVE: "Datei hierher ziehen\n→ Drop-Slot vorbereiten",
            DeviceMode.OFFLINE: "Gerät nicht verbunden",
        }[mode])
        self.setAcceptDrops(mode is not DeviceMode.OFFLINE)
        self.set_slot(None)

    def set_content(self, text: str) -> None:
        self.content.setText(text)

    def set_slot(self, text: str | None, ready: bool = False) -> None:
        self.slot.setText(text or "Kein Sample vorbereitet")
        self.btn_drop.setEnabled(ready and self.mode is DeviceMode.LIVE)

    def set_state(self, state: str, text: str = "") -> None:
        self.led.setProperty("state", state)
        self.led.style().unpolish(self.led)
        self.led.style().polish(self.led)
        self.state.setText(text)

    # ---------- Drag & Drop ----------

    @staticmethod
    def _audio_path(event) -> str | None:
        md = event.mimeData()
        if not md.hasUrls():
            return None
        for url in md.urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() in AUDIO_EXT and p.is_file():
                return str(p)
        return None

    def _highlight(self, on: bool) -> None:
        self.setProperty("dragActive", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:
        if self._audio_path(event):
            event.acceptProposedAction()
            self._highlight(True)

    def dragLeaveEvent(self, event) -> None:
        self._highlight(False)

    def dropEvent(self, event) -> None:
        self._highlight(False)
        path = self._audio_path(event)
        if path:
            event.acceptProposedAction()
            self.file_dropped.emit(self.track, path)
