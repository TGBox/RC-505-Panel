# Anleitung: Offene Punkte klären (Spikes S1 + S2)

Diese Anleitung führt Schritt für Schritt durch alle Tests, die nur mit der Loopstation in der Hand gehen. Die Ergebnisse trägst du in `spikes/S1-protokoll.md` ein. Am Ende gibt es eine Entscheidungstabelle (§9).

**Zeitbedarf:** etwa 2–3 Stunden, gut auf zwei Abende verteilbar (Teil A Live, Teil B Storage).

## Was geklärt werden muss

| # | Frage | Wo |
|---|---|---|
| **A2** ⚠️ | Startet ein MIDI-CC die Aufnahme einer Spur? Wenn nicht, ist das Projekt offline-only. | §3 |
| A1 | Landet USB-Audio nur auf der Zielspur, ohne Mic und Instrumente zu stören? | §4 |
| A3 | Schließt das Gerät die Aufnahme selbst (MEASURE), und funktioniert QUANTIZE? | §5 |
| T | Wie genau trifft der Drop den Takt, und wie stabil ist der Versatz? | §6 |
| A6 | Wie sind Assigns und Spur-Einstellungen in der `.RC0` kodiert? | §2, §7 |
| A4 | Akzeptiert das Gerät eine selbst geschriebene WAV? Welche `.RC0`-Felder müssen dazu stimmen? | §8 |
| A5 | Wie schreibt das Gerät die A/B-Dateien (`<count>`)? | §7, §8 |

**Grundregeln**
- Alle Befehle laufen in PowerShell im Projektordner (`RC-505-Panel`).
- Platzhalter wie `<N>` niemals tippen, PowerShell versteht `<` nicht. Unten stehen fertige Werte.
- Laufwerksbuchstabe der RC im Storage-Modus: Diese Anleitung nimmt **`E:`** an. Weicht er ab, überall ersetzen.
- Test-Memory: Diese Anleitung nimmt **Memory 98** an. Nimm ein Memory, dessen Inhalt du nicht brauchst, und ersetze `98` und `098` überall durch deine Nummer.

---

## 1. Einmalige Vorbereitung

### 1.1 Am Gerät: System-Einstellungen

**MENU → MIDI**
- **RX CH → CTL = 1.** Das Skript sendet auf Kanal 1. Bei einem anderen Wert später `--channel <Wert−1>` mitgeben.
- **SYNC → CLOCK = INTERNAL.** Das Gerät ist der Taktgeber, der PC folgt.
- **SYNC → OUT = ON.** Das Gerät sendet die MIDI-Clock (laut Test schon aktiv).
- **SYNC → START = ALL.**
- **THRU = OFF**

**MENU → USB**
- **AUDIO MODE = VENDOR**, danach das Gerät aus- und wieder einschalten (war schon so).
- **ROUTING = LOOP IN.** Laut Parameter Guide gelangt USB-Audio nur dann auf die Spuren.
- **INPUT LEVEL = 100**, **OUTPUT LEVEL = 100**

Mit EXIT verlassen. Die System-Einstellungen speichert das Gerät selbst.

### 1.2 Am PC
Diese Befehle einmal ausführen:
```powershell
uv run spikes/live_spike.py list
uv run spikes/live_spike.py click --bpm 104 --bars 1 --out click_1bar.wav
uv run spikes/live_spike.py click --bpm 104 --bars 2 --out click_2bar.wav
```
Die Click-Dateien haben einen lauten Schlag 1 und leisere Schläge 2–4. Daran hörst du sofort, ob ein Loop versetzt ist.

### 1.3 Ausgangs-Backup (Storage)
Am Gerät **MENU → USB → STORAGE → CONNECT** wählen. Am PC erscheint das Laufwerk.
```powershell
uv run spikes/storage_spike.py backup --drive E: --name 00-ausgang --mem 98
```
Danach am Gerät die Verbindung trennen (EXIT, Bestätigung). Zusätzlich empfehle ich, einmal den kompletten `ROLAND`-Ordner von Hand nach `D:\RC 505 mk2 - Backup\2026-11-xx` zu kopieren. Das ist die Rückfallebene, falls etwas schiefgeht.

---

## 2. Test-Memory einrichten

Am Gerät **Memory 98** wählen und alle Spuren leeren. Dann einstellen:

**Rhythmus (sorgt für ein durchgehendes Taktraster)**
- Rhythmus **ON**, Tempo **104**, Pattern beliebig. Die Lautstärke darf leise sein, aber nicht 0.

**Memory Settings (LOOP) → REC**
- **REC ACTION = REC→PLAY.** So schaltet ein zweiter Druck auf Wiedergabe statt auf Overdub.
- **QUANTIZE = OFF** (Variante MEASURE testen wir in §5)
- **AUTO REC SW = OFF**

**Memory Settings (LOOP) → TRACK 1** (Track-Taste 1)
- **LOOP SYNC = ON**
- **MEASURE = AUTO** (auf 1 stellen wir in §5)
- **TEMPO SYNC SW = OFF.** Sonst würde das Gerät den Click umrechnen.
- **INPUT:** vorerst so lassen, wie es ist. §4 testet das gezielt.
- **1SHOT = OFF**, **REVERSE = OFF**, **START MODE = IMMEDIATE**

**MENU → ASSIGN → ASSIGN1**
- **SW = ON**
- **SOURCE = CC#21**
- **SOURCE MODE = MOMENT**
- **ACT. LO = 0**, **ACT. HI = 127**
- **TARGET = TRK1 REC/PLY**

**MENU → ASSIGN → ASSIGN2** (zum Gegentest)
- **SW = ON**, **SOURCE = CC#26**, **MODE = MOMENT**, **TARGET = TRK1 STOP**

**Memory WRITE ausführen.** Ohne WRITE sind Assigns und Einstellungen beim Memory-Wechsel weg.

### 2.1 Backup nach dem Einrichten → Kodierung der Assigns (A6)
STORAGE → CONNECT, dann:
```powershell
uv run spikes/storage_spike.py backup --drive E: --name 01-eingerichtet --mem 98
uv run spikes/storage_spike.py diff backups/00-ausgang backups/01-eingerichtet --mem 98 > diff-01.txt
```
Verbindung trennen. Die Datei `diff-01.txt` zeigt jeden geänderten Wert, zum Beispiel `mem/ASSIGN1/B 0 -> 21`. Damit ist die Kodierung der Assigns gefunden. Bitte die Datei aufheben und mitschicken.

---

## 3. Aufnahme per CC (A2) ⚠️ Abbruchkriterium

Das Gerät ist **nicht** im Storage-Modus, Memory 98 ist gewählt.

### 3.1 Ohne laufenden Takt
```powershell
uv run spikes/live_spike.py cc --cc 21 --release
```
**Beobachte:** Leuchtet Spur 1 rot (Aufnahme)? Dann ein paar Sekunden ins Mikro sprechen oder klatschen und denselben Befehl erneut senden. Die Spur sollte jetzt auf grün wechseln (Wiedergabe).

Dann stoppen:
```powershell
uv run spikes/live_spike.py cc --cc 26 --release
```

### 3.2 Wenn nichts passiert, der Reihe nach prüfen
1. **Kanal:** MENU → MIDI → RX CH → CTL. Steht er nicht auf 1, `--channel` passend setzen (Kanal 1 = `0`, Kanal 2 = `1` usw.).
2. **WRITE vergessen?** Memory einmal wechseln und zurück. Ist ASSIGN1 noch gesetzt?
3. **Ohne `--release`:** `uv run spikes/live_spike.py cc --cc 21`, dann `uv run spikes/live_spike.py cc --cc 21 --value 0`
4. **SOURCE MODE = TOGGLE** ausprobieren (WRITE!), dann nur `--value 127` senden.
5. **Gegenprobe mit anderem Ziel:** ASSIGN1 TARGET = **TAP TEMPO** oder **ALL ST/STP**. Reagiert das Gerät darauf, kommt MIDI an und nur das Ziel ist falsch gewählt.
6. **Kommt MIDI überhaupt an?** Am Gerät MENU → MIDI → THRU = USB OUT setzen und einen MIDI-Monitor laufen lassen (z. B. MIDI-OX). Alternativ einen Program Change testen, das wechselt das Memory. Diese Funktion hat das Skript noch nicht, bei Bedarf baue ich sie ein.

| Ergebnis 3 | Bedeutung |
|---|---|
| Spur startet und wechselt auf Wiedergabe | ✅ A2 erfüllt, weiter mit §4 |
| Funktioniert nur mit einem bestimmten Modus oder ohne `--release` | ✅ notieren, welche Kombination |
| Nichts davon funktioniert, auch 3.2 nicht | ❌ Abbruchkriterium. Hier aufhören und Teil B (§7/§8) trotzdem machen. |

---

## 4. Landet USB-Audio auf der Zielspur? (A1)

Der PC hat vier getrennte Ausgänge zur RC: **MAIN, MIC, INST1, INST2**. Die Spuren kennen als Eingang aber nur **MIC1, MIC2, INST1, INST2, RHYTHM**. Wir testen, welcher PC-Ausgang auf welchem Spur-Eingang ankommt.

**Vorbereitung:** **ALL START** am Gerät drücken, damit der Rhythmus und die Clock laufen. Den Drop-Befehl startest du jeweils während der Takt läuft. Das Skript nimmt dann automatisch einen Takt auf: CC → Click → CC.

Pro Zeile in der Tabelle:
1. Den **INPUT von TRACK 1** wie angegeben einstellen (Memory Settings → TRACK 1 → INPUT, nur der genannte Eingang auf ON, alle anderen OFF).
2. Spur 1 leeren (CLEAR).
3. Befehl ausführen, `--device` laut Tabelle. Der Name muss „RC-505mk2“ enthalten, sonst ist er nicht eindeutig (z. B. passt „MIC“ auch auf das Steam-Mikrofon):
   ```powershell
   uv run spikes/live_spike.py drop --wav click_1bar.wav --cc 21 --close-cc --release --device "RC-505mk2 INST2 WASAPI"
   ```
4. Anhören: Hörst du den Click auf Spur 1? Am besten den Rhythmus kurz stummschalten oder das Spur-Level hochziehen.

| # | PC-Ausgang (`--device`) | TRACK 1 INPUT | Click auf Spur 1? |
|---|---|---|---|
| 4a | `"RC-505mk2 INST2 WASAPI"` | nur INST2 L/R | |
| 4b | `"RC-505mk2 INST2 WASAPI"` | nur MIC 1 | |
| 4c | `"RC-505mk2 INST1 WASAPI"` | nur INST1 L/R | |
| 4d | `"RC-505mk2 MIC WASAPI"` | nur MIC 1 | |
| 4e | `"RC-505mk2 MAIN WASAPI"` | alle Eingänge **OFF** | |
| 4f | `"RC-505mk2 MAIN WASAPI"` | nur INST2 L/R | |

**Interpretation**
- **4a ja und 4b nein:** Die PC-Ausgänge hängen an den Eingängen. Dann ist A1 gelöst: INST2 ist der Drop-Kanal und wird nur der Zielspur gegeben.
- **4e ja:** MAIN geht immer auf jede Spur, unabhängig vom INPUT. Dann landet ein Drop über MAIN auf allen Spuren, die gerade aufnehmen. Das ist okay, solange beim Drop sonst nichts aufnimmt.
- **Alles nein:** USB → ROUTING = LOOP IN und INPUT LEVEL prüfen, das richtige Gerät per `list` kontrollieren.

**Zusatzprobe, falls 4a funktioniert:** TRACK 2 INPUT = nur MIC 1, TRACK 1 INPUT = nur INST2. Ins Mikro sprechen, während der Drop auf Spur 1 läuft. Danach prüfen: Ist die Stimme auf Spur 1 gelandet? Sie sollte es nicht sein.

---

## 5. Schließt das Gerät selbst? MEASURE und QUANTIZE (A3)

Den passenden PC-Ausgang aus §4 verwenden. Unten steht beispielhaft INST2.

### 5a – MEASURE schließt die Aufnahme
TRACK 1 → **MEASURE = 1**, Spur 1 leeren, WRITE nicht nötig. Achtung: **ohne** `--close-cc`:
```powershell
uv run spikes/live_spike.py drop --wav click_1bar.wav --cc 21 --release --device "RC-505mk2 INST2 WASAPI"
```
**Beobachte:** Wechselt Spur 1 nach genau einem Takt von selbst auf grün?

Gegenprobe: MEASURE = 2 und `click_2bar.wav` verwenden.

### 5b – QUANTIZE = MEASURE
REC → **QUANTIZE = MEASURE**, Spur 1 leeren. Der CC wird 30 ms früher gesendet, das Gerät rastet auf den Taktanfang ein:
```powershell
uv run spikes/live_spike.py drop --wav click_1bar.wav --cc 21 --release --cc-lead-ms 30 --device "RC-505mk2 INST2 WASAPI"
```
**Beobachte:** Startet die Aufnahme sauber auf Schlag 1 und nicht erst einen Takt später?

| Test | Ergebnis |
|---|---|
| 5a MEASURE=1 schließt selbst | |
| 5a MEASURE=2 mit 2-Takt-Click | |
| 5b QUANTIZE=MEASURE + 30 ms Vorlauf | |
| Ausgabe „REC-CC gesendet … ms vor dem Downbeat“ | |
| Ausgabe „Stream-Latenz laut PortAudio“ | |

---

## 6. Genauigkeit messen (Timing)

Die beste Kombination aus §5 nehmen. Meist ist das MEASURE = 1 ohne `--close-cc`, mit oder ohne QUANTIZE.

1. Drop wie in §5 ausführen, `--offset-ms 0`.
2. Am Gerät **STORAGE → CONNECT**.
3. Messen:
   ```powershell
   uv run spikes/live_spike.py xcorr --ref click_1bar.wav --rec "E:/ROLAND/WAVE/098_1/098_1.WAV"
   ```
4. Verbindung trennen, Spur 1 leeren.
5. Mit dem vorgeschlagenen Wert wiederholen, zum Beispiel `--offset-ms -12.3`. Das Vorzeichen übernimmst du genau so, wie es ausgegeben wird.
6. **Mindestens 5 Durchläufe** mit demselben Offset und alle Werte notieren.

| Lauf | --offset-ms | Versatz (ms) | Längen-Δ (Frames) |
|---|---|---|---|
| 1 | 0 | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

**Bewertung**
- **Längen-Δ ≈ 0:** Die Loop-Länge stimmt, MEASURE funktioniert.
- **Versatz nach der Kalibrierung ≤ 5 ms und Streuung ≤ 2 ms:** ✅ Eine einmalige Kalibrierung reicht.
- **Streuung > 5 ms:** Jitter. Bitte die rohen Zahlen schicken, dann passe ich die Strategie an (etwa längerer Vorlauf oder QUANTIZE).

**Optional – ASIO statt WASAPI:** `$env:SD_ENABLE_ASIO=1`, dann `uv run spikes/live_spike.py list`. Wenn ein ASIO-Gerät „RC-505mk2“ erscheint, die Messung damit wiederholen. ASIO hat oft eine kleinere und stabilere Latenz. Bei ASIO ist es ein einziges Gerät mit 8 Kanälen. Dafür kommt `--device "RC-505mk2 ASIO"` plus `--ch0 6` für INST2 dazu (die Kanalzuordnung zeigt `list`).

---

## 7. Was ändert eine echte Aufnahme in den Dateien? (A5, Referenz für A4)

Die Aufnahmen aus §6 liegen schon auf dem Gerät. Jetzt ein „sauberer“ Stand:
1. Am Gerät: Spur **3** in Memory 98 leeren. Dann von Hand **genau 1 Takt** aufnehmen (MEASURE = 1 bei TRACK 3), egal was. **WRITE.**
2. STORAGE → CONNECT:
   ```powershell
   uv run spikes/storage_spike.py backup --drive E: --name 02-echte-aufnahme --mem 98
   uv run spikes/storage_spike.py diff backups/01-eingerichtet backups/02-echte-aufnahme --mem 98 > diff-02.txt
   ```
3. Trennen.

`diff-02.txt` zeigt:
- Welche **A/B-Datei** das Gerät geschrieben hat und wie sich `count` verändert hat (A5)
- Welche Werte unter `mem/TRACK3/...` sich durch die Aufnahme geändert haben. Das sind die Felder, die ein Import setzen muss (A4).
- Die Größe der neuen WAV

---

## 8. Akzeptiert das Gerät eine selbst geschriebene WAV? (A4)

Wir schreiben den Click auf eine **leere** Spur, zuerst nur die WAV, dann zusätzlich die Länge in der `.RC0`. Vor jedem Schreiben legt das Werkzeug selbst ein Backup unter `backups/auto-vor-write-…` an.

### 8a – Nur WAV
Am Gerät Spur **4** leeren, WRITE. STORAGE → CONNECT:
```powershell
uv run spikes/storage_spike.py write-wav --drive E: --mem 98 --track 4 --src click_1bar.wav
```
Trennen. Am Gerät: Wird Spur 4 als belegt angezeigt? Spielt sie den Click? Gibt es eine Fehlermeldung, etwa „UNSUPPORTED“?

### 8b – WAV plus Länge in der `.RC0`
Wenn 8a nicht funktioniert hat: Spur **5** leeren, WRITE. STORAGE → CONNECT:
```powershell
uv run spikes/storage_spike.py write-wav --drive E: --mem 98 --track 5 --src click_1bar.wav --set-frames
```
Trennen und prüfen wie in 8a.

### 8c – Was hat das Gerät danach selbst geändert?
STORAGE → CONNECT:
```powershell
uv run spikes/storage_spike.py backup --drive E: --name 03-nach-import --mem 98
uv run spikes/storage_spike.py diff backups/02-echte-aufnahme backups/03-nach-import --mem 98 > diff-03.txt
```

| Test | Spur belegt? | Spielt korrekt? | Meldung am Gerät |
|---|---|---|---|
| 8a nur WAV | | | |
| 8b WAV + TRACKn/X | | | |

Wenn 8b nicht klappt, ist das kein Abbruch. Dann vergleichen wir `diff-02.txt` (echte Aufnahme) mit dem, was 8b gesetzt hat, und ergänzen die fehlenden Felder.

---

## 9. Was du mir schicken solltest

1. `spikes/S1-protokoll.md` mit den ausgefüllten Tabellen
2. `diff-01.txt`, `diff-02.txt`, `diff-03.txt`
3. Die Konsolenausgaben der Drops aus §5/§6. Kopieren reicht, wie beim letzten Mal.

Wenn du `backups/` und die `diff-*.txt` nicht im Repo haben willst, trag sie in die `.gitignore` ein.

## 10. Entscheidungstabelle

| Ergebnis | Konsequenz |
|---|---|
| A2 ❌ | Live-Teil streichen. Weiter mit Phase 1, das Projekt wird offline-only. ADR-0001 tritt ein. |
| A2 ✅, A1 4a ✅ | INST2 wird der Drop-Kanal. Das Assign-Profil setzt zusätzlich den Spur-INPUT. |
| A2 ✅, A1 nur über MAIN | Während eines Drops darf keine andere Spur aufnehmen. Das wird in der UI gesperrt. |
| A3 ✅ (MEASURE schließt) | ADR-0002 bestätigt. |
| A3 ❌ | ADR-0002 wird angepasst: Der Fallback `--close-cc` wird zum Standard. |
| Timing stabil ≤ 5 ms | Kalibrierung wird ein einmaliger Assistent in der App. |
| Timing streut | Neue Strategie (QUANTIZE + Vorlauf). Darüber sprechen wir. |
| 8a ✅ | Import = nur WAV schreiben, sehr einfach |
| 8b ✅ | Import = WAV + `TRACKn/X`, wie in der Spec geplant |
| 8a/8b ❌ | Fehlende Felder aus `diff-02.txt` ergänzen und erneut testen |
