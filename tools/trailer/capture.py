# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Headless capture harness: runs the real Game offscreen on a fixed 60 fps clock,
lets a bot play, and writes each scene to an mp4 + a wav of the game's own sound
effects + a json of markers (death, event start, ...).

Nothing here changes how the game plays - it only swaps the clock, the input queue
and the sound output so frames can be rendered faster or slower than real time.
Imported by record.py; not part of the shipped game.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import wave
from collections import deque
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
# Keep the recorder's runs out of the player's real save file.
os.environ["HOME"] = os.environ.get("TRAILER_HOME") or tempfile.mkdtemp(prefix="megasnake-rec-")

import numpy as np  # noqa: E402
import build_info  # noqa: E402

build_info.STORE = "recorder"  # no update check on boot
import pygame  # noqa: E402

FPS = 60
_now = [0.0]
pygame.time.get_ticks = lambda: int(_now[0] * 1000)  # the game's animations follow the fake clock
pygame.event.get = lambda *a, **k: []                 # no focus-lost auto-pause, no stray input

import main  # noqa: E402
from constants import GRID_W, GRID_H  # noqa: E402
from audio import SoundBank, SR  # noqa: E402

_sound_log: List[Tuple[float, int]] = []
_sound_arrays: Dict[int, np.ndarray] = {}


def _logged_play(self, sound) -> None:
    if self.muted or self.master_volume <= 0:
        return
    if not self.ui_sounds and (sound is self.menu_move or sound is self.menu_select):
        return
    key = id(sound)
    if key not in _sound_arrays:
        _sound_arrays[key] = pygame.sndarray.array(sound).astype(np.float32) / 32767.0
    _sound_log.append((_now[0], key))


SoundBank.play = _logged_play

DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


# ---------------------------------------------------------------- bot

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
        return g.mode_cfg()["wrap"] or main.POWERUP_GHOST in g.active_powerups

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
        targets = {(f.x, f.y): (3 if f.kind == main.FOOD_GOLDEN else 1) for f in g.foods}
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


# ---------------------------------------------------------------- recorder

class Recorder:
    def __init__(self, out_dir: Path, size: Tuple[int, int] = (1920, 1080)) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.size = size
        self.game = main.Game()
        self.game.settings["show_fps"] = False
        self.game.ghost_enabled = False

    def scene(self, name: str, seconds: float, setup: Callable, each: Optional[Callable] = None,
              bot: Optional[Bot] = None, tail_after_death: float = 2.5, seed: int = 1, preroll: float = 0.0,
              steer: Optional[Callable] = None, initials: str = "YOU") -> dict:
        """Record one shot. setup(g) puts the game where we want it; each(g, t, rec)
        runs before every frame for scripted beats (forcing an event, etc.)."""
        g = self.game
        bot = bot or Bot()
        random.seed(seed)
        np.random.seed(seed)
        _sound_log.clear()
        setup(g)
        g._fade_from = None
        for _ in range(int(preroll * FPS)):  # simulated but not filmed (grow the snake, etc.)
            if g.state == main.STATE_PLAYING and g.death_pause_timer <= 0:
                for i, p in enumerate(g.players):
                    if p is not None and g.players_alive[i]:
                        bot.decide(g, p, -1.0)
            if g.state == main.STATE_PERK_PICK:
                g._choose_perk(0)
            g._frame(1 / FPS)
            _now[0] += 1 / FPS
        _sound_log.clear()
        self.markers: Dict[str, float] = {}
        path = self.out_dir / f"{name}.mp4"
        w, h = main.display.get_size()
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "12", "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)
        start = _now[0]
        n = int(seconds * FPS)
        death_at = None
        frame = 0
        typed = 0
        initials_since = None
        while frame < n or (death_at is not None and frame < death_at + tail_after_death * FPS):
            t = frame / FPS
            if g.state == main.STATE_PLAYING and g.death_pause_timer <= 0:
                for i, p in enumerate(g.players):
                    if p is not None and g.players_alive[i]:
                        bot.decide(g, p, t, steer(g, i) if steer else None)
            if g.state == main.STATE_ENTER_INITIALS:  # type a name like a player would
                initials_since = t if initials_since is None else initials_since
                k = int((t - initials_since - 0.7) / 0.3)
                if 0 <= k and typed < len(initials) and k >= typed:
                    g.handle_initials_key(pygame.K_a + ord(initials[typed].lower()) - ord("a"))
                    typed += 1
                elif typed == len(initials) and t - initials_since > 0.7 + 0.3 * typed + 0.5:
                    g.handle_initials_key(pygame.K_RETURN)
                    typed += 1
            if g.state == main.STATE_PERK_PICK and "perk" not in self.markers:
                self.markers["perk"] = t
            if g.state == main.STATE_PERK_PICK and t - self.markers["perk"] > 1.6:
                g._choose_perk(g.perk_index)
            if each:
                each(g, t, self)
            if death_at is None and g.death_pause_timer > 0:
                death_at = frame
                self.markers["death"] = t
                n = min(n, frame + 1)
            g._frame(1 / FPS)
            _now[0] += 1 / FPS
            ff.stdin.write(pygame.image.tobytes(main.display, "RGB"))
            frame += 1
            if frame > (seconds + tail_after_death + 30) * FPS:
                break
        ff.stdin.close()
        ff.wait()
        dur = frame / FPS
        self._write_wav(self.out_dir / f"{name}.wav", start, dur)
        meta = {"name": name, "duration": dur, "markers": self.markers, "died": death_at is not None,
                "score": g.score}
        (self.out_dir / f"{name}.json").write_text(json.dumps(meta, indent=1))
        print(f"  {name}: {dur:.1f}s  score={g.score}  markers={self.markers}", flush=True)
        return meta

    def mark(self, key: str, t: float) -> None:
        self.markers.setdefault(key, t)

    def _write_wav(self, path: Path, start: float, dur: float) -> None:
        out = np.zeros((int(dur * SR) + SR, 2), np.float32)
        for t, key in _sound_log:
            arr = _sound_arrays[key]
            i = int((t - start) * SR)
            if i < 0 or i >= len(out):
                continue
            seg = arr[: len(out) - i]
            out[i:i + len(seg)] += seg
        out = out[: int(dur * SR)]
        write_wav(path, out)


def write_wav(path, stereo: np.ndarray, sr: int = SR) -> None:
    data = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())
