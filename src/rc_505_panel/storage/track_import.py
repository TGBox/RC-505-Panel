"""Sample auf eine Spur importieren (C7).

Ergebnis aus Spike S2: Es reicht, die WAV im RC-Format nach WAVE/nnn_t/nnn_t.WAV zu schreiben.
Die `.RC0` wird nicht angefasst – das Gerät ergänzt Länge/Tempo (TRACKn U/V/W/X) beim Laden selbst.
Voraussetzung: Die WAV ist exakt N Takte lang und passt zum Memory-Tempo (ADR-0004).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..audio.rcwav import write_rc_wav
from ..audio.stretch import render_file
from ..audio.tempo import TempoEstimate
from ..core.models import TrackRef
from .backup import backup_memory, find_roland_root


@dataclass(frozen=True)
class ImportResult:
    wav_path: Path
    frames: int
    bars: int
    target_bpm: float
    backup_dir: Path
    tempo: TempoEstimate | None = None


def import_samples(roland: Path, ref: TrackRef, samples: np.ndarray, bars: int, target_bpm: float,
                   backup_root: Path | None = None) -> ImportResult:
    """Schreibt bereits gerenderte Samples (44,1 kHz, Stereo, exakte Taktlänge) auf die Spur."""
    roland = Path(roland)
    backup_dir = backup_memory(roland, ref.memory, backup_root, label=f"vor-import-spur{ref.track}")
    folder = roland / "WAVE" / ref.wave_dir_name
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{ref.wave_dir_name}.WAV"
    frames = write_rc_wav(target, samples)
    return ImportResult(target, frames, bars, target_bpm, backup_dir)


def import_file(drive: str | Path, ref: TrackRef, src: Path, target_bpm: float, bars: int | None = None,
                src_bpm: float | None = None, backend: str = "auto",
                backup_root: Path | None = None, cache_dir: Path | None = None) -> ImportResult:
    """Datei laden → Tempo bestimmen → auf target_bpm stretchen → exakte Takte → auf die Spur schreiben."""
    from ..audio.rcwav import read_rc_wav

    roland = find_roland_root(drive)
    clip, est = render_file(Path(src), target_bpm, bars, src_bpm, backend, cache_dir)
    samples = read_rc_wav(clip.path)
    res = import_samples(roland, ref, samples, clip.bars, target_bpm, backup_root)
    return ImportResult(res.wav_path, res.frames, res.bars, res.target_bpm, res.backup_dir, est)
