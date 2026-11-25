# Spike S1 – Protokoll (Live-Machbarkeit)

> **Schritt-für-Schritt-Anleitung:** siehe [`ANLEITUNG-offene-punkte.md`](ANLEITUNG-offene-punkte.md)

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
| Index des Geräts für `--device` | WASAPI INST2 = 42 (Indizes ändern sich). Stabiler per Name: `--device "RC-505mk2 INST2 WASAPI"` |

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
| Startet Spur 1 die Aufnahme? | ✅ ja: CC#21 → TRK1 REC/PLY (2026-11-25) |
| Schaltet ein zweiter CC auf Wiedergabe bzw. Overdub? | ✅ ja, auf Wiedergabe. Stopp per CC#26 → TRK1 STOP funktioniert auch |
| Richtiger MIDI-Kanal? (Rx-Kanal am Gerät, `--channel`) | ✅ Kanal 1 (Standard) |

1. USB-Audio auf die Spur, Routing (A1)

- Click-Datei erzeugen: `uv run spikes/live_spike.py click --bpm 104 --bars 1` (BPM = Tempo des Memory, siehe Schritt 2)
- Am Gerät die Routing-Einstellungen prüfen: USB IN → LOOP und pro Spur INPUT (MIC, INST, USB).
- **Neue Hypothese aus Schritt 1:** Der PC speist über eigene Endpunkte ein, die MIC, INST1, INST2 und MAIN heißen. Wenn das Gerät sie wie eigene Eingänge behandelt, gibt man nur der Zielspur INST2 als Input und spielt den Drop über `--device "RC-505mk2 INST2 WASAPI"` ab. Dann bleiben das echte Mic und die Instrumente auf den anderen Spuren unberührt. Das würde das Kopplungsproblem aus A1 lösen.

| Variante | Landet USB auf der Spur? |
| --- | --- |
| Mic und Inst an | |
| Mic aus, Inst an | |
| Mic und Inst aus | |
| Routing pro Spur (nur Spur 1 bekommt USB) | |

**Ergebnis 2026-11-25.** Geprüft wurde bei der *Wiedergabe* der Spur (Rhythmus aus), nicht beim Mithören während der Aufnahme. Während der Aufnahme reicht das Gerät USB nur an den Ausgang durch.

| # | PC-Ausgang | TRACK 1 INPUT | Click auf Spur 1? |
| --- | --- | --- | --- |
| 4e | MAIN | alle aus | ❌ nein |
| 4e′ | INST2 | alle aus | ❌ nein |
| 4a | INST2 | nur INST2 L/R | ✅ ja |
| 4b | INST2 | nur MIC 1 | ❌ nein |

**Fazit A1 ✅:** Der PC-Ausgang „INST2“ (WASAPI-Endpunkt) landet nur am Spur-Eingang INST2. Damit lässt sich USB-Audio gezielt auf eine Spur legen, und INST2 wird der Drop-Kanal.
**Konsequenz:** Die Buchse INST2 am Gerät bleibt für Drops frei. Ein dort eingestecktes Instrument würde mit aufgenommen (noch nicht getestet).

- **§5a Ergebnis 2026-11-25 – MEASURE schließt selbst (A3) ✅ (mit Bedingung)**

- 1. Versuch: Die Aufnahme lief nach einem Takt weiter. Danach zeigte MEASURE 8 (die tatsächlich aufgenommene Länge). Die Vorgabe 1 hatte also nicht gegriffen.
- 1. Versuch, in dieser Reihenfolge: Spur leeren → **danach** LOOP SYNC = ON und MEASURE = 1 setzen → kontrollieren → Drop ohne `--close-cc`. **Die Aufnahme stoppt nach genau einem Takt von selbst.**
- Vermutung: Das Leeren der Spur setzt MEASURE zurück, oder die erste Einstellung wurde nicht übernommen. Noch zu prüfen.
- Folge für ADR-0002: Bestätigt, sofern MEASURE vor dem Drop gesetzt ist. MEASURE ist laut Parameter Guide kein Assign-Ziel, lässt sich also nicht per MIDI setzen. Es muss vorab in der `.RC0` stehen, sonst greift der Fallback `--close-cc`.
- **Leeren setzt ein explizit gesetztes MEASURE nicht zurück** (bleibt 1). Eine Länge, die per AUTO aus einer Aufnahme entstanden ist (8), springt beim Leeren auf AUTO zurück. Daraus folgt: Ein MEASURE, das vorab in der `.RC0` steht, hält über beliebig viele Drops und Leerungen.

**§5b Ergebnis 2026-11-25 – QUANTIZE = MEASURE + `--cc-lead-ms 30` ✅**

- Die Aufnahme startet auf dem nächsten Taktanfang nach dem CC, nicht einen Takt zu spät. Der Vorlauf von 30 ms reicht.
- Damit ist das die bevorzugte Konfiguration: Das Gerät bestimmt Start (QUANTIZE) und Ende (MEASURE) selbst. Die Genauigkeit hängt nur noch an der Audio-Latenz (§6).

1. Gerät schließt die Aufnahme selbst (A3)

Spur 1: **MEASURE = 1** setzen. Dann `drop` ohne `--close-cc`:
`uv run spikes/live_spike.py drop --wav click.wav --cc 21 --device "RC-505mk2 INST2 WASAPI"`

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

## §6 Ergebnis 2026-11-25 – Timing ✅

Einstellungen: INST2-Drop, MEASURE = 1, QUANTIZE = MEASURE, `--cc-lead-ms 30`, `--offset-ms -53.5`, WASAPI (22 ms laut PortAudio), 104 BPM.

**Messreihe A** (alte Zielberechnung, korrigiert ausgewertet). Die alte Ganz-Loop-Korrelation hatte bei Lauf 1 und 5 um ganze Schläge danebengelegen. Korrigiert ergibt sich:

| Lauf | Versatz |
|---|---|
| 1 | +4,76 ms (−25 232 Frames = −1 Schlag + 210) |
| 2 | −1,95 ms |
| 3 | −0,50 ms |
| 4 | −2,36 ms (nur Schlag 1, Callback-Absturz) |
| 5 | −6,28 ms (pro Schlag −277, −277, −277 Frames) |

**Messreihe B** (Ausgleichsgerade über die Clock-Ticks, Uhrenabgleich im Hauptthread, Auswertung pro Schlag):

| Lauf | Clock-Jitter | Versatz |
|---|---|---|
| 1 | 0,45 ms | −2,70 ms |
| 2 | 0,47 ms | −0,45 ms |
| 3 | 0,49 ms | −0,66 ms |
| 4 | 0,47 ms | −2,34 ms |

- Mittelwert −1,54 ms, Spannweite 2,25 ms (±1,1 ms). Die Loop-Länge ist in allen Läufen exakt (Δ 0 Frames, alle Schläge innerhalb einer Aufnahme identisch).
- Die Werte bilden zwei Gruppen, um −0,5 ms und um −2,5 ms. Vermutlich liegt das am Puffer-Raster von USB oder Treiber, das prüfen wir nicht weiter.
- **Kalibrierter Offset für dieses Setup: `--offset-ms -52.0`.** Daraus wird ein Kalibrier-Assistent in der App (C12).
- Für den Spike ist das ausreichend: Ziel war ein Versatz von ≤ 5 ms, das ist erreicht. Die Streuung von ±1,1 ms liegt knapp über dem Ziel von ±1 ms, ist aber unhörbar.

## Fazit

- [x] **A1 Routing:** ✅ Der PC-Ausgang INST2 landet nur am Spur-Eingang INST2 → ADR-0006
- [x] **A2 REC per CC:** ✅ REC/PLAY und STOP funktionieren über Assigns (CC#21/#26)
- [x] **A3 MEASURE schließt selbst:** ✅ Das gilt, wenn MEASURE vorab explizit gesetzt ist. Der Wert übersteht das Leeren der Spur. → ADR-0002 akzeptiert
- [x] **A7 Kanalzahl:** ✅ 4 Stereo-Ausgänge vom PC zur RC (MAIN, MIC, INST1, INST2) und 4 von der RC zum PC (WASAPI)
- [x] **Erreichte Genauigkeit:** −1,5 ms ± 1,1 ms nach der Kalibrierung, Loop-Länge exakt
- [x] **A5 A/B-Schreiben:** ✅ siehe `docs/research` (count hexadezimal, jeweils der ältere Slot)
- [ ] **A4 Import einer selbst geschriebenen WAV:** offen → §7/§8 der Anleitung
- **Entscheidung:** Live-Teil bleibt. Weiter mit S2 (Storage) und danach Phase 1.
