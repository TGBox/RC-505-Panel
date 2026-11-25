"""MIDI-Verbindung zur RC-505mkII über USB (C9). mido/python-rtmidi werden erst bei Bedarf geladen."""
from __future__ import annotations

import threading

from .clock import ClockFollower

DEFAULT_PORT_HINT = "RC-505"


class MidiError(RuntimeError):
    pass


def find_port(names: list[str], hint: str) -> str:
    hits = [n for n in names if hint.lower() in n.lower()]
    if not hits:
        raise MidiError(f"Kein MIDI-Port mit „{hint}“. Vorhanden: {names}")
    return hits[0]


class MidiLink:
    """Sendet CC/Program Change und speist eingehende Clock-/Start/Stop-Meldungen in einen ClockFollower."""

    def __init__(self, port_hint: str = DEFAULT_PORT_HINT, channel: int = 0,
                 clock: ClockFollower | None = None) -> None:
        import mido
        self._mido = mido
        self.channel = channel
        self.clock = clock or ClockFollower()
        self._out = mido.open_output(find_port(mido.get_output_names(), port_hint))
        self._in = mido.open_input(find_port(mido.get_input_names(), port_hint), callback=self._on_msg)
        self._send_lock = threading.Lock()

    def _on_msg(self, msg) -> None:
        if msg.type in ("clock", "start", "stop", "continue"):
            self.clock.feed(msg.type)

    def cc(self, control: int, value: int, release: bool = False) -> None:
        """Control Change; mit `release` direkt danach Wert 0 (für MOMENT-Assigns)."""
        with self._send_lock:
            self._out.send(self._mido.Message("control_change", control=control, value=value, channel=self.channel))
            if release:
                self._out.send(self._mido.Message("control_change", control=control, value=0, channel=self.channel))

    def program_change(self, memory: int) -> None:
        """Memory 1–99 wählen (Program Change 0–98)."""
        if not 1 <= memory <= 99:
            raise ValueError("Memory 1–99")
        with self._send_lock:
            self._out.send(self._mido.Message("program_change", program=memory - 1, channel=self.channel))

    def close(self) -> None:
        for p in (self._in, self._out):
            try:
                p.close()
            except Exception:
                pass

    def __enter__(self) -> "MidiLink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
