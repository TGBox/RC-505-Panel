# ADR-0004: Time-Stretch immer vorab rendern

**Status:** Akzeptiert (die Wahl der Bibliothek ist offen) · **Datum:** 2026-11-18

## Kontext

Die Samples des Nutzers haben uneinheitliche BPM, das Stretching ist also Pflicht. Für den Live-Drop ist Latenz kritisch, und Python ist für Echtzeit-DSP ungeeignet.

## Optionen

1. Echtzeit-Stretch im Audio-Callback
2. **Vorab-Rendern, sobald ein Sample einem Slot oder einer Spur zugewiesen wird (Hintergrund-Thread, Cache nach Hash aus Quelle, BPM und Takten)**

## Entscheidung

Option 2. Eine Neuberechnung ist nötig, wenn sich das Memory-Tempo ändert. Die UI zeigt dann den Status „Slot wird gerendert…“, und der Drop-Button ist deaktiviert, bis das Rendern fertig ist.

**Bibliothek, wird in Phase 1 per Hörtest entschieden:**

- `pyrubberband`: beste Qualität, braucht die Rubber-Band-CLI
- Pure-Python-Lösung (WSOLA/Phase-Vocoder): keine zusätzliche Abhängigkeit, schlechtere Qualität

## Konsequenzen

- **Plus:** Der Drop spielt nur noch eine fertige Datei ab und verursacht keine DSP-Last. Die Länge ist auf den Frame genau definiert (AC5). Offline-Import und Live-Drop nutzen denselben Renderer.
- **Minus:** Ein spontaner Tempowechsel während der Performance macht die Slots ungültig, bis sie neu gerendert sind.
