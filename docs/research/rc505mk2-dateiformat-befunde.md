# RC-505mkII – Dateiformat-Befunde (aus echtem Backup, 2026-11-18)

Quelle: `D:\RC 505 mk2 - Backup\ROLAND` (Stichprobe: MEMORY001A/B, SYSTEM1, WAVE 005_1, 002_3)

## Dateistruktur

- `ROLAND/DATA/MEMORY001A.RC0` … `MEMORY099B.RC0` – **zwei Kopien pro Memory (A/B)**, je ~273 KB
- `ROLAND/DATA/SYSTEM1.RC0`, `SYSTEM2.RC0` (ebenfalls doppelt), `RHYTHM.RC0` (~2 MB)
- `ROLAND/WAVE/001_1/001_1.WAV` … `099_5/099_5.WAV` + `ROLAND/WAVE/TEMP/`
- Leere Spur = leerer Ordner (keine WAV-Datei)

## .RC0-Format

- XML-artig, `<database name="RC-505MK2" revision="0">`, darin `<mem id="0">`, `<ifx>`, `<tfx>`
- **Nicht wohlgeformt:** Nach `</database>` folgt `<count>0008</count>` → Standard-XML-Parser scheitern; Count separat behandeln
- **A/B-Doppelpuffer:** Die Datei mit dem höheren `<count>` ist die aktuelle (001A=0007, 001B=0008). Beim Schreiben: ältere überschreiben, Count +1 (Hypothese – am Gerät verifizieren)
- Parameter-Tags sind anonym: `<A>`, `<B>`, … → Bedeutung muss gegen das Parameter Guide / per Diff am Gerät gemappt werden
- `NAME`: 12 Zeichen als ASCII-Codes (`77 101 109 111 114 121 48 49` = "Memory01")
- Sektionen pro Memory: `TRACK1`–`TRACK6` (!), `MASTER`, `REC`, `PLAY`, `RHYTHM`, `ICTL*`, `ECTL_*`, `ASSIGN1`–`ASSIGN16`, `INPUT`, `OUTPUT`, `ROUTING`, `MIXER`, `EQ_*`, `MASTER_FX`, FX-Bänke `AA_*`…`DD_*` (2112 FX-Sektionen)
- `TRACKn/<X>` = sehr wahrscheinlich Wave-Länge in Frames (001B Track1: 1.336.560 Frames ≙ 10.692.480 Byte Audio ≙ exakt die Dateigröße 10.747.904 nach Header + Padding) → **muss beim WAV-Import mitgeschrieben werden** (an weiteren Spuren bestätigen)

## WAV-Format (byteidentisch nachgebaut, verifiziert)

- `RIFF` (Größe = Datei − 8) · `WAVE`
- `fmt`-Chunk mit **28 Byte**: Format 3 (IEEE Float), 2 Kanäle, 44.100 Hz, 352.800 B/s, Block 8, 32 Bit, danach 12 Byte Extra `0a 00 00 00 00 00 00 00 00 00 00 00`
- `data`-Chunk-Header bei Offset 48, **Samples ab Offset 56** (interleaved float32 L/R)
- Danach `JUNK`-Chunk (8 Byte Header + Nullen), sodass die Dateigröße ein **Vielfaches von 262.144 Byte (256 KB)** ist (nicht 512 KB wie in Spec v1)
- Alle ~430 WAVs im Backup sind exakte 256-KB-Vielfache
- Nachbau mit diesem Schema ist für 005_1.WAV und 002_3.WAV **byteidentisch** zum Original (siehe `spikes/rcwav_prototype.py`)

## Offene Punkte

- Randfall Padding = 0 Byte (JUNK weglassen oder vollen Block anhängen?)
- Akzeptiert das Gerät auch Standard-WAVs ohne Padding / mit 16/24 Bit? (BTS for RC importiert diese – evtl. konvertiert BTS)
- Bedeutung der anonymen Tags (TRACK, ASSIGN, ROUTING)
- Welche `.RC0`-Felder außer `TRACKn/X` muss ein Import anpassen, damit das Gerät die Spur als belegt erkennt? (Spike S2)

## Update 2026-11-25 (Diff `00-ausgang` → `01-eingerichtet`, Memory 98)
- **`<count>` ist hexadezimal** (`000D`, `000E` → `000F`, `0010`).
- **A/B (A5 bestätigt):** Pro WRITE schreibt das Gerät in den *älteren* Slot und vergibt den nächsten Count. Bei zwei Speichervorgängen wurde abwechselnd A (`000F`), dann B (`0010`) geschrieben.
- **ASSIGN-Kodierung (A6, teilweise):**
  - `ASSIGNn/A` = SW (0 = OFF, 1 = ON)
  - `ASSIGNn/C` = SOURCE als Index. CC#21 → 59, CC#26 → 64, also **Index = 38 + CC-Nummer** für CC#01–31. Das passt zur Liste im Parameter Guide: 30 Spur-Quellen + 3 Sync/Knob + 6 CTL/EXP = 39 Einträge vor CC#01.
  - `ASSIGNn/H` = TARGET als Index: 0 = TRK1 REC/PLY, 2 = TRK1 STOP (also vermutlich 1 = TRK1 PLY/STP)
  - SOURCE MODE und ACT LO/HI sind bei den Standardwerten (MOMENT, 0, 127) unverändert geblieben → vermutlich B/D/E mit Standard 0/0/127. Noch nicht belegt.
- **Vermutlich Tempo:** `MASTER/A` = Memory-Tempo × 10 (910 → 830, also 91,0 → 83,0 BPM). `MASTER/B` ≈ Taktlänge in Frames. Ebenso `TRACKn/U` = Spurtempo × 10, `TRACKn/V` = Taktlänge in Frames (116307 = 4 × 60/91 × 44100). `TRACKn/X` = Gesamtlänge in Frames (465228 = 4 Takte), `TRACKn/W` = 1, wenn die Spur Daten hat (Hypothese).
- Noch unklar: `REC/B` 1 → 0 (vermutlich QUANTIZE MEASURE → OFF), `TRACK1/J,M,R,S` (MEASURE, LOOP SYNC, TEMPO SYNC …), `RHYTHM/M`, `PLAY/F`, `MASTER/D`, `ifx/AD/A`.
