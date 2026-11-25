"""Eine Aktion, viele Auslöser (ADR-0005): Buttons, Tastatur und später MIDI-Controller
erzeugen dieselben `Action`-Objekte; die App abonniert sie an einer Stelle."""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

ActionName = Literal["drop", "rec_play", "stop", "memory_select", "calibrate", "import"]


@dataclass(frozen=True)
class Action:
    name: ActionName
    track: int | None = None
    value: int | None = None
    source: str = "ui"          # "ui" | "key" | "midi"


class ActionBus:
    def __init__(self) -> None:
        self._handlers: list[Callable[[Action], None]] = []
        self._lock = threading.Lock()
        self.log: list[Action] = []     # für Drop-Log / North-Star-Metrik (Discovery §5)

    def subscribe(self, handler: Callable[[Action], None]) -> None:
        with self._lock:
            self._handlers.append(handler)

    def dispatch(self, action: Action) -> None:
        with self._lock:
            handlers = list(self._handlers)
            self.log.append(action)
            del self.log[:-500]
        for h in handlers:
            h(action)


# Standard-Tastenbelegung: F1–F5 = Drop auf Spur 1–5, Umschalt+F1–F5 = REC/PLAY, Strg+F1–F5 = STOP
DEFAULT_KEYS: dict[str, Action] = {
    **{f"F{t}": Action("drop", t, source="key") for t in range(1, 6)},
    **{f"Shift+F{t}": Action("rec_play", t, source="key") for t in range(1, 6)},
    **{f"Ctrl+F{t}": Action("stop", t, source="key") for t in range(1, 6)},
}
