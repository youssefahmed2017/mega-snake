"""Procedurally synthesized sound effects — no external asset files needed."""
from __future__ import annotations

import numpy as np
import pygame


def _tone(freq: float, duration: float, volume: float = 0.3, wave: str = "sine", fade: bool = True) -> pygame.mixer.Sound:
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, False)

    if wave == "sine":
        signal = np.sin(freq * t * 2 * np.pi)
    elif wave == "square":
        signal = np.sign(np.sin(freq * t * 2 * np.pi))
    elif wave == "saw":
        signal = 2 * (t * freq - np.floor(0.5 + t * freq))
    else:
        signal = np.sin(freq * t * 2 * np.pi)

    if fade:
        fade_len = max(1, n_samples // 8)
        envelope = np.ones(n_samples)
        envelope[:fade_len] = np.linspace(0, 1, fade_len)
        envelope[-fade_len:] = np.linspace(1, 0, fade_len)
        signal = signal * envelope

    audio = (signal * volume * 32767).astype(np.int16)
    stereo = np.column_stack([audio, audio])
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


def _sweep(f0: float, f1: float, duration: float, volume: float = 0.3) -> pygame.mixer.Sound:
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, False)
    freqs = np.linspace(f0, f1, n_samples)
    phase = np.cumsum(2 * np.pi * freqs / sample_rate)
    signal = np.sin(phase)
    fade_len = max(1, n_samples // 10)
    envelope = np.ones(n_samples)
    envelope[:fade_len] = np.linspace(0, 1, fade_len)
    envelope[-fade_len:] = np.linspace(1, 0, fade_len)
    signal *= envelope
    audio = (signal * volume * 32767).astype(np.int16)
    stereo = np.column_stack([audio, audio])
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


class SoundBank:
    def __init__(self) -> None:
        pygame.mixer.set_num_channels(16)
        self.eat = _tone(520, 0.08, 0.25, "square")
        # Ascending scale for chained eats - each step in a combo plays a
        # note higher than the last (classic "satisfying chain" trick),
        # instead of the same flat blip every time. Climbs a bit over an
        # octave then holds, so a long combo doesn't end up ultrasonic.
        _combo_semitones = [0, 2, 4, 5, 7, 9, 11, 12, 14, 16, 19, 24]
        self.combo_scale = [_tone(520 * (2 ** (s / 12)), 0.07, 0.22, "square") for s in _combo_semitones]
        self.golden = _sweep(500, 1100, 0.2, 0.3)
        self.powerup = _sweep(300, 900, 0.25, 0.3)
        self.shrink = _sweep(400, 150, 0.2, 0.25)
        self.bomb = _tone(90, 0.35, 0.35, "saw")
        self.death = _sweep(400, 60, 0.6, 0.35)
        self.achievement = _sweep(600, 1400, 0.35, 0.3)
        self.menu_move = _tone(300, 0.04, 0.15, "square")
        self.menu_select = _tone(700, 0.08, 0.2, "square")
        self.portal = _sweep(700, 300, 0.18, 0.25)
        self.curse = _sweep(500, 200, 0.3, 0.3)
        self.freeze = _tone(1200, 0.15, 0.2, "sine")
        self.teleport = _sweep(200, 1400, 0.22, 0.3)
        self.unlock = _sweep(500, 1600, 0.4, 0.3)
        self.near_miss = _sweep(1200, 700, 0.1, 0.22)
        self.chat = _tone(950, 0.05, 0.14, "square")
        self.muted = False
        self.master_volume = 1.0

    def eat_sound(self, combo: int) -> pygame.mixer.Sound:
        """The plain blip at combo 1, else the next note up the scale."""
        if combo <= 1:
            return self.eat
        return self.combo_scale[min(combo - 2, len(self.combo_scale) - 1)]

    def play(self, sound: pygame.mixer.Sound) -> None:
        if self.muted or self.master_volume <= 0:
            return
        sound.set_volume(min(1.0, self.master_volume))
        sound.play()
