# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Food, power-up, and portal spawning."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from constants import (
    FOOD_WEIGHTS, GRID_W, GRID_H,
    POWERUP_GHOST, POWERUP_MAGNET, POWERUP_SHIELD, POWERUP_SLOWMO, POWERUP_MULT,
    POWERUP_FREEZE, POWERUP_TELEPORT,
    DOWNERUP_TYPES, DOWNERUP_SPAWN_RATE, DOWNERUP_TTL, POWERUP_SPAWN_RATE, PORTAL_SPAWN_RATE,
)

POWERUP_TYPES = [
    POWERUP_GHOST, POWERUP_MAGNET, POWERUP_SHIELD, POWERUP_SLOWMO,
    POWERUP_MULT, POWERUP_FREEZE, POWERUP_TELEPORT,
]


@dataclass
class Food:
    x: int
    y: int
    kind: str
    temp: bool = False  # event-spawned extra: eating it doesn't trigger a replacement spawn


@dataclass
class PowerUp:
    x: int
    y: int
    kind: str
    ttl: float = 12.0  # despawns if not collected


@dataclass
class Downerup:
    """A hazard pickup (bomb, curse): spawned and collected like a power-up,
    not mixed into the food pool - see constants.DOWNERUP_* for why."""
    x: int
    y: int
    kind: str
    ttl: float = DOWNERUP_TTL  # despawns if not collected


def random_free_cell(occupied: Set[Tuple[int, int]], rng: random.Random = random) -> Tuple[int, int]:
    attempts = 0
    while attempts < 500:
        attempts += 1
        cell = (rng.randint(0, GRID_W - 1), rng.randint(0, GRID_H - 1))
        if cell not in occupied:
            return cell
    # Grid is basically full; fall back to a linear scan.
    for x in range(GRID_W):
        for y in range(GRID_H):
            if (x, y) not in occupied:
                return (x, y)
    return (0, 0)


def spawn_food(occupied: Set[Tuple[int, int]], rng: random.Random = random) -> Food:
    kinds = list(FOOD_WEIGHTS.keys())
    weights = list(FOOD_WEIGHTS.values())
    kind = rng.choices(kinds, weights=weights, k=1)[0]
    x, y = random_free_cell(occupied, rng)
    return Food(x, y, kind)


def maybe_spawn_powerup(occupied: Set[Tuple[int, int]], existing: List[PowerUp], enabled: bool,
                        dt: float) -> Optional[PowerUp]:
    if not enabled or len(existing) >= 2:
        return None
    if random.random() > POWERUP_SPAWN_RATE * dt:
        return None
    kind = random.choice(POWERUP_TYPES)
    x, y = random_free_cell(occupied)
    return PowerUp(x, y, kind)


def maybe_spawn_downerup(occupied: Set[Tuple[int, int]], existing: List[Downerup], enabled: bool,
                         dt: float) -> Optional[Downerup]:
    if not enabled or len(existing) >= 1:
        return None
    if random.random() > DOWNERUP_SPAWN_RATE * dt:
        return None
    kind = random.choice(DOWNERUP_TYPES)
    x, y = random_free_cell(occupied)
    return Downerup(x, y, kind)


def maybe_spawn_portal_pair(occupied: Set[Tuple[int, int]],
                            dt: float) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
    if random.random() > PORTAL_SPAWN_RATE * dt:
        return None
    a = random_free_cell(occupied)
    occupied = occupied | {a}
    b = random_free_cell(occupied)
    return a, b
