# UX Discovery: RC-505mkII Studio

**Datum:** 2026-11-18 · **Status:** Entwurf zur Review · **Scope:** Neues Produkt (persönliches Tool)

---

1. Problem Brief

- **Problem:** PC-Samples lassen sich nur über einen fehleranfälligen Handgriff als Loop auf die RC-505mkII bringen. Darum nutzt der Nutzer heute faktisch gar keine PC-Samples.
- **Betroffene:** Der Nutzer selbst, ein Live-Looper mit RC-505mkII und Windows-PC. Das Tool ist rein persönlich.
- **Heutige Alternative:**
  - Das Sample läuft am PC in Dauerschleife, der Audio-Ausgang hängt am Eingang der Loopstation.
  - Der Nutzer versucht, das Gerät zu synchronisieren, und drückt dann im richtigen Moment Start und Stopp.
- **Warum das scheitert:**
  - Das Timing hängt von der Reaktionszeit ab.
  - Der Sync ist manuell.
  - Die Tempi von Sample und Memory passen nicht zueinander.
  - Fehlversuche kosten Zeit und sind live sichtbar.
- **Bestehende Tools decken das nicht ab:**
  - BOSS Tone Studio for RC importiert WAVs zwar im Storage-Modus, kann aber kein Live-Einspielen.
  - Der kommerzielle RC-Editor für RC-600/505mk2 verwaltet Memories, Setlists und WAVs, ebenfalls ohne Live-Funktion.

1. Persona

## P1 – „Der Live-Looper-Entwickler“ (primär, einzige Persona)

| | |
| --- | --- |
| **Rolle & Kontext** | Spielt mit der RC-505mkII, sowohl in der Vorbereitung zu Hause als auch live. Ein Windows-PC steht neben dem Gerät. Ist selbst Entwickler und toleriert raue Kanten. |
| **Primäres Ziel** | Beliebige Samples taktgenau als Loop auf eine Spur bringen, vorab oder während ein Loop läuft. |
| **Emotionales Ziel** | Sich auf das Spielen konzentrieren statt auf das Timing von Klicks. Kein Bangen, ob der Loop sauber schließt. |
| **Pain Points** | Manueller Start und Stopp, Tempo-Mismatch, Menüarbeit am Gerät, kein Weg vom Sample-Ordner direkt zur Spur. |
| **Workaround heute** | PC-Wiedergabe plus manuelle Aufnahme am Gerät (siehe Problem Brief). |
| **Eingaben** | Maus oder Touch, Tastatur und Fußschalter oder MIDI-Controller. Alle sollen unterstützt werden. |
| **Evidenz** | Aussagen des Nutzers im Discovery-Gespräch vom 2026-11-18. Eine Person, also hohe Validität für genau diesen Nutzer. |

1. Jobs to Be Done

## **Funktional**

- **J1 (Vorbereitung):** *Wenn* ich ein Memory für einen Gig vorbereite, *will ich* ein beliebiges Sample auf eine Spur ziehen, *damit* es dort im richtigen Tempo und taktgenau als Loop liegt.
- **J2 (Performance):** *Wenn* bereits ein Loop läuft, *will ich* ein vorbereitetes Sample mit einer einzigen Aktion auf eine freie Spur fallen lassen, *damit* es ab dem nächsten Downbeat synchron mitläuft.
- **J3 (Steuerung):** *Wenn* ich spiele, *will ich* die Spuren (REC/PLAY, STOP, Level) vom PC oder Fuß aus steuern, *damit* ich nicht im Gerätemenü suchen muss.
- **J4 (Tempo):** *Wenn* ein Sample ein anderes Tempo hat als das Memory, *will ich*, dass es automatisch angepasst wird, *damit* ich nicht vorher in einer DAW stretchen muss.

**Emotional:** Ich will mich sicher fühlen, dass ein Drop klappt, auch vor Publikum.

**Sozial:** Ich will live professionell wirken: keine hörbaren Lücken oder Versätze, kein Herumfummeln.

| Job | Wichtigkeit | Zufriedenheit heute | Chance |
| --- | --- | --- | --- |
| J2 Live-Drop | hoch | sehr niedrig | **höchste** |
| J1 Vorbereitung | hoch | niedrig (manuell möglich, aber ohne Tempo und Länge) | hoch |
| J4 Tempo | hoch | sehr niedrig | hoch, Voraussetzung für J1 und J2 |
| J3 Steuerung | mittel | mittel (Gerät selbst) | mittel |

1. User Journeys

### 4a. Vorbereitung (J1 + J4)

| Phase | Heute | Zielbild |
| --- | --- | --- |
| Sample finden | Explorer oder DAW | Sample-Bibliothek im Tool, mit Vorhören am PC und erkannter BPM |
| Tempo anpassen | DAW, oder gar nicht | Automatisches Stretching auf das Memory-Tempo, mit BPM-Korrektur ×2 oder ÷2 |
| Auf Spur bringen | Live-Workaround, fehleranfällig | Drag & Drop auf eine Spur, das Tool schreibt WAV und `.RC0` im Storage-Modus |
| Prüfen | Am Gerät anhören | Waveform und Länge in Takten im Tool, danach am Gerät |

### 4b. Performance (J2 + J3)

| Phase | Heute | Zielbild |
| --- | --- | --- |
| Sample bereitstellen | Player-Fenster am PC | Bis zu 5 „Drop-Slots“ sind vorgeladen und schon auf das Tempo gestreckt |
| Auslösen | Start drücken und hoffen | Ein Klick, eine Taste oder ein Fußtritt auf „Drop → Spur N“ |
| Synchronisieren | Nach Gehör | Das Tool wartet über die MIDI-Clock auf den nächsten Downbeat |
| Loop schließen | Stopp im richtigen Moment drücken | Automatisch, vom Gerät über MEASURE oder vom Tool per CC |
| Weiterspielen | Konzentration ist weg | Status „Spur 3 spielt“ ist sichtbar, die Hände sind frei |

**Moment of Truth:** Der erste Live-Drop vor Publikum. Ein hörbarer Versatz zerstört dort das Vertrauen dauerhaft.

1. Erfolgsmessung (nur lokal, keine Analytics)

| Metrik | Ziel | Messung |
| --- | --- | --- |
| **North Star:** Erfolgreiche Live-Drops | ≥ 95 % ohne Nachkorrektur | Lokales Drop-Log (JSON): Zeitpunkt, Spur, Ergebnis |
| Timing-Versatz eines Drops | ≤ 5 ms (≈ 220 Samples) | Kalibrierung über Kreuzkorrelation zwischen der Quell-WAV und der WAV, die das Gerät danach im Storage-Modus zurückgibt |
| Zeit vom Sample bis zum Loop (Vorbereitung) | < 30 s | Manuell gestoppt |
| Fehlgeschlagene Imports (Gerät lehnt ab) | 0 | Test am Gerät |

1. Einsichten & Designprinzipien

1. **Das Risiko zuerst.** Live-Timing und USB-Routing sind ungeklärt, ein Spike kommt vor jeder GUI.
1. **Offline ist die verlässliche Variante.** Was vorbereitet werden kann, geht über den Storage-Modus, samplegenau und ohne Latenz. Live ist für das Spontane.
1. **Schwere Arbeit vorher, nicht im Moment.** Stretching und Konvertierung laufen im Hintergrund, wenn ein Sample in einen Slot kommt. Der Drop selbst spielt nur ab.
1. **Eine Aktion, viele Eingaben.** Jede Funktion ist eine Action. Maus, Tastatur und MIDI sind austauschbare Auslöser.
1. **Das Gerät macht, was es kann.** Quantisierung und Loop-Schluss übernimmt die RC-505 wo möglich selbst. Das Tool repliziert keine Gerätelogik.
1. **Nie Daten zerstören.** Vor jedem Schreibvorgang auf das Gerät wird ein Backup angelegt. `.RC0` wird roundtrip-treu bearbeitet: Es ändert sich nur, was geändert werden soll.

1. Annahmen & Risiken

| # | Annahme | Status | Wenn falsch |
| --- | --- | --- | --- |
| A1 | USB-Audio kann auf genau eine Spur aufgenommen werden, ohne Mic- oder Line-Eingang zu verlieren | **Risiko**: Ein Community-Bericht sagt, dass USB und Mic/Line gekoppelt sind | Auto-Drop nur mit stummgeschalteten Eingängen, oder Workaround über ROUTING in der `.RC0` |
| A2 | MIDI-CC kann REC/PLAY per Assign auslösen, die Clock kommt über USB-MIDI | Plausibel, ungeprüft | Kein Auto-Drop möglich, das Tool bleibt ein Offline-Tool |
| A3 | Der Loop-Schluss lässt sich über MEASURE am Gerät steuern | Ungeprüft | Fallback: zweiter CC zum berechneten Zeitpunkt |
| A4 | Eine selbst geschriebene WAV (32f, 256-KB-JUNK-Padding) plus `TRACKn/X` wird vom Gerät akzeptiert | Format im Backup belegt, Schreiben ungetestet | Weitere `.RC0`-Felder per Diff ermitteln |
| A5 | A/B-Puffer: Die Datei mit dem höheren `<count>` gewinnt | Hypothese | Datenverlust möglich, daher Backup-Pflicht |
| A6 | Die anonymen Tags `<A>…` lassen sich per Diff am Gerät zuordnen | Plausibel, mit Aufwand | Nur die nötigen Felder mappen, nicht alle |
| A7 | Die USB-Audio-Kanalzahl reicht (8×8?) | Ungeprüft | Stereo reicht für Auto-Drop |
| A8 | Die Stretch-Qualität ist mit Python-Bibliotheken ausreichend | Ungeprüft | Rubber Band als CLI einbinden |

1. Nächste Schritte

1. Discovery-Dokument reviewen.
1. **Live-Spike** (siehe Spec §6): beantwortet A1, A2, A3 und A7.
1. **Storage-Spike**: eine WAV auf eine leere Spur schreiben und am Gerät abspielen. Beantwortet A4 und A5.
1. Danach Architektur einfrieren und Phase 1 starten.
