# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""The trailer bot: plays any Game-shaped state (a local run or a guest's snapshots)."""
from __future__ import annotations

from collections import deque
from typing import Callable, Dict, Optional

from constants import GRID_W, GRID_H, POWERUP_GHOST, FOOD_GOLDEN

DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]



class Bot:
    """Greedy BFS to the nearest wanted pickup, with a flood-fill check so it
    doesn't box itself in. Good enough to look like a decent player."""

    def __init__(self, want_powerups: bool = True, suicide_after: Optional[float] = None,
                 seek: Optional[Callable] = None) -> None:
        self.want_powerups = want_powerups
        self.suicide_after = suicide_after  # seconds; then it steers into the nearest wall/body
        self.seek = seek  # seek(g, snake) -> cells to go for first (a portal, a bomb on purpose...)
        self._last: Dict[int, tuple] = {}

    def _wrap(self, g) -> bool:
        return g.mode_cfg()["wrap"] or POWERUP_GHOST in g.active_powerups

    def _step(self, c, d, wrap):
        x, y = c[0] + d[0], c[1] + d[1]
        if wrap:
            return x % GRID_W, y % GRID_H
        if 0 <= x < GRID_W and 0 <= y < GRID_H:
            return x, y
        return None

    def _blocked(self, g, snake) -> set:
        b = set(g.obstacles)
        for i, p in enumerate(g.players):
            if p is None or not g.players_alive[i]:
                continue
            body = list(p.body)
            b |= set(body[:-1] if p.grow_pending == 0 else body)
        for r in g.rivals:
            if r.alive:
                b |= r.occupies()
                for d in DIRS:  # cells a rival could step into next
                    b.add((r.head[0] + d[0], r.head[1] + d[1]))
        b |= {(d.x, d.y) for d in g.downerups}
        for m in g.meteors:  # red warning zones
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    b.add((m[0] + dx, m[1] + dy))
        b.discard(snake.head)
        return b

    def _flood(self, start, blocked, wrap, limit) -> int:
        seen = {start}
        q = deque([start])
        while q and len(seen) < limit:
            c = q.popleft()
            for d in DIRS:
                n = self._step(c, d, wrap)
                if n and n not in blocked and n not in seen:
                    seen.add(n)
                    q.append(n)
        return len(seen)

    def decide(self, g, snake, t: float, apply: Optional[Callable] = None) -> None:
        key = id(snake)
        sig = (snake.head, len(g.foods), len(g.powerups), len(g.downerups))
        if self._last.get(key) == sig:
            return
        self._last[key] = sig
        apply = apply or snake.set_direction
        wrap = self._wrap(g)
        cur = snake.direction
        options = [d for d in DIRS if not (d[0] == -cur[0] and d[1] == -cur[1])]

        if self.suicide_after is not None and t >= self.suicide_after:
            # Head for the closest wall and keep going - a "classic" death.
            hx, hy = snake.head
            dists = {(1, 0): GRID_W - hx, (-1, 0): hx + 1, (0, 1): GRID_H - hy, (0, -1): hy + 1}
            apply(min((d for d in options), key=lambda d: dists[d]))
            return

        blocked = self._blocked(g, snake)
        wanted = set(self.seek(g, snake)) if self.seek else set()
        blocked -= wanted
        need = len(snake.body) + 4
        targets = {(f.x, f.y): (3 if f.kind == FOOD_GOLDEN else 1) for f in g.foods}
        if self.want_powerups:
            for p in g.powerups:
                targets[(p.x, p.y)] = 2
        if wanted:
            targets = {c: 50 for c in wanted}

        # BFS from each option so we know the first move of every shortest path.
        best = None
        for d in options:
            first = self._step(snake.head, d, wrap)
            if first is None or first in blocked:
                continue
            seen = {first: 0}
            q = deque([first])
            found = None
            while q:
                c = q.popleft()
                if c in targets:
                    found = seen[c] - targets[c] * 2
                    break
                for dd in DIRS:
                    n = self._step(c, dd, wrap)
                    if n and n not in blocked and n not in seen:
                        seen[n] = seen[c] + 1
                        q.append(n)
            space = self._flood(first, blocked, wrap, need)
            safe = space >= need
            score = (0 if safe else 1, found if found is not None else 999, -space)
            if best is None or score < best[0]:
                best = (score, d)
        if best is not None:
            apply(best[1])
