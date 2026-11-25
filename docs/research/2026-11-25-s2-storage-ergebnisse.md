# Spike S2 – Storage-Ergebnisse (2026-11-25)

Grundlage: Backups `02-vorher` → `03-echte-aufnahme` → `04-nach-import` (Memory 98) sowie `diff-02.txt` und `diff-03.txt`.

## A4 ✅ Eine selbst geschriebene WAV wird akzeptiert, ohne dass wir die `.RC0` ändern

- §8a: `write-wav` hat nur `WAVE/098_4/098_4.WAV` geschrieben (RC-Format: 32f, fmt 28 Byte, JUNK-Padding auf 256 KB), ohne `--set-frames`. Danach Memory gewechselt und zurück.
- Die Spur wurde als belegt erkannt und spielte korrekt, ohne Fehlermeldung.
- **Das Gerät hat die `.RC0` danach selbst ergänzt** und dafür einen neuen Slot geschrieben (B: `0020` → `0022`):

| Feld | vorher | nach Import | gleich wie bei echter Aufnahme (Spur 3)? |
| --- | --- | --- | --- |
| TRACK4/J | 11 | 8 | ja |
| TRACK4/S | 4 | 1 | ja |
| TRACK4/U | 1200 | 1040 | ja (Tempo × 10 = 104,0) |
| TRACK4/V | 88200 | 101769 | ja (Frames pro Takt bei 104 BPM) |
| TRACK4/W | 0 | 1 | ja (Spur hat Daten) |
| TRACK4/X | 0 | 101769 | ja (Länge in Frames) |

**Folge:** Ein Import muss nur die WAV im RC-Format in `WAVE/xxx_y/` schreiben. Die Längen- und Tempofelder ergänzt das Gerät beim Laden selbst. `TRACKn/X` von Hand zu setzen (`--set-frames`, 8b) ist nicht nötig.
Voraussetzung, die wir eingehalten haben: Die WAV ist exakt N Takte lang und passt zum Memory-Tempo (ADR-0004).

## Bedeutung der TRACK-Felder (Stand jetzt)

- `U` = Spurtempo × 10 · `V` = Frames pro Takt · `X` = Gesamtlänge in Frames · `W` = 1, wenn die Spur Daten hat (bestätigt durch Aufnahme und Import)
- `S` = Anzahl Takte? (4 → 1 bei einem 1-Takt-Loop) · `J` 11 → 8: Bedeutung offen (Taktart oder MEASURE-Modus?)
- Nur bei der echten Aufnahme mit geänderten Spur-Einstellungen (INPUT nur MIC 1, MEASURE 1): `Q` 127 → 2, `R` 1 → 2, `PLAY/F` 0 → 2. Das sind Kandidaten für INPUT bzw. MEASURE und wichtig für ADR-0006 (Spur-INPUT INST2 per `.RC0`). Klären wir per gezieltem Einzel-Diff (ein Parameter pro Backup).

## A/B-Schreibreihenfolge (bestätigt)

- Echte Aufnahme + WRITE: A `001F` → `0021`, B unverändert.
- Laden der importierten WAV: B `0020` → `0022`. Das Gerät schreibt also auch ohne WRITE von sich aus, sobald es fehlende Metadaten ergänzt.
