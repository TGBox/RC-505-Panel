# ADR-0002: Loop-Schluss durch das Gerät, CC nur als Fallback

**Status:** Vorgeschlagen (wird in Spike S1 validiert) · **Datum:** 2026-11-18

## Kontext

Spec v1 sieht vor, dass die Software nach Ablauf der Sample-Dauer einen zweiten CC (REC/PLAY) samplegenau sendet. Das stößt auf drei Probleme:

- MIDI über USB hat Jitter.
- Python-Threads haben keine garantierte Echtzeit.
- Jeder Versatz wird als Loop-Länge eingefroren und ist danach dauerhaft hörbar.

## Optionen

1. Zweiter CC zum berechneten Zeitpunkt (v1)
2. **MEASURE der Zielspur auf N Takte setzen, damit das Gerät die Aufnahme selbst am Taktende beendet**
3. MIDI-Clock-Master im Tool, dann CC auf einen Clock-Tick

## Entscheidung

Option 2 ist der Standard. Option 1 bleibt als Fallback, falls sich MEASURE für die Spur nicht vorab setzen lässt (über `.RC0` oder Assign) oder das Gerät nicht wie erwartet schließt.

## Konsequenzen

- **Plus:** Die Loop-Länge ist hardwaregenau. Das Tool muss nur noch den *Start* treffen, und den gleicht die Latenz-Kalibrierung aus.
- **Minus:** Die Spur braucht vorab den passenden MEASURE-Wert. Das ist ein Feld mehr im `.RC0`-Mapping, oder ein Assign.
- Der Clip muss exakt N Takte lang sein. Das ist durch ADR-0004 ohnehin gegeben.
