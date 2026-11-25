import numpy as np
import pytest

from rc_505_panel.audio.rcwav import BLOCK, build_rc_wav, read_rc_wav, write_rc_wav
from rc_505_panel.audio.stretch import fit_length, limit_peak, render, stretch, wsola
from rc_505_panel.audio.tempo import bpm_from_filename, estimate_tempo, loop_candidates, onset_bpm
from rc_505_panel.core.models import SR, frames_per_bar, loop_frames

from .helpers import click


# ---------- Gerätekonventionen ----------

def test_frames_like_device():
    assert frames_per_bar(104) == 101769          # S2: TRACKn/V bei 104 BPM
    assert frames_per_bar(91) == 116307           # Backup: TRACKn/V bei 91 BPM
    assert loop_frames(91, 4) == 465228           # Backup: TRACKn/X, 4 Takte


# ---------- RC-WAV (AC2) ----------

@pytest.mark.parametrize("name", ["005_1.WAV", "002_3.WAV"])
def test_rcwav_rebuild_byte_identical(fixtures, name):
    raw = (fixtures / name).read_bytes()
    assert build_rc_wav(read_rc_wav(fixtures / name)) == raw


def test_rcwav_size_and_roundtrip(tmp_path):
    for n in (1, 1000, (BLOCK - 64) // 8, 101769):
        x = np.random.default_rng(n).standard_normal((n, 2)).astype(np.float32)
        p = tmp_path / "t.WAV"
        assert write_rc_wav(p, x) == n
        assert p.stat().st_size % BLOCK == 0
        assert np.array_equal(read_rc_wav(p), x)


# ---------- Tempo ----------

def test_bpm_from_filename():
    assert bpm_from_filename("Drums_128bpm_A.wav") == 128
    assert bpm_from_filename("loop 92.5 BPM.flac") == 92.5
    assert bpm_from_filename("kick_01.wav") is None


def test_loop_candidates_contains_true_tempo():
    bpms = [round(b, 3) for b, _ in loop_candidates(loop_frames(104, 2))]
    assert any(abs(b - 104) < 0.01 for b in bpms)


@pytest.mark.parametrize("bpm", [90.0, 104.0, 128.0])
def test_estimate_tempo_loop(bpm):
    est = estimate_tempo(click(bpm, 2))
    assert est.source == "loop"
    assert abs(est.bpm - bpm) / bpm < 0.005 and est.bars == 2
    assert est.onset_bpm is not None and min(abs(est.onset_bpm * k - bpm) for k in (0.5, 1, 2)) / bpm < 0.04


def test_onset_bpm_non_loop():
    x = click(100, 4)[: loop_frames(100, 4) - 5000]  # keine ganzen Takte
    b = onset_bpm(x)
    assert b is not None and min(abs(b * k - 100) for k in (0.5, 1, 2)) < 4


# ---------- Stretch (AC5) ----------

@pytest.mark.parametrize("src,dst,bars", [(90, 104, 1), (128, 104, 2), (104, 104, 1), (120, 83, 4)])
def test_render_exact_length(src, dst, bars):
    y, used = render(click(src, bars), src, dst, bars, backend="wsola")
    assert used == bars and len(y) == loop_frames(dst, bars) and y.dtype == np.float32


def test_wsola_keeps_beat_positions():
    """Nach dem Stretch liegen die Schläge an den Taktpositionen des Zieltempos (±5 ms)."""
    src, dst = 120.0, 100.0
    y, _ = render(click(src, 1), src, dst, 1, backend="wsola")
    env = np.abs(y.mean(axis=1))
    beat = 60 / dst * SR
    for i in range(4):
        c = int(round(i * beat))
        lo, hi = max(c - 2000, 0), c + 2000
        peak = lo + int(np.argmax(env[lo:hi]))
        assert abs(peak - (c + 220)) < 0.005 * SR, (i, peak, c)


def test_stretch_identity_and_fit_length():
    x = click(104, 1)
    assert stretch(x, 1.0) is not None and np.array_equal(stretch(x, 1.0), x)
    assert len(fit_length(x, 10)) == 10
    assert len(fit_length(x, len(x) + 7)) == len(x) + 7


def test_wsola_length():
    x = np.random.default_rng(0).standard_normal((44100, 2)).astype(np.float32) * 0.1
    for a in (0.5, 0.8, 1.25, 2.0):
        assert len(wsola(x, a)) == int(round(len(x) * a))


def test_limit_peak():
    x = np.array([[0.5, -0.5]], np.float32)
    assert limit_peak(x)[1] == 1.0
    y, g = limit_peak(np.array([[1.5, -2.0]], np.float32))
    assert g < 1 and abs(np.abs(y).max() - 0.98) < 1e-6


def test_render_never_exceeds_full_scale():
    y, _ = render(click(104, 1) * 3.0, 104, 90, 1, backend="wsola")
    assert np.abs(y).max() <= 1.0
