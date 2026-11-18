# RC-505-Panel (RC-505mkII Studio)

Windows-Desktop-Tool, das PC-Samples tempo- und taktgenau auf die Spuren der BOSS RC-505mkII bringt:
- vorab im Storage-Modus,
- live per USB-Audio und MIDI („Auto-Drop“).

**Status:** Discovery und Spec abgeschlossen. Als Nächstes kommt Phase 0 (Spikes S1/S2).

## Dokumente
- [Spec v2](docs/spec/rc505mk2-studio-spec.md): maßgeblich. Enthält One-Pager, MVP und Not-Doing, Schnittstellen, Akzeptanzkriterien, Spikes und Roadmap.
- [UX Discovery](docs/ux-discovery/2026-11-18-rc505mk2-studio-discovery.md): Persona, JTBD, Journeys, Metriken, Annahmen.
- [Dateiformat-Befunde](docs/research/rc505mk2-dateiformat-befunde.md): `.RC0`- und WAV-Format aus dem echten Backup.
- [ADRs](docs/adr/): Architekturentscheidungen 0001–0005.
- [Spec v1](docs/spec/rc_505mkii_studio_architektur_spezifikation_v1.md): ursprünglicher Entwurf, durch v2 ersetzt.

## Spikes
- `spikes/rcwav_prototype.py`: WAV-Writer im RC-Format. Auf Backup-WAVs angewendet ergibt er eine byteidentische Datei.
  `python spikes/rcwav_prototype.py "D:\RC 505 mk2 - Backup\ROLAND\WAVE\005_1\005_1.WAV"`
