# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""The player snake: grid-based movement with smooth interpolated rendering."""
from __future__ import annotations

import math
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
        """Interpolate between previous and current body for smooth rendering.

        Across a screen edge the positions carry on past the edge (x = 31.7, then 32.3) instead of
        jumping to the other side, so the snake slides through; the caller draws a copy shifted by a
        board width so the part that left one side shows up on the other."""
        prev = self.prev_body
        cur = list(self.body)
        n = min(len(prev), len(cur))
        positions: List[Tuple[float, float]] = []
        for i in range(len(cur)):
            cx, cy = cur[i]
            if i >= n:
                positions.append((cx, cy))
                continue
            px, py = prev[i]
            dx, dy = cx - px, cy - py
            if abs(dx) == GRID_W - 1:  # stepped across the left/right edge: really one cell the other way
                dx -= math.copysign(GRID_W, dx)
            if abs(dy) == GRID_H - 1:
                dy -= math.copysign(GRID_H, dy)
            if abs(dx) > 1 or abs(dy) > 1:  # a portal jump: nothing to slide through
                positions.append((cx, cy))
            else:
                positions.append((px + dx * alpha, py + dy * alpha))
        # Keep the chain continuous: a segment that sits on the far side of the board from its neighbour
        # (one wrapped, the other has not yet) is moved a whole board width to sit next to it.
        for i in range(1, len(positions)):
            x, y = positions[i]
            ox, oy = positions[i - 1]
            if x - ox > GRID_W / 2:
                x -= GRID_W
            elif ox - x > GRID_W / 2:
                x += GRID_W
            if y - oy > GRID_H / 2:
                y -= GRID_H
            elif oy - y > GRID_H / 2:
                y += GRID_H
            positions[i] = (x, y)
        return positions
