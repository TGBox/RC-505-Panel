import numpy as np

from rc_505_panel.core.models import SR, loop_frames


def click(bpm: float, bars: int) -> np.ndarray:
    n = loop_frames(bpm, bars)
    x = np.zeros((n, 2), np.float32)
    burst = (np.sin(2 * np.pi * 1000 * np.arange(441) / SR) * np.hanning(441)).astype(np.float32)
    beat = 60 / bpm * SR
    for i in range(bars * 4):
        s = int(round(i * beat))
        x[s:s + 441] += ((0.9 if i % 4 == 0 else 0.4) * burst)[: n - s, None]
    return x
