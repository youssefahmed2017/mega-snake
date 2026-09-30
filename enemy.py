"""A simple greedy AI snake that competes for food in Battle mode."""
from __future__ import annotations

import random
from collections import deque
from typing import List, Optional, Set, Tuple

from constants import GRID_W, GRID_H


class EnemySnake:
    def __init__(self, x: int, y: int) -> None:
        self.body: List[Tuple[int, int]] = [(x, y), (x - 1, y), (x - 2, y)]
        self.direction = (1, 0)
        self.alive = True
        self.color = (255, 140, 90)

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
            if not (0 <= nx < GRID_W and 0 <= ny < GRID_H) or (nx, ny) in blocked:
                return float("inf")
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
        new_head = (hx + dx, hy + dy)
        self.body.insert(0, new_head)
        if not grow:
            self.body.pop()

    def occupies(self) -> Set[Tuple[int, int]]:
        return set(self.body)
