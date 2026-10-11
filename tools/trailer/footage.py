# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Find the good bits of a raw gameplay recording by *listening* to it.

MEGA SNAKE's sound effects are synthesized (audio.py), so we can rebuild each one
exactly and look for it in the recording's audio with normalized cross-correlation.
That tells us when you died, ate a golden apple, chained a combo, unlocked an
achievement, grabbed a power-up, and so on, with no video analysis at all.
Only needs the game audio in the recording (desktop audio / "Desktop Audio" in OBS).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

import audio
from audio import SR

DS = 4                 # analyse at SR / 4 = 11025 Hz
TEMPLATE_SECONDS = 0.30
THRESHOLD = 0.5

WEIGHTS = {"achievement": 6, "unlock": 4, "golden": 3, "powerup": 3, "teleport": 3, "freeze": 3, "portal": 2,
           "bomb": 3, "near_miss": 4, "curse": 2, "shrink": 1, "eat": 1}
LABELS = {"achievement": "ACHIEVEMENT UNLOCKED", "unlock": "HERE WE GO", "golden": "GOLDEN APPLE",
          "powerup": "POWER-UP", "teleport": "TELEPORT", "freeze": "FREEZE!", "portal": "PORTALS",
          "bomb": "BOOM", "near_miss": "TOO CLOSE", "curse": "CURSED: CONTROLS FLIPPED", "shrink": "SHRINK",
          "eat": ""}


def _templates() -> Dict[str, np.ndarray]:
    """Rebuild the game's SoundBank as raw float arrays (no mixer needed)."""
    real_make, real_channels = audio._make, audio.pygame.mixer.set_num_channels

    def as_array(mono, volume, reverb=0.2, width=0.5):
        m = audio._reverb(mono, reverb)
        return (m / (float(np.max(np.abs(m))) or 1.0)).astype(np.float32)

    audio._make = as_array
    audio.pygame.mixer.set_num_channels = lambda n: None
    try:
        bank = audio.SoundBank()
    finally:
        audio._make, audio.pygame.mixer.set_num_channels = real_make, real_channels
    out = {k: getattr(bank, k) for k in ("death", "eat", "golden", "powerup", "shrink", "bomb", "achievement",
                                         "portal", "curse", "freeze", "teleport", "unlock", "near_miss")}
    for i, s in enumerate(bank.combo_scale):
        out[f"combo{i + 2}"] = s
    return out


def _down(x: np.ndarray) -> np.ndarray:
    n = len(x) // DS * DS
    return x[:n].reshape(-1, DS).mean(axis=1)


def find_events(stereo: np.ndarray) -> Dict[str, List[float]]:
    """stereo float audio at audio.SR -> {sound name: [times in seconds]}."""
    sig = _down(stereo.mean(axis=1).astype(np.float64))
    sr = SR / DS
    nfft = 1 << int(np.ceil(np.log2(len(sig) + sr)))
    X = np.fft.rfft(sig, nfft)
    csum = np.concatenate([[0.0], np.cumsum(sig ** 2)])
    found: Dict[str, List[float]] = {}
    for name, tpl in _templates().items():
        t = _down(tpl[: int(SR * TEMPLATE_SECONDS)].astype(np.float64))
        t = t - t.mean()
        tn = np.linalg.norm(t) or 1.0
        corr = np.fft.irfft(X * np.conj(np.fft.rfft(t, nfft)), nfft)[: len(sig) - len(t)]
        energy = np.sqrt(np.maximum(csum[len(t):len(t) + len(corr)] - csum[: len(corr)], 1e-12))
        ncc = corr / (energy * tn)
        hits, i, gap = [], 0, int(0.2 * sr)
        cand = np.flatnonzero(ncc > THRESHOLD)
        for c in cand:
            if hits and c - hits[-1][0] < gap:
                if ncc[c] > hits[-1][1]:
                    hits[-1] = (c, ncc[c])
                continue
            hits.append((c, ncc[c]))
        if hits:
            found[name] = [round(float(c) / sr, 3) for c, _ in hits]
    # a combo note is also a (higher) eat: keep combos separate, drop eats that are really combos
    return found


def _score(found: Dict[str, List[float]], length: float) -> np.ndarray:
    sec = np.zeros(int(length) + 2)
    for name, times in found.items():
        w = WEIGHTS.get(name, 0)
        if name.startswith("combo"):
            w = 1 + int(name[5:]) * 0.25  # higher combo, better moment
        for t in times:
            sec[min(len(sec) - 1, int(t))] += w
    return np.convolve(sec, np.ones(3), mode="same")


def best_moments(found: Dict[str, List[float]], length: float, count: int = 12, avoid: float = -99) -> List[float]:
    score = _score(found, length)
    for s in range(len(score)):
        if abs(s - avoid) < 4:
            score[s] = -1
    picks: List[float] = []
    order = np.argsort(-score)
    for s in order:
        if score[s] <= 0 or len(picks) >= count:
            break
        if all(abs(s - p) >= 4 for p in picks):
            picks.append(float(s) + 0.5)
    missing = count - len(picks)
    for k in range(missing):  # quiet footage: fill with evenly spaced moments
        picks.append(length * (k + 1) / (missing + 1))
    top = sorted(picks[:8])
    return top + sorted(picks[8:])


def label_moments(found: Dict[str, List[float]], moments: List[float]) -> List[str]:
    labels = []
    for m in moments:
        best, bw = "", 0.0
        for name, times in found.items():
            near = [t for t in times if abs(t - m) < 1.6]
            if not near:
                continue
            if name.startswith("combo"):
                w, lab = 1 + int(name[5:]) * 0.25, f"COMBO x{name[5:]}"
            else:
                w, lab = WEIGHTS.get(name, 0), LABELS.get(name, "")
            if w > bw and lab:
                best, bw = lab, w
        labels.append(best)
    return labels
