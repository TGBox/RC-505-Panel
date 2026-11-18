# ADR-0001: Erst der Spike, dann die Architektur

**Status:** Akzeptiert · **Datum:** 2026-11-18

## Kontext

Der Hauptnutzen des Tools ist der Live-Drop (J2). Er hängt von ungeprüften Geräteeigenschaften ab:

- Kann eine Aufnahme per MIDI-CC ausgelöst werden?
- Lässt sich USB-Audio unabhängig von Mic und Line routen?
- Schließt MEASURE die Aufnahme selbst?
- Wie viele USB-Kanäle stehen zur Verfügung?

Ein Community-Bericht deutet an, dass USB- und Mic/Line-Eingang gekoppelt sind. Die ursprüngliche Spec v1 enthielt außerdem nachweislich falsche Annahmen, etwa zu den Dateinamen und zum Padding.

## Optionen

1. Architektur und GUI nach Spec v1 bauen und Probleme unterwegs lösen.
2. Mit dem Offline-Teil anfangen (risikoarm) und Live später angehen.
3. **Zuerst zwei Headless-Spikes (Live und Storage), danach die Architektur einfrieren.**

## Entscheidung

Option 3. Das Spike-Skript wird nach Phase 0 verworfen.

## Konsequenzen

- **Plus:** Bevor viel Arbeit in die GUI fließt, wissen wir, ob Live überhaupt geht. Das Abbruchkriterium ist klar: kein REC per MIDI bedeutet offline-only.
- **Minus:** Für ein bis zwei Abende gibt es keinen sichtbaren Fortschritt in der App.
