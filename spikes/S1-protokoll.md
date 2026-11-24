# Spike S1 – Protokoll (Live-Machbarkeit)

**Ziel:** Annahmen A1, A2, A3 und A7 aus der Discovery beantworten.
**Abbruchkriterium:** Schritt 3 scheitert (keine Aufnahme per MIDI-CC). Dann wird das Projekt offline-only.

## **Vorbereitung**

- An der RC-505mkII: MENU → USB → **VENDOR**. Danach das Gerät aus- und wieder einschalten.
- Den aktuellen BOSS-Treiber installieren und per USB 2.0 anschließen.
- Ein leeres Test-Memory wählen.
- ASIO aktivieren (PowerShell): `$env:SD_ENABLE_ASIO=1`

Beim ersten `uv run` installiert uv die Abhängigkeiten aus dem Kopf von `live_spike.py`. Scheitert dabei `python-rtmidi` (kein Wheel für deine Python-Version), dann so aufrufen:
`uv run --python 3.12 spikes/live_spike.py …`

---

1. Geräte auflisten (A7)

`uv run spikes/live_spike.py list`

| Frage | Ergebnis |
| --- | --- |
| Name des MIDI-Ports (IN / OUT) | IN `RC-505MK2 0`, OUT `RC-505MK2 1` ✅ |
| ASIO als Host-API vorhanden? | ❔ Nicht gelistet, Lauf war ohne `SD_ENABLE_ASIO=1`. Für den Spike reicht WASAPI. |
| Ausgangskanäle des RC-505-Audiogeräts (ASIO / WASAPI) | WASAPI: 4 Stereo-Endpunkte PC→RC (**MAIN, MIC, INST1, INST2**) und 4 RC→PC (MAIN, SUB1, SUB2, PHONES). Das sind 8×8 Kanäle, A7 ✅ |
| Index des Geräts für `--device` | WASAPI INST2 = 42 (Indizes ändern sich). Stabiler per Name: `--device "INST2 WASAPI"` |

1. MIDI-Clock empfangen

Am Gerät: SYSTEM → MIDI → **Clock Out / Sync Out = ON**. Dann `uv run spikes/live_spike.py clock` starten und am Gerät ALL START drücken.

| Frage | Ergebnis |
| --- | --- |
| Kommen Start und Clock an? | ✅ ja |
| Wie stabil ist die BPM? (Schwankung ±?) | 104,01 BPM, nach dem Einschwingen ±0,01. Kurz nach START bis 104,16 |
| Wird Stop erkannt? | ✅ ja |

1. Aufnahme per CC (A2) ⚠️ Abbruchkriterium

- Am Gerät im Test-Memory ein Assign anlegen: **SOURCE = CC#21**, **TARGET = TRK1 REC/PLAY**, Modus MOMENT bzw. passend.
- Senden: `uv run spikes/live_spike.py cc --cc 21` (falls nötig mit `--release`).

| Frage | Ergebnis |
| --- | --- |
| Startet Spur 1 die Aufnahme? | |
| Schaltet ein zweiter CC auf Wiedergabe bzw. Overdub? | |
| Richtiger MIDI-Kanal? (Rx-Kanal am Gerät, `--channel`) | |

1. USB-Audio auf die Spur, Routing (A1)

- Click-Datei erzeugen: `uv run spikes/live_spike.py click --bpm 104 --bars 1` (BPM = Tempo des Memory, siehe Schritt 2)
- Am Gerät die Routing-Einstellungen prüfen: USB IN → LOOP und pro Spur INPUT (MIC, INST, USB).
- **Neue Hypothese aus Schritt 1:** Der PC speist über eigene Endpunkte ein, die MIC, INST1, INST2 und MAIN heißen. Wenn das Gerät sie wie eigene Eingänge behandelt, gibt man nur der Zielspur INST2 als Input und spielt den Drop über `--device "INST2 WASAPI"` ab. Dann bleiben das echte Mic und die Instrumente auf den anderen Spuren unberührt. Das würde das Kopplungsproblem aus A1 lösen.

| Variante | Landet USB auf der Spur? |
| --- | --- |
| Mic und Inst an | |
| Mic aus, Inst an | |
| Mic und Inst aus | |
| Routing pro Spur (nur Spur 1 bekommt USB) | |

1. Gerät schließt die Aufnahme selbst (A3)

Spur 1: **MEASURE = 1** setzen. Dann `drop` ohne `--close-cc`:
`uv run spikes/live_spike.py drop --wav click.wav --cc 21 --device "INST2 WASAPI"`

| Frage | Ergebnis |
| --- | --- |
| Wechselt die Spur nach einem Takt selbst in Wiedergabe? | |
| Falls nein: Klappt der Fallback `--close-cc`? | |
| Ausgegebene Abweichung des CC zum Ziel (ms) | |
| Stream-Latenz laut PortAudio (ms) | |

1. Timing messen (Kalibrierungs-Prototyp)

1. Den Drop aus Schritt 5 durchführen.
1. Das Gerät auf STORAGE umstellen und mit dem PC verbinden.
1. Versatz messen: `uv run spikes/live_spike.py xcorr --ref click.wav --rec "E:/ROLAND/WAVE/001_1/001_1.WAV"` (Laufwerk und Memory-Nummer anpassen)
1. Mit dem vorgeschlagenen `--offset-ms` wiederholen, bis der Versatz bei ≤ 5 ms liegt.

| Versuch | --offset-ms | Gemessener Versatz (ms) | Längen-Δ (Frames) |
| --- | --- | --- | --- |
| 1 | 0 | | |
| 2 | | | |
| 3 | | | |

**Wichtig:** Ist der Versatz bei gleichem Offset über mehrere Versuche stabil (Streuung ≤ 2 ms), reicht eine einmalige Kalibrierung. Streut er stark, sind Jitter von MIDI oder USB das Problem. Dann müssen wir ADR-0002 bzw. die Clock-Strategie überdenken.

---

## Fazit

- [ ] A1 Routing:
- [ ] A2 REC per CC:
- [ ] A3 MEASURE schließt selbst:
- [ ] A7 Kanalzahl:
- [ ] Erreichte Genauigkeit:
- **Entscheidung:** weiter mit Phase 1 / offline-only / ADR anpassen
