# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Procedural trailer music and stingers, built from the same synth voices the game
uses (audio.py), so the trailer sounds like MEGA SNAKE. Pure numpy, no samples.

Everything returns float32 stereo arrays at audio.SR.
"""
from __future__ import annotations

import numpy as np

from audio import SR, _bell, _pluck, _glide, _noise_whoosh, _lowpass, _reverb, _t

BPM = 128
BEAT = 60.0 / BPM
BAR = BEAT * 4
_rng = np.random.default_rng(42)

# A minor: Am - F - C - G
CHORDS = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (261.63, 329.63, 392.0), (196.0, 246.94, 293.66)]
ROOTS = [110.0, 87.31, 130.81, 98.0]


def _st(mono: np.ndarray, width: float = 0.0) -> np.ndarray:
    if width <= 0:
        return np.column_stack([mono, mono]).astype(np.float32)
    d = int(SR * 0.012 * width)
    r = np.concatenate([np.zeros(d), mono[:-d]]) if d else mono
    return np.column_stack([mono, r]).astype(np.float32)


def _place(buf: np.ndarray, sig: np.ndarray, t: float, gain: float = 1.0) -> None:
    i = int(t * SR)
    if i >= len(buf) or i + len(sig) <= 0:
        return
    if i < 0:
        sig, i = sig[-i:], 0
    n = min(len(sig), len(buf) - i)
    buf[i:i + n] += sig[:n] * gain


def kick() -> np.ndarray:
    t = _t(0.38)
    f = 46 + 110 * np.exp(-28 * t)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-7 * t)
    s[:60] += np.linspace(0.6, 0, 60)  # click
    return _st(np.tanh(s * 1.6))


def clap() -> np.ndarray:
    t = _t(0.28)
    n = _rng.standard_normal(len(t))
    band = _lowpass(n, 3500) - _lowpass(n, 900)
    env = np.exp(-16 * t)
    for off in (0.0, 0.011, 0.022):  # three quick hits = clap
        env += 0.6 * np.exp(-90 * np.clip(t - off, 0, None)) * (t >= off)
    s = band * env * 2.2 + 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-25 * t)
    return _st(_reverb(s, 0.35)[: int(SR * 0.45)], 0.6)


def hat(open_: bool = False) -> np.ndarray:
    t = _t(0.18 if open_ else 0.05)
    n = _rng.standard_normal(len(t))
    s = (n - _lowpass(n, 7000)) * np.exp(-(14 if open_ else 70) * t)
    return _st(s * 0.5, 0.3)


from functools import lru_cache


@lru_cache(maxsize=None)
def bass_note(freq: float, dur: float) -> np.ndarray:
    t = _t(dur)
    ph = 2 * np.pi * freq * t
    saw = sum(np.sin(h * ph) / h for h in range(1, 9))
    env = np.exp(-14 * t)  # filter "pluck": bright attack closing down
    s = (_lowpass(saw, 1300) * env + _lowpass(saw, 420) * (1 - env)) * np.minimum(1, t * 300) * np.exp(-1.5 * t)
    s[-200:] *= np.linspace(1, 0, 200)
    return _st(np.tanh(s * 1.4))


@lru_cache(maxsize=None)
def pad(chord, dur: float) -> np.ndarray:
    t = _t(dur)
    s = np.zeros_like(t)
    for f in chord:
        for det in (-0.35, 0.0, 0.4):
            ph = 2 * np.pi * (f * (1 + det / 100)) * t + _rng.uniform(0, 6.28)
            s += np.sin(ph) + 0.3 * np.sin(2 * ph)
    env = np.minimum(1, t / 0.4) * np.minimum(1, (dur - t) / 0.3)
    return _st(_lowpass(s, 1600) * env / 9, 1.0)


def impact() -> np.ndarray:
    t = _t(2.2)
    boom = np.sin(2 * np.pi * (38 + 90 * np.exp(-9 * t)) * t) * np.exp(-2.2 * t)
    noise = _noise_whoosh(1.2, 4000, 300)
    s = np.tanh(1.8 * boom)
    s[: len(noise)] += 0.5 * noise
    s += 0.35 * _bell(110, 2.2, 1.2)[: len(s)]
    return _st(_reverb(s, 0.5)[: len(t)] * 0.9, 0.8)


def riser(dur: float) -> np.ndarray:
    n = _noise_whoosh(dur, 300, 9000)
    n *= np.linspace(0.1, 1, len(n)) ** 2
    n[int(len(n) * 0.9):] *= np.linspace(1, 0, len(n) - int(len(n) * 0.9))
    g = _glide(200, 1400, dur, 2.2, 0.2) * np.linspace(0, 0.6, int(SR * dur)) ** 2
    m = min(len(n), len(g))
    return _st((n[:m] * 0.8 + g[:m]) * 0.7, 0.5)


def whoosh(dur: float = 0.35, up: bool = True) -> np.ndarray:
    return _st(_noise_whoosh(dur, 500 if up else 6000, 6000 if up else 500) * 0.7, 0.6)


def record_scratch() -> np.ndarray:
    """Vinyl stop: a squealing two-way pitch swipe over gritty noise."""
    dur = 0.42
    t = _t(dur)
    rate = np.interp(t, [0, 0.12, 0.2, 0.32, dur], [1.0, 2.6, 0.2, 1.8, 0.0])
    ph = 2 * np.pi * np.cumsum(420 * rate) / SR
    tone = np.sign(np.sin(ph)) * 0.25 + np.sin(ph * 2.01) * 0.4
    n = _rng.standard_normal(len(t))
    grit = (_lowpass(n, 4000) - _lowpass(n, 700)) * (0.6 + rate)
    s = (tone + grit * 0.8) * np.minimum(1, t * 200) * np.minimum(1, (dur - t) * 40)
    return _st(np.tanh(s * 1.5) * 0.8)


def rewind(dur: float) -> np.ndarray:
    """Tape rewind: a high, wobbling, accelerating chirp."""
    t = _t(dur)
    f = 600 + 2400 * (t / dur) ** 1.5 + 300 * np.sin(2 * np.pi * 23 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * 0.35 + np.sign(np.sin(ph * 0.5)) * 0.08
    n = _rng.standard_normal(len(t))
    s += (n - _lowpass(n, 3000)) * 0.25
    s *= np.minimum(1, t * 30) * np.minimum(1, (dur - t) * 20)
    return _st(s * 0.7, 0.4)


def drone(dur: float) -> np.ndarray:
    t = _t(dur)
    s = sum(np.sin(2 * np.pi * f * t + i) for i, f in enumerate((55.0, 82.41, 110.3)))
    s = _lowpass(s, 300) * np.minimum(1, t / 1.0) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.5 * t))
    return _st(s * 0.18, 0.5)


def song(sections) -> np.ndarray:
    """sections: [(kind, bars) or (kind, bars, riser)] with kind in
    intro | verse | build | break | drop | end. Bar boundaries line up with the video cuts;
    riser=True rolls a snare + noise riser over the section's last bar."""
    total = sum(sec[1] for sec in sections) * BAR + 4.0
    buf = np.zeros((int(total * SR), 2), np.float32)
    K, C, H, HO = kick(), clap(), hat(), hat(True)
    t0 = 0.0
    bar_i = 0
    for sec in sections:
        kind, bars = sec[0], sec[1]
        rise = sec[2] if len(sec) > 2 else (kind == "build")
        for b in range(bars):
            tb = t0 + b * BAR
            ci = bar_i % 4
            last = b == bars - 1
            if kind == "intro":
                _place(buf, pad(CHORDS[ci], BAR + 0.3), tb, 0.8)
                _place(buf, K, tb, 0.9)
                for s in range(8):
                    f = CHORDS[ci][s % 3] * (2 if s % 4 < 2 else 1)
                    _place(buf, _st(_pluck(f, 0.3, 9) * 0.22, 0.6), tb + s * BEAT / 2)
            elif kind == "break":  # half-time: pad, slow arp, kick on 1 and a soft clap on 3
                _place(buf, pad(CHORDS[ci], BAR + 0.3), tb, 0.75)
                _place(buf, K, tb, 0.8)
                _place(buf, C, tb + 2 * BEAT, 0.4)
                _place(buf, bass_note(ROOTS[ci], BEAT * 2 - 0.01), tb, 0.55)
                for s in range(8):
                    f = CHORDS[ci][(s * 2) % 3] * (4 if s % 2 else 2)
                    _place(buf, _st(_pluck(f, 0.4, 7) * 0.18, 0.8), tb + s * BEAT / 2)
            elif kind in ("verse", "build", "drop"):
                drop = kind == "drop"
                build = kind == "build"
                _place(buf, pad(CHORDS[ci], BAR + 0.3), tb, 0.55 if drop else 0.45)
                for q in range(4):
                    _place(buf, K, tb + q * BEAT, 1.0)
                    _place(buf, HO if drop else H, tb + q * BEAT + BEAT / 2, 0.5)
                    if (drop or build) and q in (1, 3):
                        _place(buf, C, tb + q * BEAT, 0.8 if drop else 0.55)
                    if drop:
                        _place(buf, H, tb + q * BEAT + BEAT / 4, 0.25)
                        _place(buf, H, tb + q * BEAT + 3 * BEAT / 4, 0.25)
                for e in range(8):
                    if e % 2 == 1 or drop:
                        _place(buf, bass_note(ROOTS[ci] * (2 if (drop and e % 4 == 3) else 1), BEAT / 2 - 0.01),
                                tb + e * BEAT / 2, 0.75)
                if kind == "verse":
                    pattern = [0, 2, 1, 2]
                elif build:
                    pattern = [0, 1, 2, 1, 0, 2, 1, 2]
                else:
                    pattern = [0, 2, 1, 2, 0, 2, 1, 0, 2, 1, 2, 0, 1, 2, 0, 2]
                step = BAR / len(pattern)
                for s, p in enumerate(pattern):
                    f = CHORDS[ci][p] * (4 if drop and s % 2 == 0 else 2)
                    _place(buf, _st(_pluck(f, 0.25, 11) * (0.2 if drop else 0.17), 0.7), tb + s * step)
                if drop and b % 2 == 0:
                    _place(buf, _st(_bell(CHORDS[ci][2] * 4, 0.8, 4) * 0.12, 0.9), tb)
            elif kind == "end":
                if b == 0:
                    _place(buf, impact(), tb, 0.9)
                    _place(buf, pad(CHORDS[0], BAR * bars + 1.0), tb, 0.7)
                    for i, f in enumerate((440.0, 523.25, 659.25, 880.0)):
                        _place(buf, _st(_bell(f, 1.6, 2.5) * 0.25, 0.8), tb + i * BEAT / 2)
            if last and rise and kind != "end":
                for r in range(8):  # snare roll into whatever comes next
                    _place(buf, C, tb + 2 * BEAT + r * BEAT / 4, 0.25 + r * 0.08)
                _place(buf, riser(BAR), tb, 0.7)
            bar_i += 1
        t0 += bars * BAR
    return buf


def master(x: np.ndarray, gain: float = 0.9) -> np.ndarray:
    peak = float(np.max(np.abs(x))) or 1.0
    y = np.tanh(x / peak * 1.4) / np.tanh(1.4)
    return (y * gain).astype(np.float32)
