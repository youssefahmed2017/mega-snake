# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Tiny particle system for juice: bursts on eating, death explosions, etc."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Tuple

import pygame

import gfx


def _circle_sprite(cache: dict, radius: int, color: Tuple[int, int, int]) -> pygame.Surface:
    """A small, fully-opaque circle sprite, rendered once per (radius, color) and cached.
    Callers fade it with .set_alpha() right before blitting instead of rebuilding a new
    SRCALPHA surface and re-rasterizing a circle every frame - the radius bucket is an int,
    so the cache converges to a handful of entries almost immediately."""
    key = (radius, color)
    img = cache.get(key)
    if img is None:
        img = gfx.surface((radius * 2, radius * 2), pygame.SRCALPHA)
        gfx.draw.circle(img, color, (radius, radius), radius)
        cache[key] = img
    return img


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: Tuple[int, int, int]
    radius: float

    def update(self, dt: float) -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 300 * dt  # gravity
        self.life -= dt
        return self.life > 0

    def draw(self, surf: pygame.Surface, cache: dict) -> None:
        t = max(0.0, self.life / self.max_life)
        r = max(0, round(self.radius * t))
        if r <= 0:
            return
        img = _circle_sprite(cache, r, self.color)
        img.set_alpha(int(255 * t))
        surf.blit(img, (self.x - r, self.y - r))


@dataclass
class Shockwave:
    """Expanding, fading ring - the blast edge of an explosion."""
    x: float
    y: float
    life: float
    max_life: float
    max_radius: float
    color: Tuple[int, int, int]

    def update(self, dt: float) -> bool:
        self.life -= dt
        return self.life > 0

    def draw(self, surf: pygame.Surface) -> None:
        t = max(0.0, min(1.0, 1 - self.life / self.max_life))
        radius = self.max_radius * (1 - (1 - t) ** 2)  # ease-out: fast start, slow finish
        r = int(radius)
        if r <= 1:
            return
        width = max(1, int(6 * (1 - t)))
        alpha = int(220 * (1 - t))
        pad = width + 1
        s = gfx.surface((r * 2 + pad * 2, r * 2 + pad * 2), pygame.SRCALPHA)
        gfx.draw.circle(s, (*self.color, alpha), (r + pad, r + pad), r, width=width)
        surf.blit(s, (self.x - r - pad, self.y - r - pad))


@dataclass
class Flash:
    """Brief radial white-hot core, additive-blended so it reads as light."""
    x: float
    y: float
    life: float
    max_life: float
    max_radius: float
    color: Tuple[int, int, int]

    def update(self, dt: float) -> bool:
        self.life -= dt
        return self.life > 0

    def draw(self, surf: pygame.Surface) -> None:
        t = max(0.0, self.life / self.max_life)
        radius = self.max_radius * (0.4 + 0.6 * (1 - t))
        alpha = int(255 * t * t)
        r = int(radius)
        if alpha <= 0 or r <= 1:
            return
        s = gfx.surface((r * 2, r * 2), pygame.SRCALPHA)
        gfx.draw.circle(s, (*self.color, alpha), (r, r), r)
        surf.blit(s, (self.x - r, self.y - r), special_flags=pygame.BLEND_RGBA_ADD)


@dataclass
class Scorch:
    """Lingering dark blotch left on the floor after an explosion. Shape never changes
    over its ~4s life (only alpha does), so it's rendered once and reused every frame -
    unlike Particle there's no shared cache, since each scorch mark is already a single
    long-lived instance rather than dozens spawned per frame."""
    x: float
    y: float
    life: float
    max_life: float
    radius: float
    _img: pygame.Surface = field(default=None, init=False, repr=False)

    def update(self, dt: float) -> bool:
        self.life -= dt
        return self.life > 0

    def draw(self, surf: pygame.Surface) -> None:
        t = max(0.0, self.life / self.max_life)
        alpha = int(140 * min(1.0, t * 3))  # holds steady, only fades in the last third
        r = int(self.radius)
        if alpha <= 0 or r <= 1:
            return
        if self._img is None:
            self._img = gfx.surface((r * 2, r * 2), pygame.SRCALPHA)
            gfx.draw.circle(self._img, (12, 9, 9), (r, r), r)
        self._img.set_alpha(alpha)
        surf.blit(self._img, (self.x - r, self.y - r))


class ParticleSystem:
    def __init__(self) -> None:
        self.particles: List[Particle] = []
        self.shockwaves: List[Shockwave] = []
        self.flashes: List[Flash] = []
        self.scorches: List[Scorch] = []
        self._circle_cache: dict = {}  # shared by Particle.draw - see _circle_sprite()
        self.shake_time = 0.0
        self.shake_duration = 0.0
        self.shake_mag = 0.0
        self.density = 1.0  # user setting: scales how many particles each burst spawns

    def burst(self, x: float, y: float, color: Tuple[int, int, int], count: int = 14, speed: float = 140, life: float = 0.5) -> None:
        for _ in range(round(count * self.density)):
            angle = random.uniform(0, 6.283)
            spd = random.uniform(speed * 0.3, speed)
            self.particles.append(
                Particle(
                    x=x, y=y,
                    vx=spd * random.uniform(-1, 1),
                    vy=spd * random.uniform(-1, 1) - 40,
                    life=random.uniform(life * 0.5, life),
                    max_life=life,
                    color=color,
                    radius=random.uniform(2, 5),
                )
            )

    def explosion(self, x: float, y: float, color: Tuple[int, int, int] = (255, 120, 60), radius: float = 70) -> None:
        """Bomb/meteor-style blast: particle burst + shockwave ring + white flash + scorch decal."""
        self.burst(x, y, color, count=30, speed=260, life=0.7)
        self.shockwaves.append(Shockwave(x, y, life=0.4, max_life=0.4, max_radius=radius, color=color))
        self.flashes.append(Flash(x, y, life=0.18, max_life=0.18, max_radius=radius * 0.6, color=(255, 240, 200)))
        self.scorches.append(Scorch(x, y, life=4.0, max_life=4.0, radius=radius * 0.55))

    def shake(self, duration: float, magnitude: float) -> None:
        self.shake_time = max(self.shake_time, duration)
        self.shake_duration = max(self.shake_duration, self.shake_time)
        self.shake_mag = max(self.shake_mag, magnitude)

    def get_shake_offset(self) -> Tuple[int, int]:
        if self.shake_time <= 0:
            return 0, 0
        # Full magnitude (in pixels) at the start, fading linearly to zero.
        m = self.shake_mag * (self.shake_time / self.shake_duration)
        return round(random.uniform(-m, m)), round(random.uniform(-m, m))

    def update(self, dt: float) -> None:
        self.particles = [p for p in self.particles if p.update(dt)]
        self.shockwaves = [s for s in self.shockwaves if s.update(dt)]
        self.flashes = [f for f in self.flashes if f.update(dt)]
        self.scorches = [s for s in self.scorches if s.update(dt)]
        if self.shake_time > 0:
            self.shake_time = max(0.0, self.shake_time - dt)
            if self.shake_time == 0:
                # Reset so one big shake doesn't inflate every later small one.
                self.shake_mag = 0.0
                self.shake_duration = 0.0

    def draw_scorch(self, surf: pygame.Surface) -> None:
        """Call early, right after the floor/grid, so the mark sits under everything else."""
        for s in self.scorches:
            s.draw(surf)

    def draw(self, surf: pygame.Surface) -> None:
        for p in self.particles:
            p.draw(surf, self._circle_cache)
        for s in self.shockwaves:
            s.draw(surf)
        for f in self.flashes:
            f.draw(surf)

    def clear_sprite_cache(self) -> None:
        """Call when resolution changes - cached sprites are baked at the old pixel density."""
        self._circle_cache.clear()
        for s in self.scorches:
            s._img = None
