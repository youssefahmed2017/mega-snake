# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""The player snake: grid-based movement with smooth interpolated rendering."""
from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional, Tuple

from constants import GRID_W, GRID_H


class PlayerSnake:
    def __init__(self, x: int, y: int) -> None:
        self.body: Deque[Tuple[int, int]] = deque([(x, y), (x - 1, y), (x - 2, y)])
        self.prev_body: List[Tuple[int, int]] = list(self.body)
        self.direction = (1, 0)
        self.pending_direction = (1, 0)
        self.grow_pending = 0
        self.tail_pop_anim = 999.0  # seconds since the tail last grew; big = no pop animation playing
        self.turn_anim = 999.0  # seconds since the head last changed direction; big = no squash playing

    @property
    def head(self) -> Tuple[int, int]:
        return self.body[0]

    def set_direction(self, d: Tuple[int, int]) -> None:
        # Prevent reversing directly into the snake's own neck.
        if (d[0] == -self.direction[0] and d[1] == -self.direction[1]) and len(self.body) > 1:
            return
        self.pending_direction = d

    def step(self, wrap: bool) -> Tuple[int, int]:
        self.prev_body = list(self.body)
        old_direction = self.direction
        self.direction = self.pending_direction
        if self.direction != old_direction:
            self.turn_anim = 0.0
        hx, hy = self.head
        dx, dy = self.direction
        nx, ny = hx + dx, hy + dy

        if wrap:
            nx %= GRID_W
            ny %= GRID_H

        self.body.appendleft((nx, ny))
        if self.grow_pending > 0:
            self.grow_pending -= 1
            self.tail_pop_anim = 0.0
        else:
            self.body.pop()

        return nx, ny

    def grow(self, amount: int = 1) -> None:
        self.grow_pending += amount

    def shrink(self, amount: int = 1) -> None:
        for _ in range(amount):
            if len(self.body) > 2:
                self.body.pop()

    def occupies(self, skip_head: bool = False) -> set:
        cells = list(self.body)
        if skip_head:
            cells = cells[1:]
        return set(cells)

    def self_collision(self) -> bool:
        return self.head in list(self.body)[1:]

    def render_positions(self, alpha: float) -> List[Tuple[float, float]]:
        """Interpolate between previous and current body for smooth rendering."""
        positions = []
        prev = self.prev_body
        cur = list(self.body)
        n = min(len(prev), len(cur))
        for i in range(len(cur)):
            if i < n:
                px, py = prev[i]
                cx, cy = cur[i]
                # Handle wraparound jump: if distance is huge, don't interpolate.
                if abs(cx - px) > 1 or abs(cy - py) > 1:
                    positions.append((cx, cy))
                else:
                    positions.append((px + (cx - px) * alpha, py + (cy - py) * alpha))
            else:
                positions.append(cur[i])
        return positions
