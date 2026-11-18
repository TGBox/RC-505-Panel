# ADR-0005: Alle Eingaben über einen Action-Bus

**Status:** Akzeptiert · **Datum:** 2026-11-18

## Kontext

Der Nutzer will jede Funktion per Maus oder Touch, per Tastatur und per Fußschalter oder MIDI-Controller auslösen können.

## Optionen

1. Jede Eingabeart verdrahtet ihre Logik direkt mit dem Widget oder Handler
2. **Zentraler `ActionBus`: Eingabequellen erzeugen `Action`-Objekte, die Engines abonnieren sie. Die Bindings liegen in JSON.**

## Entscheidung

Option 2. Die GUI-Buttons dispatchen ebenfalls Actions, es gibt also keinen Sonderweg für die Maus.

## Konsequenzen

- **Plus:** Eine neue Eingabeart ist nur ein neuer Adapter, die Logik bleibt unberührt. Actions lassen sich ohne GUI testen und mitloggen (Drop-Log für die North-Star-Metrik).
- **Minus:** Eine Indirektionsschicht mehr.
- MIDI-Input braucht einen eigenen Port, damit Controller-Daten nicht mit dem Port der RC-505 kollidieren. Das wird in Phase 4 geklärt.
