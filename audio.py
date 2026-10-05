"""Procedurally synthesized sound effects (no asset files). Modern, soft timbres:
FM-ish bells, plucked strings, airy glides and filtered-noise whooshes, all with a
short reverb tail and a touch of stereo width."""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pygame

SR = 44100
_RNG = np.random.default_rng(7)


def _t(duration: float) -> np.ndarray:
    return np.arange(int(SR * duration)) / SR


def _fade(sig: np.ndarray, attack: float = 0.004, release: float = 0.02) -> np.ndarray:
    n = len(sig)
    a, r = min(n, max(1, int(SR * attack))), min(n, max(1, int(SR * release)))
    env = np.ones(n)
    env[:a] = np.linspace(0, 1, a)
    env[-r:] *= np.linspace(1, 0, r)
    return sig * env


def _lowpass(sig: np.ndarray, cutoff: float) -> np.ndarray:
    """One-pole low-pass as a truncated exponential-kernel convolution."""
    a = float(np.exp(-2 * np.pi * cutoff / SR))
    kernel = (1 - a) * a ** np.arange(512)
    return np.convolve(sig, kernel)[: len(sig)]


def _reverb(sig: np.ndarray, amount: float = 0.25) -> np.ndarray:
    """A few decaying echoes: cheap, but enough to take the 'dry beep' edge off."""
    if amount <= 0:
        return sig
    out = np.concatenate([sig, np.zeros(int(SR * 0.16))])
    for delay, gain in ((0.023, 0.55), (0.041, 0.38), (0.067, 0.26), (0.097, 0.16)):
        d = int(SR * delay)
        out[d:d + len(sig)] += sig * gain * amount * 2
    return out


def _make(mono: np.ndarray, volume: float, reverb: float = 0.2, width: float = 0.5) -> pygame.mixer.Sound:
    mono = _reverb(mono, reverb)
    peak = float(np.max(np.abs(mono))) or 1.0
    mono = mono / peak * volume
    shift = int(SR * 0.0004 * (1 + width * 2))  # sub-millisecond Haas offset = width
    left = mono
    right = np.concatenate([np.zeros(shift), mono[:-shift]]) if shift else mono
    stereo = np.column_stack([left, right])
    return pygame.sndarray.make_sound(np.ascontiguousarray(np.clip(stereo * 32767, -32767, 32767).astype(np.int16)))


def _bell(freq: float, duration: float = 0.5, decay: float = 7.0) -> np.ndarray:
    t = _t(duration)
    sig = np.zeros_like(t)
    for ratio, amp, d in ((1.0, 1.0, 1.0), (2.76, 0.35, 1.7), (5.4, 0.16, 2.6), (8.93, 0.06, 3.5)):
        sig += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-decay * d * t)
    return _fade(sig, attack=0.002, release=0.03)


def _pluck(freq: float, duration: float = 0.3, decay: float = 9.0) -> np.ndarray:
    t = _t(duration)
    sig = np.zeros_like(t)
    for h in range(1, 7):
        sig += (1.0 / h) * np.sin(2 * np.pi * freq * h * t) * np.exp(-decay * (0.7 + 0.35 * h) * t)
    return _fade(sig, attack=0.002, release=0.02)


def _glide(f0: float, f1: float, duration: float, shape: float = 1.0, tone: float = 0.25) -> np.ndarray:
    t = _t(duration)
    freqs = f0 + (f1 - f0) * (t / duration) ** shape
    phase = 2 * np.pi * np.cumsum(freqs) / SR
    sig = np.sin(phase) + tone * np.sin(2 * phase) + tone * 0.4 * np.sin(3 * phase)
    return _fade(sig, attack=0.015, release=duration * 0.45)


def _noise_whoosh(duration: float, c0: float, c1: float) -> np.ndarray:
    """Filtered noise whose brightness sweeps c0 -> c1 Hz."""
    n = int(SR * duration)
    noise = _RNG.standard_normal(n)
    low, high = _lowpass(noise, c0), _lowpass(noise, c1)
    mix = np.linspace(0, 1, n)
    sig = low * (1 - mix) + high * mix
    env = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
    return sig * env


def _mix(*layers) -> np.ndarray:
    """Sum (array, gain) layers of different lengths."""
    out = np.zeros(max(len(a) for a, _ in layers))
    for a, g in layers:
        out[:len(a)] += a * g
    return out


def _sequence(notes: Sequence[np.ndarray], gap: float) -> np.ndarray:
    total = int(SR * gap * (len(notes) - 1)) + max(len(n) for n in notes)
    out = np.zeros(total)
    for i, note in enumerate(notes):
        start = int(SR * gap * i)
        out[start:start + len(note)] += note
    return out


class SoundBank:
    def __init__(self) -> None:
        pygame.mixer.set_num_channels(16)
        self.eat = _make(_pluck(659.3, 0.22, 11), 0.5, 0.18)
        # Chained eats climb a pentatonic scale: always consonant, never ultrasonic.
        _combo_semitones = [0, 2, 4, 7, 9, 12, 14, 16, 19, 21, 24, 28]
        self.combo_scale = [_make(_pluck(523.3 * 2 ** (s / 12), 0.24, 10), 0.5, 0.2) for s in _combo_semitones]
        self.golden = _make(_sequence([_bell(f, 0.6, 5) for f in (880, 1108.7, 1318.5)], 0.045), 0.55, 0.35)
        self.powerup = _make(_mix((_glide(330, 990, 0.3, 1.4), 0.8),
                                    (_sequence([np.zeros(1), _bell(1318.5, 0.35, 8)], 0.18), 0.5)), 0.5, 0.3)
        self.shrink = _make(_glide(520, 230, 0.22, 0.8, 0.15), 0.45, 0.15)
        t = _t(0.5)
        boom = np.sin(2 * np.pi * (75 * np.exp(-3 * t) + 32) * t) * np.exp(-6 * t)
        self.bomb = _make(_fade(boom + 0.5 * _lowpass(_noise_whoosh(0.5, 900, 300), 500), 0.002, 0.1), 0.8, 0.3)
        self.death = _make(_glide(360, 70, 0.7, 0.6, 0.35) + 0.25 * _noise_whoosh(0.7, 2500, 250), 0.6, 0.35)
        self.achievement = _make(_sequence([_bell(f, 0.9, 4) for f in (523.3, 659.3, 784.0, 1046.5)], 0.075), 0.6, 0.4)
        # UI: barely-there taps rather than beeps.
        tt = _t(0.045)
        self.menu_move = _make(_fade(np.sin(2 * np.pi * 1180 * tt) * np.exp(-90 * tt), 0.001, 0.01), 0.22, 0.05)
        self.menu_select = _make(_sequence([_pluck(587.3, 0.16, 16), _pluck(880, 0.2, 14)], 0.045), 0.4, 0.15)
        self.portal = _make(_mix((_noise_whoosh(0.32, 600, 3200), 0.7), (_glide(900, 380, 0.3, 0.7, 0.1), 0.5)), 0.5, 0.35)
        tc = _t(0.45)
        curse = (np.sin(2 * np.pi * 196 * tc) + np.sin(2 * np.pi * 199.5 * tc)) * np.exp(-3.2 * tc)
        self.curse = _make(_fade(curse + 0.4 * _glide(420, 150, 0.45, 0.6, 0.3), 0.01, 0.2), 0.55, 0.3)
        self.freeze = _make(_sequence([_bell(1568, 0.5, 9), _bell(2093, 0.4, 11)], 0.05), 0.45, 0.35)
        self.teleport = _make(_mix((_glide(220, 1500, 0.28, 2.0, 0.2), 0.7),
                                      (_sequence([np.zeros(1), _bell(1975.5, 0.35, 9)], 0.2), 0.4)), 0.5, 0.3)
        self.unlock = _make(_sequence([_bell(f, 1.0, 3.5) for f in (392.0, 493.9, 587.3, 784.0, 987.8)], 0.07), 0.6, 0.45)
        self.near_miss = _make(_noise_whoosh(0.16, 1200, 5200) * 0.9, 0.4, 0.15)
        tp = _t(0.07)
        self.chat = _make(_fade(np.sin(2 * np.pi * 740 * tp) * np.exp(-55 * tp), 0.001, 0.02), 0.35, 0.1)
        self.muted = False
        self.master_volume = 1.0
        self.ui_sounds = True

    def eat_sound(self, combo: int) -> pygame.mixer.Sound:
        """The plain pluck at combo 1, else the next note up the scale."""
        if combo <= 1:
            return self.eat
        return self.combo_scale[min(combo - 2, len(self.combo_scale) - 1)]

    def play(self, sound: pygame.mixer.Sound) -> None:
        if self.muted or self.master_volume <= 0:
            return
        if not self.ui_sounds and (sound is self.menu_move or sound is self.menu_select):
            return
        sound.set_volume(min(1.0, self.master_volume))
        sound.play()
