# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Tiny particle system for juice: bursts on eating, death explosions, etc."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Tuple

import pygame

import gfx


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

    def draw(self, surf: pygame.Surface) -> None:
        t = max(0.0, self.life / self.max_life)
        r = max(0, int(self.radius * t))
        if r <= 0:
            return
        color = self.color
        s = gfx.surface((r * 2, r * 2), pygame.SRCALPHA)
        alpha = int(255 * t)
        gfx.draw.circle(s, (*color, alpha), (r, r), r)
        surf.blit(s, (self.x - r, self.y - r))


class ParticleSystem:
    def __init__(self) -> None:
        self.particles: List[Particle] = []
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
        if self.shake_time > 0:
            self.shake_time = max(0.0, self.shake_time - dt)
            if self.shake_time == 0:
                # Reset so one big shake doesn't inflate every later small one.
                self.shake_mag = 0.0
                self.shake_duration = 0.0

    def draw(self, surf: pygame.Surface) -> None:
        for p in self.particles:
            p.draw(surf)
