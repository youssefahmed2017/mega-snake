# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""A simple greedy AI snake that competes for food in Battle mode."""
from __future__ import annotations

import random
from collections import deque
from typing import List, Optional, Set, Tuple

from constants import GRID_W, GRID_H


class EnemySnake:
    def __init__(self, x: int, y: int, hunter: bool = False) -> None:
        self.body: List[Tuple[int, int]] = [(x, y), (x - 1, y), (x - 2, y)]
        self.direction = (1, 0)
        self.alive = True
        self.wrap = False  # Reversed's hunters chase across the screen edges too
        self.hunter = hunter  # Hunter event: chases the player's head instead of food
        self.move_phase = 0
        self.grow_pending = 0  # segments still to add (Reversed: a hunter that ate an apple)
        self.color = (255, 70, 70) if hunter else (255, 140, 90)

    @property
    def head(self) -> Tuple[int, int]:
        return self.body[0]

    def choose_direction(self, target: Tuple[int, int], blocked: Set[Tuple[int, int]]) -> None:
        hx, hy = self.head
        tx, ty = target
        candidates = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        # Never reverse directly into itself.
        opposite = (-self.direction[0], -self.direction[1])
        candidates = [c for c in candidates if c != opposite]

        def score(d: Tuple[int, int]) -> float:
            nx, ny = hx + d[0], hy + d[1]
            if self.wrap:
                nx, ny = nx % GRID_W, ny % GRID_H
            elif not (0 <= nx < GRID_W and 0 <= ny < GRID_H):
                return float("inf")
            if (nx, ny) in blocked:
                return float("inf")
            if self.wrap:
                ax, ay = abs(nx - tx), abs(ny - ty)
                return min(ax, GRID_W - ax) + min(ay, GRID_H - ay)
            return abs(nx - tx) + abs(ny - ty)

        candidates.sort(key=score)
        best = candidates[0]
        if score(best) == float("inf"):
            self.alive = False
            return
        self.direction = best

    def step(self, grow: bool) -> None:
        hx, hy = self.head
        dx, dy = self.direction
        if self.grow_pending > 0:
            self.grow_pending -= 1
            grow = True
        new_head = (hx + dx, hy + dy)
        if self.wrap:
            new_head = (new_head[0] % GRID_W, new_head[1] % GRID_H)
        self.body.insert(0, new_head)
        if not grow:
            self.body.pop()

    def occupies(self) -> Set[Tuple[int, int]]:
        return set(self.body)
