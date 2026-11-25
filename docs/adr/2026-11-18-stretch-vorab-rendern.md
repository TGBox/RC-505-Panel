# ADR-0004: Time-Stretch immer vorab rendern

**Status:** Akzeptiert · Bibliothek entschieden am 2026-11-25 · **Datum:** 2026-11-18

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

## Entscheidung Bibliothek (Phase 1, 2026-11-25)

Umgesetzt in `audio/stretch.py` mit zwei Backends hinter `stretch(x, alpha, backend="auto")`:

- **Rubber Band (CLI, `--fine` = R3-Engine):** Standard, sobald `rubberband` im PATH liegt. Es wird die CLI genutzt, nicht `pyrubberband`. Das spart eine Python-Abhängigkeit.
- **Eigene WSOLA (numpy):** Fallback ohne zusätzliche Installation. Fenster 512/256, Suche ±128. Schläge bleiben damit ≤ 3,5 ms an ihrer Taktposition (mit 1024/512/±512 waren es bis zu 11 ms).

**Hörtest:** Freie Aufnahme `t.wav`, ca. 95 → 104 BPM (−8 %), Spur 5 in Memory 98. WSOLA zeigt leichte Verzerrungsartefakte, Rubber Band ist hörbar „ein wenig besser“. Übersteuerung wurde als Ursache ausgeschlossen (Spitze −2,5 dBFS).

## **Folgerungen**

- Rubber Band ist die empfohlene Installation. Die App weist darauf hin, wenn nur WSOLA verfügbar ist.
- Jedes Stretching um mehrere Prozent bleibt hörbar. Die UI bietet deshalb als Alternative **„Memory-Tempo an das Sample anpassen“** an (kein Stretch). Das ist sinnvoll, wenn das Sample die erste Spur eines Memory wird.
- Nach dem Rendern begrenzt `limit_peak` auf ≤ 0,98, falls Samples über 1,0 liegen (das Gerät würde sonst abschneiden).
