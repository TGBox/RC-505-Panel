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
