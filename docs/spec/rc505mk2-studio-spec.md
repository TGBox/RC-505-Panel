# Spec: RC-505mkII Studio (v2)

**Ersetzt:** `rc_505mkii_studio_architektur_spezifikation.md` (v1)
**Grundlage:**

- [UX Discovery](../ux-discovery/2026-11-18-rc505mk2-studio-discovery.md)
- Befunde aus dem echten Backup `D:\RC 505 mk2 - Backup`

---

1. One-Pager

**Problem:** Ein PC-Sample taktgenau als Loop auf die RC-505mkII zu bringen geht heute nur per Hand-Timing und ist fehleranfällig. Darum werden PC-Samples gar nicht genutzt.

**How Might We:** Wie können wir ein beliebiges Sample mit einer Aktion tempo- und taktgenau auf eine Spur bringen, vorab im Storage-Modus und live in einen laufenden Loop?

**Gewählte Richtung:** *Risk-first Dual-Mode*

1. Zuerst ein Live-Spike, der die Machbarkeit klärt.
2. Dann der Offline-Kern: WAV- und `.RC0`-Writer plus Time-Stretch.
3. Dann Auto-Drop.
4. Zuletzt die GUI, die alles zusammenführt.

**Was v1 der Spec falsch oder ungeprüft hatte (korrigiert):**

| v1 | v2 (belegt bzw. entschieden) |
| --- | --- |
| `MEMORY001.RC0` | `MEMORY001A.RC0` und `MEMORY001B.RC0`, die aktuelle Datei hat den höheren `<count>` |
| Padding auf 512 KB | **`JUNK`-Chunk** füllt auf ein Vielfaches von **256 KB** auf |
| `.RC0` als XML | Nicht wohlgeformt (`<count>` hinter `</database>`), die Tags sind anonym (`<A>…`) |
| WAV kopieren reicht | `TRACKn/<X>` (Länge in Frames) muss mitgeschrieben werden |
| Loop-Schluss per zweitem CC | Bevorzugt schließt das Gerät selbst (MEASURE), der CC ist nur Fallback (ADR-0002) |
| 8×8 USB-Audio, Routing pro Spur | Ungeprüft, wird im Spike gemessen |
| Gleichwertige Dual-Suite | Erst der Spike, dann Offline, dann Live (ADR-0001) |

## **MVP-Scope**

- Storage: Sample per Drag & Drop auf eine Spur. Das Tool stretcht aufs Memory-Tempo und schreibt WAV plus `.RC0`. Vorher wird automatisch ein Backup angelegt.
- Storage: Das Standard-Assign-Profil (16 Assigns) per Klick in ein Memory schreiben.
- Live: Fünf Drop-Slots (vorgerendert), „Drop → Spur N“, quantisiert auf den Downbeat.
- Live: REC/PLAY, STOP und Level der Spuren 1–5 per MIDI, BPM-Anzeige aus der Clock.
- Eingaben: Maus und Tastatur. MIDI-Input (Fußschalter) kommt in Phase 4.
- Erkennung des Gerätemodus (Storage, Live oder Offline).

## **Not-Doing (bewusst weggelassen)**

- Kein Installer, keine Unterstützung mehrerer Firmware-Versionen, kein RC-600 oder MK1
- Kein vollständiger Editor aller `.RC0`-Parameter und FX (dafür gibt es BTS und den RC-Editor). Gemappt werden nur die Felder, die wir brauchen.
- Kein Echtzeit-Time-Stretching. Gestreckt wird immer vorab.
- Keine Setlist-Verwaltung, keine Cloud, keine Analytics
- Kein Waveform-Editor (nur Trim auf Taktlänge)
- Keine eigene Master-Clock im MVP: Das Gerät ist der Clock-Master.

**Offene Fragen:** Siehe Discovery §7, Annahmen A1–A8. Der Spike in §6 beantwortet die kritischen.

---

1. Capability-Matrix

| ID | Fähigkeit | Modul | Hängt ab von | Testbar ohne Gerät? |
| --- | --- | --- | --- | --- |
| C1 | `.RC0` lesen und schreiben, roundtrip-treu, A/B-Auswahl | `storage/rc0.py` | – | ✅ (Fixtures aus dem Backup) |
| C2 | Feld-Mapping (NAME, TRACKn, ASSIGNn, Tempo) | `storage/rc0_schema.py` | C1 | ✅ teilweise, Bedeutungen per Diff am Gerät |
| C3 | RC-WAV schreiben (32f, `fmt` mit 28 Byte, JUNK auf 256 KB) | `audio/rcwav.py` | – | ✅ (gegen Backup-WAVs vergleichen) |
| C4 | Transcode (beliebiges Format → 44,1 kHz, Stereo, float32) | `audio/convert.py` | – | ✅ |
| C5 | BPM-Erkennung mit Korrektur ×2/÷2 | `audio/tempo.py` | C4 | ✅ |
| C6 | Time-Stretch und Trim auf N Takte | `audio/stretch.py` | C4, C5 | ✅ |
| C7 | Spur-Import (C3 + C2 + Backup) | `storage/track_import.py` | C1–C6 | ✅ mit temporärem Ordner, am Ende am Gerät |
| C8 | Erkennung des Gerätemodus | `core/device_watch.py` | – | ✅ gemockt |
| C9 | MIDI: Ports, CC, PC, Clock-Empfang, BPM | `live/midi.py` | – | ✅ mit virtuellem Port |
| C10 | Audio-Ausgabe (ASIO/WASAPI), Wiedergabe mit Vorlauf | `live/audio_out.py` | – | ✅ teilweise |
| C11 | Auto-Drop-State-Machine | `live/autodrop.py` | C9, C10 | ✅ mit simulierter Clock |
| C12 | Latenz-Kalibrierung (Drop → Storage → Kreuzkorrelation) | `live/calibrate.py` | C1, C3, C11 | ❌ nur am Gerät |
| C13 | Action-Bus und Input-Mapping (Maus, Tastatur, MIDI) | `core/actions.py` | – | ✅ |
| C14 | GUI (Top-Bar, 5 Spuren, Bibliothek, Drop-Slots) | `ui/` | alle | manuell |

---

1. Schnittstellen-Verträge (Python)

Die Verträge stehen vor der Logik fest. Alle Kernmodule sind Qt-frei, damit sie ohne GUI testbar bleiben.

```python
# core/models.py
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

class DeviceMode(Enum):
    OFFLINE = auto()   # kein Gerät, nur lokale Bearbeitung
    STORAGE = auto()   # Laufwerk mit ROLAND/DATA + ROLAND/WAVE
    LIVE = auto()      # MIDI-Port "RC-505mk2" + Audio-Device vorhanden

@dataclass(frozen=True)
class TrackRef:
    memory: int        # 1..99
    track: int         # 1..5

@dataclass(frozen=True)
class AudioClip:
    path: Path         # bereits gerendert: 44,1 kHz, Stereo, float32
    frames: int
    bpm: float
    bars: int
```

```python
# storage/rc0.py – roundtrip-treu: Der Originaltext bleibt erhalten, nur Werte werden ersetzt
class Rc0Document:
    @classmethod
    def load(cls, data_dir: Path, memory: int) -> "Rc0Document": ...
        # wählt A oder B nach höherem <count>, merkt sich die Quelle
    def get(self, section: str, key: str) -> int: ...          # z. B. ("TRACK1", "X")
    def set(self, section: str, key: str, value: int) -> None: ...
    def name(self) -> str: ...                                  # NAME-Sektion als ASCII
    def to_bytes(self) -> bytes: ...                            # unverändert, wenn nichts gesetzt wurde
    def save(self) -> Path: ...
        # schreibt in den älteren Slot (A/B), count + 1 (Hypothese A5, Backup-Pflicht)
```

```python
# audio/rcwav.py
BLOCK = 262_144  # 256 KB
def write_rc_wav(path: Path, samples: "np.ndarray[float32, (n, 2)]") -> int: ...
    # RIFF/WAVE, fmt mit 28 Byte (Format 3, 2 Kanäle, 44100 Hz, 32 Bit, 12 Byte Extra wie im Original),
    # data-Chunk-Header ab Offset 48, Samples ab Offset 56, danach JUNK-Chunk (inkl. 8 Byte Header) so lang,
    # dass die Dateigröße ein Vielfaches von BLOCK ist. Gibt die Frames zurück.
    # Am 2026-11-18 gegen 005_1.WAV und 002_3.WAV geprüft: Der Nachbau ist byteidentisch.
    # Offen: Randfall, wenn das Padding 0 Byte ergibt (JUNK weglassen oder einen vollen Block anhängen?)
def read_rc_wav(path: Path) -> "np.ndarray": ...
```

```python
# audio/stretch.py
def render_for_memory(src: Path, target_bpm: float, bars: int | None,
                      src_bpm: float | None = None) -> AudioClip: ...
    # Transcode, BPM bestimmen oder übernehmen, stretchen, auf bars * 4 Schläge trimmen.
    # Länge exakt round(bars * 4 * 60 / target_bpm * 44100) Frames.
```

```python
# storage/track_import.py
def import_to_track(drive: Path, ref: TrackRef, clip: AudioClip) -> None: ...
    # 1. Backup von MEMORYxxxA/B + WAVE/xxx_y nach %LOCALAPPDATA%/rc505studio/backups/<ts>/
    # 2. write_rc_wav(drive/ROLAND/WAVE/xxx_y/xxx_y.WAV)
    # 3. Rc0Document: TRACKy.X = clip.frames (+ weitere Felder laut Storage-Spike)
    # 4. save()
```

```python
# core/actions.py – eine Action, viele Auslöser
from typing import Literal, Callable
ActionName = Literal["drop", "rec_play", "stop", "clear", "level", "all_start_stop", "memory_select"]

@dataclass(frozen=True)
class Action:
    name: ActionName
    track: int | None = None
    value: int | None = None

class ActionBus:
    def subscribe(self, handler: Callable[[Action], None]) -> None: ...
    def dispatch(self, action: Action) -> None: ...     # thread-sicher, nicht blockierend

# Bindings als JSON, z. B. {"key:F3": {"name":"drop","track":3}, "midi:cc:64:127": {"name":"drop","track":1}}
```

```python
# live/autodrop.py
class DropState(Enum):
    IDLE = auto(); ARMED = auto(); RECORDING = auto(); PLAYING = auto(); FAILED = auto()

class AutoDropEngine:
    def __init__(self, midi: "MidiLink", audio: "AudioOut", latency_frames: int): ...
    def arm(self, track: int, clip: AudioClip) -> None: ...   # nur gerenderte Clips
    def on_clock_tick(self, tick: int) -> None: ...           # 24 ppqn, wird vom MIDI-Thread aufgerufen
    # Ablauf: ARMED → Downbeat − Vorlauf: Audio starten → Downbeat: CC REC/PLAY
    #         → (das Gerät schließt über MEASURE | Fallback: CC nach clip.frames) → PLAYING
    state: DropState
```

---

1. Standard-Assign-Profil (unverändert aus v1, Kodierung offen)

| Assign | Quelle | Ziel |
| --- | --- | --- |
| 1–5 | CC 21–25 | TRK 1–5 REC/PLAY |
| 6–10 | CC 26–30 | TRK 1–5 STOP |
| 11–15 | CC 71–75 | TRK 1–5 PLAY LEVEL |
| 16 | CC 80 | frei / FX-Toggle |

Wie `ASSIGNn/<A…>` kodiert ist, ermitteln wir per Diff: ein Assign am Gerät setzen, ein Backup ziehen und mit dem vorherigen vergleichen.

---

1. Akzeptanzkriterien (Definition of Done)

| ID | Kriterium |
| --- | --- |
| AC1 | `Rc0Document.load(...).to_bytes()` ist **byteidentisch** mit allen 198 Memory-Dateien des Backups. |
| AC2 | `write_rc_wav` auf die Samples einer Backup-WAV ergibt eine **byteidentische** Datei. Der Prototyp vom 2026-11-18 erfüllt das schon für 2 von 2 Dateien. |
| AC3 | Ein importiertes Sample (aus MP3 oder WAV) spielt am Gerät ohne Fehlermeldung, die Länge stimmt mit N Takten überein. |
| AC4 | Vor jedem Schreibvorgang existiert ein Backup. Eine Wiederherstellung per Ein-Klick bringt das Memory auf den Zustand vorher zurück. |
| AC5 | `render_for_memory` liefert eine Länge auf ±1 Frame genau zur Taktlänge. |
| AC6 | Auto-Drop: 10 von 10 Drops landen auf dem Downbeat, nach der Kalibrierung mit einem Versatz von ≤ 5 ms (gemessen nach C12). |
| AC7 | Ein Drop blockiert nie den UI-Thread. Die GUI reagiert während eines Drops in < 50 ms. |
| AC8 | Jede Action ist über Maus und Tastatur auslösbar. Ab Phase 4 auch über MIDI-Input. |

---

1. Spikes (vor Phase 1, je 1–2 Abende)

**S1 – Live-Machbarkeit** (`spikes/live_spike.py`, Headless)

1. `mido.get_input_names()` und `get_output_names()` sowie `sounddevice.query_devices()` auflisten. Daraus ergeben sich Portnamen, ASIO-Verfügbarkeit und Kanalzahl (A7).
2. MIDI-Clock empfangen und BPM ausgeben. Prüfen, ob sie stabil ist und ob Start/Stop ankommen.
3. Am Gerät von Hand ein Assign setzen (CC 21 → TRK1 REC/PLAY), dann per Skript senden. Prüfen, ob Spur 1 aufnimmt (A2).
4. USB-Audio einspielen, mit Mic und Line an und aus (A1).
5. MEASURE der Spur auf 1 Takt setzen. Prüfen, ob das Gerät die Aufnahme selbst schließt (A3).
6. Einen Klick-Drop durchführen, dann in den Storage-Modus wechseln, die WAV lesen und den Versatz gegen die Quelle per Kreuzkorrelation messen (C12-Prototyp).

## **S2 – Storage-Schreibtest**

1. Eine leere Spur wählen und eine selbst geschriebene RC-WAV ablegen. Erst nur die WAV testen, dann WAV plus `TRACKn/X`.
2. Am Gerät prüfen, ob die Spur geladen wird und spielt (A4).
3. Danach ein Backup ziehen und gegen den Stand vorher vergleichen: Welche Felder hat das Gerät selbst angepasst? Und wie verhält sich `<count>` (A5)?

**Abbruchkriterium:** Wenn S1-3 scheitert (kein REC per MIDI), ist das Projekt offline-only. Live-Steuerung und Auto-Drop werden dann gestrichen.

---

1. Projektstruktur

```text
rc505mk2-studio/
├── pyproject.toml            # uv; PySide6, mido, python-rtmidi, sounddevice, soundfile, numpy, scipy
├── spikes/                   # wird verworfen, kein Produktionscode
├── src/rc505studio/
│   ├── core/      models.py · actions.py · device_watch.py · config.py
│   ├── audio/     convert.py · tempo.py · stretch.py · rcwav.py
│   ├── storage/   rc0.py · rc0_schema.py · track_import.py · backup.py
│   ├── live/      midi.py · audio_out.py · autodrop.py · calibrate.py
│   └── ui/        main_window.py · track_strip.py · waveform.py · drop_slots.py · library.py
└── tests/
    ├── fixtures/  (Kopien aus dem Backup: MEMORY001A/B, SYSTEM1, 2–3 WAVs)
    └── test_rc0_roundtrip.py · test_rcwav.py · test_stretch.py · test_autodrop_sim.py · test_actions.py
```

1. Roadmap

| Phase | Inhalt | Exit-Kriterium |
| --- | --- | --- |
| 0 | Spikes S1 und S2 | Annahmen A1–A5 beantwortet, ADR-0002 bestätigt oder angepasst |
| 1 | Offline-Kern: C1, C2 (nur NAME, TRACKn, Tempo), C3, C4, C5, C6, C7, Backup | AC1–AC5 |
| 2 | Live-Kern headless: C9, C10, C11, C12 | AC6 |
| 3 | GUI und Moduserkennung: C8, C13, C14 (Maus und Tastatur) | AC7, AC8 (ohne MIDI) |
| 4 | Assign-Profil (C2: ASSIGN1–16) und MIDI-Input-Mapping (Fußschalter) | AC8 vollständig |

1. Entscheidungen

- [ADR-0001](../adr/2026-11-18-risk-first-spike.md): Erst der Spike, dann die Architektur
- [ADR-0002](../adr/2026-11-18-loop-schluss-durch-geraet.md): Loop-Schluss durch das Gerät, CC nur als Fallback
- [ADR-0003](../adr/2026-11-18-rc0-roundtrip-parser.md): Eigener roundtrip-treuer `.RC0`-Parser
- [ADR-0004](../adr/2026-11-18-stretch-vorab-rendern.md): Time-Stretch immer vorab rendern
- [ADR-0005](../adr/2026-11-18-action-bus-eingaben.md): Alle Eingaben über einen Action-Bus
