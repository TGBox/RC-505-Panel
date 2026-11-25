"""Roundtrip-treuer Leser/Schreiber für RC-505mkII-`.RC0`-Dateien (ADR-0003).

Format (siehe docs/research):
- XML-artig, aber nicht wohlgeformt: nach `</database>` folgt `<count>XXXX</count>` (hexadezimal).
- Jedes Memory liegt doppelt vor (MEMORYnnnA/B.RC0); aktuell ist die Datei mit dem höheren count.
- Beim Schreiben überschreibt das Gerät den älteren Slot und vergibt den nächsten count.

Wir arbeiten auf Bytes: Jeder Zahlenwert wird über seinen Pfad (z. B. ``mem/TRACK1/X``)
indiziert; geändert werden nur die gesetzten Werte, alles andere bleibt Byte für Byte gleich.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_VALUE = re.compile(rb"^[ \t]*<(\w+)>(-?\d+)</\1>[ \t]*\r?$")
_OPEN = re.compile(rb"^[ \t]*<(\w+)(?:[ \t][^>]*)?>[ \t]*\r?$")
_CLOSE = re.compile(rb"^[ \t]*</(\w+)>[ \t]*\r?$")
_COUNT = re.compile(rb"<count>([0-9A-Fa-f]+)</count>")


class Rc0Error(ValueError):
    pass


def memory_files(data_dir: Path, memory: int) -> tuple[Path, Path]:
    return (data_dir / f"MEMORY{memory:03d}A.RC0", data_dir / f"MEMORY{memory:03d}B.RC0")


def read_count(path: Path) -> int | None:
    m = _COUNT.search(path.read_bytes()[-64:])
    return int(m[1], 16) if m else None


@dataclass
class _Span:
    start: int
    end: int


class Rc0Document:
    """Eine `.RC0`-Datei im Speicher. Werte per Pfad lesen/setzen, unverändert zurückschreiben."""

    def __init__(self, data: bytes, source: Path | None = None) -> None:
        self._data = data
        self.source = source
        self._index: dict[str, _Span] = {}
        self._edits: dict[str, int] = {}
        self._count_span: _Span | None = None
        self.memory: int | None = None       # gesetzt von load()
        self.data_dir: Path | None = None    # gesetzt von load()
        self._parse()

    # ---------- Laden ----------

    @classmethod
    def from_file(cls, path: Path) -> "Rc0Document":
        return cls(Path(path).read_bytes(), Path(path))

    @classmethod
    def load(cls, data_dir: Path, memory: int) -> "Rc0Document":
        """Lädt die aktuelle Fassung (höherer count) von MEMORYnnnA/B.RC0."""
        best: tuple[int, Path] | None = None
        for p in memory_files(Path(data_dir), memory):
            if p.exists():
                c = read_count(p)
                c = -1 if c is None else c
                if best is None or c > best[0]:
                    best = (c, p)
        if best is None:
            raise FileNotFoundError(f"MEMORY{memory:03d}A/B.RC0 nicht in {data_dir}")
        doc = cls.from_file(best[1])
        doc.memory = memory
        doc.data_dir = Path(data_dir)
        return doc

    def _parse(self) -> None:
        stack: list[str] = []
        pos = 0
        data = self._data
        for line in data.split(b"\n"):
            line_start = pos
            pos += len(line) + 1
            if m := _VALUE.match(line):
                tag = m[1].decode()
                if tag == "count":
                    continue
                key = "/".join(stack + [tag])
                if key in self._index:
                    raise Rc0Error(f"Pfad doppelt: {key}")
                self._index[key] = _Span(line_start + m.start(2), line_start + m.end(2))
            elif m := _CLOSE.match(line):
                tag = m[1].decode()
                if tag == "database":
                    continue
                if not stack or stack[-1] != tag:
                    raise Rc0Error(f"Unerwartetes </{tag}> (offen: {'/'.join(stack)})")
                stack.pop()
            elif (m := _OPEN.match(line)) and not line.lstrip().startswith(b"<?"):
                tag = m[1].decode()
                if tag != "database":
                    stack.append(tag)
        if stack:
            raise Rc0Error(f"Nicht geschlossene Sektionen: {'/'.join(stack)}")
        if m := _COUNT.search(data, max(0, len(data) - 64)):
            self._count_span = _Span(m.start(1), m.end(1))

    # ---------- Zugriff ----------

    def __contains__(self, path: str) -> bool:
        return path in self._index

    def paths(self, prefix: str = "") -> list[str]:
        return [p for p in self._index if p.startswith(prefix)]

    def get(self, path: str) -> int:
        if path in self._edits:
            return self._edits[path]
        try:
            s = self._index[path]
        except KeyError:
            raise KeyError(f"Pfad nicht vorhanden: {path}") from None
        return int(self._data[s.start:s.end])

    def set(self, path: str, value: int) -> None:
        if path not in self._index:
            raise KeyError(f"Pfad nicht vorhanden: {path}")
        self._edits[path] = int(value)

    @property
    def count(self) -> int | None:
        s = self._count_span
        return None if s is None else int(self._data[s.start:s.end], 16)

    @property
    def dirty(self) -> bool:
        return any(self.get_original(p) != v for p, v in self._edits.items())

    def get_original(self, path: str) -> int:
        s = self._index[path]
        return int(self._data[s.start:s.end])

    # ---------- Name ----------

    def name(self) -> str:
        chars = [self.get(p) for p in sorted(self.paths("mem/NAME/"))]
        return "".join(chr(c) for c in chars).rstrip()

    def set_name(self, name: str) -> None:
        keys = sorted(self.paths("mem/NAME/"))
        if not name.isascii() or len(name) > len(keys):
            raise ValueError(f"Name muss ASCII und max. {len(keys)} Zeichen sein")
        for k, ch in zip(keys, name.ljust(len(keys)), strict=True):
            self.set(k, ord(ch))

    # ---------- Schreiben ----------

    def to_bytes(self, count: int | None = None) -> bytes:
        """Datei mit allen Änderungen; ohne Änderungen byteidentisch zum Original."""
        repl: list[tuple[_Span, bytes]] = [
            (self._index[p], str(v).encode()) for p, v in self._edits.items()
        ]
        if count is not None:
            if self._count_span is None:
                raise Rc0Error("Datei hat kein <count>")
            width = self._count_span.end - self._count_span.start
            repl.append((self._count_span, f"{count:0{width}X}".encode()))
        out = self._data
        for span, new in sorted(repl, key=lambda r: r[0].start, reverse=True):
            out = out[:span.start] + new + out[span.end:]
        return out

    def save(self) -> Path:
        """Schreibt wie das Gerät in den älteren A/B-Slot mit count = höchster count + 1."""
        data_dir, memory = self.data_dir, self.memory
        if data_dir is None or memory is None:
            raise Rc0Error("save() nur für per load() geladene Dokumente")
        a, b = memory_files(data_dir, memory)
        ca = read_count(a) if a.exists() else None
        cb = read_count(b) if b.exists() else None
        ca_, cb_ = (-1 if ca is None else ca), (-1 if cb is None else cb)
        target = a if ca_ <= cb_ else b
        new_count = max(ca_, cb_, self.count if self.count is not None else -1) + 1
        payload = self.to_bytes(count=new_count)
        tmp = target.with_suffix(".RC0.tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, target)
        return target
