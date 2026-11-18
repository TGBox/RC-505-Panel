# ADR-0003: Eigener roundtrip-treuer `.RC0`-Parser

**Status:** Akzeptiert · **Datum:** 2026-11-18

## Kontext

Was das echte Backup über `.RC0`-Dateien zeigt:

- Sie sind XML-artig, aber **nicht wohlgeformt**: Hinter `</database>` steht noch `<count>NNNN</count>`.
- Die Tags sind anonym (`<A>`, `<B>`, …).
- Pro Datei gibt es über 2.000 FX-Sektionen.
- Jedes Memory liegt doppelt vor (A/B), und der höhere `count` gewinnt.

Ein Datenverlust an der Loopstation wäre fatal.

## Optionen

1. `xml.etree` mit Vorverarbeitung, danach neu serialisieren
2. Vollständiges Objektmodell aller Parameter
3. **Text-basierter Parser: Er indiziert `(Sektion, Tag) → Byte-Spanne` und ersetzt nur die Werte, die geändert werden sollen. Alles andere bleibt Byte für Byte erhalten.**

## Entscheidung

Option 3. Ein dünnes Schema (`rc0_schema.py`) bildet nur die Felder ab, die wir wirklich brauchen, zum Beispiel `TRACKn.X` → `wave_frames`.

## Konsequenzen

- **Plus:** Der Roundtrip ist byteidentisch und testbar (AC1). Unbekannte Felder werden nie beschädigt, und die Formatierung bleibt erhalten (Tabs, `\n`).
- **Minus:** Es gibt kein bequemes Objektmodell. Neue Felder müssen von Hand ins Schema.
- Die A/B-Schreibstrategie ist eine Hypothese (Spike S2) und wird durch die Backup-Pflicht abgesichert.
