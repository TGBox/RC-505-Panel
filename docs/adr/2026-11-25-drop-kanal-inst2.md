# ADR-0006: USB-Drop über den Kanal INST2

**Status:** Akzeptiert · **Datum:** 2026-11-25

## Kontext
Ein Drop soll nur auf der Zielspur landen, ohne dass Mikro oder Instrumente auf anderen Spuren betroffen sind. Laut Parameter Guide ist USB kein Eingang einer Spur, die Spur-Eingänge sind nur MIC 1/2, INST1/2 und RHYTHM. Im Modus VENDOR stellt die RC-505mkII unter WASAPI aber vier Stereo-Ausgänge vom PC zum Gerät bereit: MAIN, MIC, INST1 und INST2.

## Befund (Spike S1, §4)
Geprüft wurde bei der Wiedergabe der Spur, nicht beim Mithören während der Aufnahme.

| PC-Ausgang | Spur-Eingang | Aufgenommen? |
|---|---|---|
| MAIN | alle aus | nein |
| INST2 | alle aus | nein |
| INST2 | nur INST2 | **ja** |
| INST2 | nur MIC 1 | nein |

Der PC-Ausgang INST2 kommt also genau am Spur-Eingang INST2 an.

## Optionen
1. Drop über MAIN: Das landet auf keiner Spur (siehe Befund), scheidet also aus.
2. **Drop über den PC-Ausgang INST2, und die Zielspur bekommt INPUT INST2 = ON**
3. Drop über MIC oder INST1: Das ginge vermutlich genauso, kollidiert aber eher mit echten Mikros und Instrumenten.

## Entscheidung
Option 2. INST2 ist der feste Drop-Kanal.

## Konsequenzen
- **Plus:** Ein Drop ist eindeutig auf eine Spur gerichtet, Mikro und INST1 bleiben frei für die Performance.
- **Minus:** Die Buchse INST2 am Gerät sollte für Drops frei bleiben. Ein dort eingestecktes Instrument würde vermutlich mit aufgenommen (nicht getestet).
- **Minus:** Spur-INPUT ist kein Assign-Ziel. Welche Spuren INST2 annehmen, legt das Assign-/Drop-Profil offline in der `.RC0` fest (TRACKn-Eingänge, Kodierung noch zu ermitteln).
- Ein Drop auf eine Spur ohne INST2-Eingang bleibt still. Die UI muss das anzeigen.
