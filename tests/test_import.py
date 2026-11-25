import shutil

import numpy as np
import pytest

from rc_505_panel.audio.convert import write_float_wav
from rc_505_panel.audio.rcwav import read_rc_wav
from rc_505_panel.core.models import TrackRef, loop_frames
from rc_505_panel.storage.backup import backup_memory, find_roland_root, restore_memory
from rc_505_panel.storage.track_import import import_file, import_samples

from .helpers import click


@pytest.fixture
def roland(fixtures, tmp_path):
    """Minimales ROLAND-Laufwerk: Memory 1 mit Spur 1 belegt, Spuren 2–5 leer."""
    r = tmp_path / "drive" / "ROLAND"
    (r / "DATA").mkdir(parents=True)
    for n in ("MEMORY001A.RC0", "MEMORY001B.RC0"):
        shutil.copy(fixtures / n, r / "DATA" / n)
    for t in range(1, 6):
        (r / "WAVE" / f"001_{t}").mkdir(parents=True)
    shutil.copy(fixtures / "005_1.WAV", r / "WAVE" / "001_1" / "001_1.WAV")
    return r


def test_find_roland_root(roland):
    assert find_roland_root(roland.parent) == roland
    assert find_roland_root(roland) == roland
    with pytest.raises(FileNotFoundError):
        find_roland_root(roland / "DATA")


def test_import_writes_wav_and_leaves_rc0_untouched(roland, tmp_path):
    rc0_before = {p.name: p.read_bytes() for p in (roland / "DATA").iterdir()}
    x = np.full((loop_frames(104, 1), 2), 0.25, np.float32)
    res = import_samples(roland, TrackRef(1, 4), x, 1, 104, backup_root=tmp_path / "bk")
    assert res.wav_path == roland / "WAVE" / "001_4" / "001_4.WAV"
    assert np.array_equal(read_rc_wav(res.wav_path), x)
    assert {p.name: p.read_bytes() for p in (roland / "DATA").iterdir()} == rc0_before  # S2: RC0 nicht anfassen
    assert (res.backup_dir / "manifest.json").exists()


def test_backup_restore_exact(roland, tmp_path):
    """AC4: Nach einem Import stellt restore den Stand vorher exakt wieder her."""
    def snapshot():
        return {str(p.relative_to(roland)): p.read_bytes() for p in roland.rglob("*") if p.is_file()}
    before = snapshot()
    bk = backup_memory(roland, 1, tmp_path / "bk")
    import_samples(roland, TrackRef(1, 2), np.zeros((loop_frames(120, 1), 2), np.float32), 1, 120,
                   backup_root=tmp_path / "bk2")
    shutil.copy(roland / "WAVE" / "001_2" / "001_2.WAV", roland / "WAVE" / "001_1" / "001_1.WAV")
    assert snapshot() != before
    restore_memory(bk, roland)
    assert snapshot() == before


def test_import_file_end_to_end(roland, tmp_path):
    src = tmp_path / "beat_90bpm.wav"
    write_float_wav(src, click(90, 2))
    res = import_file(roland.parent, TrackRef(1, 3), src, target_bpm=104, backend="wsola",
                      backup_root=tmp_path / "bk", cache_dir=tmp_path / "cache")
    assert res.tempo.source == "filename" and res.tempo.bpm == 90
    assert res.bars == 2 and res.frames == loop_frames(104, 2)
    assert len(read_rc_wav(res.wav_path)) == loop_frames(104, 2)
