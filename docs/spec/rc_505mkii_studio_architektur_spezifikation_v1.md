# Architektur- & Spezifikationsdokument: RC-505mkII Studio

1. Projektziel & Systemkontext

Entwicklung einer Desktop-Applikation für Windows, welche die **BOSS RC-505mkII** über USB in beiden Hardware-Betriebsarten verwaltet und steuert:

1. **Offline-Modus (`USB STORAGE`):** Direktes Lesen, Konvertieren und Schreiben von Samples (WAV) sowie Patch-Konfigurationen (`.RC0`) auf dem internen Massenspeicher der Loopstation.
2. **Live-Modus (`USB AUDIO/MIDI`):** Echtzeit-Fernsteuerung von Spuren, Effekten und Parametern via MIDI sowie sample-genaues, automatisiertes Einspielen ("Auto-Drop") von PC-Audiodateien auf einzelne Spuren über das USB-Audio-Interface.

Da die RC-505mkII hardwareseitig immer nur in einem der beiden Modi aktiv sein kann, fungiert die Software als **Dual-State-Suite** mit einer gemeinsamen lokalen Projekt-Datenbank: Änderungen, die im Offline-Modus vorbereitet oder als lokales Preset gespeichert werden, stehen im Live-Modus sofort als Metadaten (z. B. bekannte MIDI-Assigns, Tempo, Spurnamen) zur Verfügung.

---

1. Empfohlener Tech-Stack (Python / Windows)

| Komponente | Technologie / Paket | Begründung |
| --- | --- | --- |
| **GUI-Framework** | `PySide6` (Qt 6) | Volle Unterstützung für Custom-Widgets (Fader, Waveform-Views), Multi-Threading (`QThread`) und geringe UI-Latenz. |
| **Audio-I/O (Echtzeit)** | `sounddevice` (PortAudio) | Direkter Zugriff auf den BOSS ASIO- bzw. Windows WASAPI-Treiber für latenzarmes Mehrkanal-Streaming. |
| **Audio-Konvertierung** | `soundfile` + `numpy` / `scipy` | Schnelles Resampling und Konvertierung nach **44.1 kHz, 32-Bit Float Stereo WAV** inklusive Header-/Padding-Anpassung. |
| **MIDI-Engine** | `mido` + `python-rtmidi` | Zuverlässiges Senden/Empfangen von MIDI CC, Program Change (`PC`), MIDI Clock (`0xF8`) und Roland SysEx. |
| **Hardware-Erkennung** | `psutil` + `WMI` / `QFileSystemWatcher` | Automatische Erkennung, ob die RC-505mkII gerade als Laufwerk (`STORAGE`) oder als Audio/MIDI-Device gemountet ist. |

---

1. Software-Architektur

Die Anwendung wird nach dem **Model-View-Controller (MVC)**-Muster in vier entkoppelte Kernschichten unterteilt:

1. **Core / State Model (`RC505ProjectState`)**
   * Hält das Abbild der 99 Memories (Patches) inkl. der jeweils 5 Spuren, FX-Bänke (A–D) und der 16 Assign-Slots im RAM.
   * Speichert lokale Setlists und Sample-Pools (JSON/SQLite), auch wenn die Loopstation gerade nicht oder nur im MIDI-Modus angeschlossen ist.
2. **Connection Manager (`DeviceWatchdog`)**
   * Überwacht im Hintergrund (Polling alle 1000 ms oder Event-basiert) die USB-Schnittstellen.
   * **State A (`STORAGE_ACTIVE`):** Sobald ein Laufwerk mit der Struktur `ROLAND/DATA/` und `ROLAND/WAVE/` erkannt wird, schaltet die GUI die Datei-Operationen frei.
   * **State B (`LIVE_ACTIVE`):** Sobald der MIDI-Port `RC-505mk2` und der BOSS ASIO-Treiber aktiv sind, wird die Echtzeit-Engine verbunden.
3. **Storage Engine (Offline-Backend)**
   * Parser/Writer für die Roland `.RC0`-Konfigurationsdateien.
   * Audio-Transcoder & Padding-Processor für den direkten WAV-Export.
4. **Live Engine (Real-Time Audio/MIDI Worker)**
   * Läuft in einem dedizierten High-Priority-Thread, strikt getrennt vom Qt-UI-Thread.
   * Synchronisiert sich auf die eingehende MIDI-Clock der RC-505mkII (oder agiert als Master-Clock) und steuert den synchronen Audio-/MIDI-Stream beim Live-Einspielen.

---

1. Spezifikation Modul A: Offline-Modus (`STORAGE`)

## 4.1 Dateisystem-Struktur der RC-505mkII

* **Konfiguration:** `ROLAND/DATA/MEMORY001.RC0` bis `MEMORY099.RC0` (bzw. `SYSTEM.RC0` für globale Settings).
* **Audiodaten:** `ROLAND/WAVE/001_1/` bis `099_5/` (je ein Unterordner pro Memory `001`–`099` und Track `1`–`5`).

### 4.2 WAV-Konvertierungs-Pipeline (32-Bit Float & Padding)

Die RC-505mkII arbeitet intern im Gegensatz zur MK1 (16-Bit) zwingend mit **44.100 Hz, 32-Bit Floating Point, Stereo**. Zudem erfordert die Firmware der MK2/RC-600 beim direkten Dateischreiben ein spezifisches **512 KB Block-Alignment/Padding** bzw. exakte Header-Chunks, damit die Loopstation die Datei nicht als `UNSUPPORTED FORMAT` ablehnt.

* **Ablauf beim Drag & Drop eines Samples auf Spur $X$:**
  1. Einlesen der Quell-Audiodatei (WAV, MP3, FLAC, OGG).
  2. Resampling auf exakt `44100 Hz` und Konvertierung des Array-Datentyps nach `float32` (Stereo, 2 Kanäle).
  3. Optionales Time-Stretching oder Trimmen auf eine exakte Taktlänge anhand der Ziel-BPM des Patches.
  4. Schreiben der WAV-Datei inkl. des von der MK2 erwarteten Header-/Padding-Layouts in den Zielordner `ROLAND/WAVE/<MEM>_<TRACK>/`.

### 4.3 `.RC0` Patch-Parser & Generator

Damit ein eingespieltes Sample auf der MK2 sofort mit den richtigen Parametern läuft, aktualisiert die GUI die zugehörige `.RC0`-Datei des Memories:

* **Track-Parameter:** `1SHOT` (On/Off), `REVERSE`, `PLAY LEVEL`, `PAN`, `START MODE` (Immediate/Fade), `STOP MODE`, `MEASURE` (Taktanzahl / Free / Auto).
* **Tempo & Sync:** Setzen des Memory-Tempos (BPM) entsprechend der Sample-Länge sowie `TEMPO SYNC` (On/Off) und `SPEED` (Pitch vs. XFADE).
* **Assign-Injektion (Brücke zum Live-Modus):** Die Software kann im Offline-Modus automatisch ein standardisiertes **"PC-Control-Profil"** in die 16 Assign-Slots (`ASSIGN 1`–`16`) der `.RC0`-Datei schreiben, damit im späteren Live-Modus alle 5 Spuren sofort ohne manuelles Menü-Diving am Gerät über feste MIDI-CCs erreichbar sind.

---

1. Spezifikation Modul B: Live-Modus (`AUDIO/MIDI`)

### 5.1 Besonderheiten der MK2 im USB-Audio/MIDI-Betrieb

Im Vergleich zur MK1 bietet die RC-505mkII entscheidende Vorteile für eine PC-GUI:

* **Vendor-Driver (`VENDOR`-Modus):** Über den BOSS ASIO-Treiber stellt die MK2 ein mehrkanaliges USB-Audio-Interface (8 Inputs / 8 Outputs) bereit. Dadurch lassen sich Audiosignale vom PC gezielt über die internen Routing-Optionen (`LOOP IN` bzw. Sub-Mixes) einspeisen.
* **16 Assigns + dedizierte MIDI-Befehle:** Pro Memory stehen 16 frei belegbare Assign-Slots zur Verfügung, die auf MIDI-CC-Befehle (`CC#1`–`CC#31`, `CC#64`–`CC#95`) reagieren.

### 5.2 Das "Auto-Drop"-Verfahren (Samples live auf Spuren einspielen)

Da im `AUDIO/MIDI`-Modus kein Dateisystem-Zugriff existiert, implementiert die GUI eine **Sample-Accurate Live-Injection**:

1. **Vorbereitung & Routing (Einmaliges Setup im Patch / System):**
   USB-Audio-Routing der RC-505mkII steht auf `LOOP IN`. Über das Input-Routing der MK2 kann per MIDI/SysEx definiert werden, welche Spuren das USB-Signal empfangen dürfen (damit z. B. Mikrofon-Aufnahmen auf Spur 1 nicht versehentlich das PC-Sample auf Spur 3 mitaufnehmen).
2. **Quantisierter Trigger-Start (Synchronisation auf MIDI-Clock `0xF8`):**
   Der Nutzer klickt in der GUI bei einem Sample auf **"Drop to Track 3"**. Der Audio-Worker wartet (falls ein Loop läuft) anhand der eingehenden MIDI-Clock-Ticks (`24 ppqn`) exakt auf den nächsten Taktbeginn (Downbeat).
3. **Simultaner MIDI-Rec & Audio-Stream (Kompensation der ASIO-Buffer-Latenz):**
   Auf Schlag 1 sendet der Worker `MIDI CC` für `Track 3 REC/PLAY` und startet exakt um den berechneten ASIO-Output-Latenz-Offset versetzt das Abspielen des Samples über den USB-Audio-Stream.
4. **Automatischer Loop-Schluss (Sample-genauer Stop/Play-Trigger):**
   Exakt nach Ablauf der Sample-Dauer (berechnet über die Sample-Frames bei 44.1 kHz) sendet der Worker erneut den `MIDI CC` für `Track 3 REC/PLAY` (Wechsel in Playback) oder `Track 3 STOP` (wenn das Sample nur geladen, aber noch nicht abgespielt werden soll).

### 5.3 Standard-MIDI-Mapping (16 Assigns der MK2)

Um im Live-Modus die volle Kontrolle über alle 5 Spuren zu haben, nutzt die GUI folgendes Standard-Assign-Layout (das über Modul A automatisch in die Patches gepatcht werden kann):

| Assign # | MIDI Quelle | Ziel-Parameter (Target) | Funktion in der GUI |
| --- | --- | --- | --- |
| **1 – 5** | `CC# 21 – 25` | `TRK 1–5 REC/PLAY` | Startet Aufnahme / Playback / Overdub für Spur 1–5 |
| **6 – 10** | `CC# 26 – 30` | `TRK 1–5 STOP` (bzw. `CLEAR`) | Stoppt Spur 1–5 (oder löscht bei Hold/Wert 127) |
| **11 – 15** | `CC# 71 – 75` | `TRK 1–5 PLAY LEVEL` | Virtuelle 100mm-Fader in der GUI für Spur 1–5 (Werte 0–127) |
| **16** | `CC# 80` | `INPUT FX` / `TRACK FX` Toggle | Dynamischer Slot oder Umschalten der aktiven FX-Bank |

*(Zusätzlich werden `MIDI Clock`, `MIDI Start/Stop` für `ALL START/STOP` und `Program Change 1–99` für den Memory-Wechsel nativ ohne Verbrauch von Assign-Slots unterstützt).*

---

1. UI/UX-Konzept (Hauptfenster)

Die Oberfläche orientiert sich am physischen Layout der RC-505mkII, erweitert um einen Sample-Browser:

* **Top-Bar (Status & Global Controls):**
  * **Connection Badge:** Zeigt live `LIVE MODE (ASIO + MIDI)` oder `STORAGE MODE (Laufwerk E:)` oder `OFFLINE (Local Edit)`.
  * **Memory-Selector (`01` – `99`):** Dropdown + Name des aktuellen Patches, BPM-Anzeige (live synchronisiert über MIDI-Clock), Tap-Tempo-Button und `ALL START / STOP`.
* **Center-View (5-Track-Channellayout):**
  * 5 vertikale Kanalzüge (Track 1 bis 5) nebeneinander.
  * **Pro Kanalzug:**
    * **Waveform-Display / Drop-Zone:** Zeigt im Storage-Modus die tatsächliche Wellenform der `WAV`-Datei auf der Spur; nimmt in beiden Modi per Drag & Drop neue Samples entgegen.
    * **Track-Controls:** Virtueller Volume-Fader, Pan-Potentiometer, Buttons für `1-SHOT`, `REVERSE`, `FX` und die beleuchteten Haupttaster `REC/PLAY`, `STOP` und `CLEAR`.
* **Left-Sidebar (Sample-Library & Setlists):**
  * Lokaler Datei-Browser mit Vorhör-Funktion (Preview über PC-Kopfhörer statt Loopstation) und automatischer BPM-/Taktlängen-Erkennung.
* **Bottom-Panel (FX & Assign-Matrix):**
  * Schnellzugriff auf **Input FX (A–D)** und **Track FX (A–D)** inkl. Bank-Umschaltung.
  * Ein-Klick-Button im Storage-Modus: *"MIDI-Steuerungsprofil auf dieses Memory anwenden"* (schreibt die 16 Standard-Assigns in die `.RC0`-Datei).

---

1. Projektstruktur (Blueprint)

```text
rc505mk2-studio/
├── pyproject.toml              # uv / Projekt-Abhängigkeiten (PySide6, mido, python-rtmidi, sounddevice, soundfile, numpy)
├── src/
│   ├── main.py                 # App-Entrypoint
│   ├── core/
│   │   ├── models.py           # Datenklassen: MemoryPatch, TrackConfig, FXSlot, AssignSlot
│   │   ├── device_watcher.py   # Erkennt USB-Storage-Mount vs. USB-MIDI/ASIO-Port
│   │   └── audio_converter.py  # Resampling -> 44.1kHz, 32-Bit Float Stereo WAV + 512KB Padding
│   ├── storage_mode/
│   │   ├── rc0_parser.py       # Liest und schreibt ROLAND/DATA/MEMORYxxx.RC0
│   │   └── wave_manager.py     # Kopiert, sichert und räumt ROLAND/WAVE/xxx_x/ auf
│   ├── live_mode/
│   │   ├── midi_controller.py  # Mido/RtMidi Wrapper (CC, PC, Clock-Sync, SysEx)
│   │   ├── audio_streamer.py   # Sounddevice ASIO/WASAPI Output-Stream
│   │   └── autodrop_engine.py  # Takt-synchroner State-Machine-Worker (Rec -> Play Audio -> Stop)
│   └── ui/
│       ├── main_window.py      # Hauptfenster mit Top-Bar, 5-Track-Grid & Sidebar
│       ├── track_strip.py      # Custom Widget für einen einzelnen Spur-Kanalzug
│       └── waveform_widget.py  # PySide6 QPainter Waveform-Vorschau & Drag-and-Drop-Target
└── tests/
    ├── test_rc0_parser.py
    └── test_wav_padding.py
```

---

1. Entwicklungs-Roadmap (Meilensteine)

1. **Phase 1 – Storage-Core & `.RC0`-Analyse:**
   Einlesen eines echten `ROLAND`-Backup-Ordners der MK2. Verifizieren des `.RC0`-Parsers und Testen der `32-Bit Float WAV`-Generierung inkl. Header/Padding, sodass die MK2 per Skript erzeugte Samples fehlerfrei abspielt.
1. **Phase 2 – Live-MIDI & Auto-Drop-Prototyp (CLI/Headless):**
   Verbinden mit dem MK2-MIDI-Port, Auslesen der MIDI-Clock (`0xF8`) und Bau der `autodrop_engine.py`, die ein Test-Sample über ASIO abspielt und per MIDI-CC rahmengenau auf Spur 1 aufnimmt.
1. **Phase 3 – PySide6-GUI & Dual-Mode-Integration:**
   Zusammenführen beider Backends hinter den `5 Track-Strips` und Einbau des `DeviceWatchdog`, damit die GUI beim Umschalten des USB-Modus an der RC-505mkII nahtlos zwischen Dateizugriff und Echtzeit-Streaming wechselt.
