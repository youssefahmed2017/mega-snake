# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""YouTube thumbnails (1280x720) from clean, re-rendered game frames.

    python tools/trailer/thumbnail.py [out_dir]

Replays three of record.py's scenes with the same seeds, grabs a frame with the
in-game announcer text hidden (it fights the thumbnail text), notes where the
meteors and snake heads are, and composes three designs:
  1. "THIS IS SNAKE?!"   - full chaos, big two-line text
  2. SNAKE vs MEGA SNAKE - before/after split
  3. "I BROKE SNAKE"     - red circle + arrow on a meteor strike
"""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pygame

from capture import Recorder, main  # noqa: E402  (headless game)
import record
from constants import CELL_SIZE, BOARD_Y

W, H = 1280, 720
ROOT = Path(__file__).resolve().parents[2]
HEAD = str(ROOT / "assets/fonts/LilitaOne-Regular.ttf")
YELLOW, WHITE, GREEN, RED, BLACK = (255, 214, 40), (255, 255, 255), (110, 235, 130), (255, 45, 45), (0, 0, 0)


def grab(rec: Recorder, name: str, at: float):
    """Re-record scene `name` (same seed as the trailer) and keep the frame at `at` seconds."""
    (args, kw), = [(a, k) for a, k in record.scenes() if a[0] == name]
    _, seconds, setup, each = args
    kw = {k: v for k, v in kw.items() if k != "after"}
    shot = {}

    def hook(g, t, r):
        if each:
            each(g, t, r)
        g.announcer_queue.clear()  # no "GOLDEN RUSH!" across the middle
        g.toast_queue.clear()      # ...or achievement pop-ups in the corner
        if shot.pop("pending", None):  # the frame for `at` has been drawn by now
            shot["img"] = main.display.copy()
            k = main.display.get_width() / main.SCREEN_W
            cells = lambda cs: [((x + 0.5) * CELL_SIZE * k, (y + 0.5) * CELL_SIZE * k) for x, y in cs]  # noqa  (board px)
            shot["meteors"] = cells([(m[0], m[1]) for m in g.meteors])
            shot["heads"] = cells([p.head for p in g.players if p is not None])
        elif t >= at and "img" not in shot:
            shot["pending"] = True
    for attempt in range(8):  # the bot can die before `at`; try the next seed like record.py does
        shot.clear()
        meta = rec.scene(f"thumb_{name}", min(seconds, at + 0.3), setup, hook, **kw)
        if "img" in shot and meta["markers"].get("death", 99) > at:
            return shot
        kw["seed"] = kw.get("seed", 1) + 1000
        if kw.get("bot") is not None:
            kw["bot"]._last.clear()
    raise RuntimeError(f"no clean frame for {name}")


def board(img: pygame.Surface) -> pygame.Surface:
    k = img.get_width() / main.SCREEN_W
    return img.subsurface(pygame.Rect(0, int(BOARD_Y * k), int(768 * k), int(528 * k))).copy()


def punch_up(surf: pygame.Surface, sat: float = 1.35, contrast: float = 1.15, bright: float = 1.1) -> pygame.Surface:
    a = pygame.surfarray.array3d(surf).astype(np.float32)
    gray = a.mean(axis=2, keepdims=True)
    a = gray + (a - gray) * sat
    a = (a - 128) * contrast + 128
    a *= bright
    out = pygame.surfarray.make_surface(np.clip(a, 0, 255).astype(np.uint8))
    return out


def gray(surf: pygame.Surface, dim: float = 0.75) -> pygame.Surface:
    a = pygame.surfarray.array3d(surf).astype(np.float32).mean(axis=2, keepdims=True) * dim
    return pygame.surfarray.make_surface(np.repeat(a, 3, axis=2).clip(0, 255).astype(np.uint8))


def cover(surf: pygame.Surface, focus=None, zoom: float = 1.0):
    """Scale-and-crop to 1280x720 around `focus` (source px); returns (image, mapper)."""
    sw, sh = surf.get_size()
    s = max(W / sw, H / sh) * zoom
    fx, fy = focus or (sw / 2, sh / 2)
    ox = min(max(fx * s - W / 2, 0), sw * s - W)
    oy = min(max(fy * s - H / 2, 0), sh * s - H)
    big = pygame.transform.smoothscale(surf, (int(sw * s), int(sh * s)))
    out = pygame.Surface((W, H))
    out.blit(big, (-ox, -oy))
    return out, (lambda p: (p[0] * s - ox, p[1] * s - oy))


def vignette(surf: pygame.Surface, strength: int = 160) -> None:
    v = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(40):
        pygame.draw.rect(v, (0, 0, 0, strength // 40), v.get_rect().inflate(-i * 18, -i * 10), 18)
    surf.blit(v, (0, 0))


def text(surf, s, size, color, pos, stroke=10, anchor="topleft", angle=0.0, shadow=True):
    f = pygame.font.Font(HEAD, size)
    fg = f.render(s, True, color)
    bk = f.render(s, True, BLACK)
    pad = stroke + 12
    t = pygame.Surface((fg.get_width() + pad * 2, fg.get_height() + pad * 2), pygame.SRCALPHA)
    if shadow:
        sh = f.render(s, True, BLACK)
        sh.set_alpha(140)
        for a in range(0, 360, 30):
            t.blit(sh, (pad + 8 + math.cos(math.radians(a)) * stroke, pad + 10 + math.sin(math.radians(a)) * stroke))
    for a in range(0, 360, 12):
        t.blit(bk, (pad + math.cos(math.radians(a)) * stroke, pad + math.sin(math.radians(a)) * stroke))
    t.blit(fg, (pad, pad))
    if angle:
        t = pygame.transform.rotozoom(t, angle, 1.0)
    r = t.get_rect(**{anchor: pos})
    surf.blit(t, r)
    return r


def badge(surf):
    """Small game logo, top-left, on every design."""
    r = pygame.Rect(26, 22, 300, 64)
    pygame.draw.rect(surf, (12, 14, 20), r, border_radius=14)
    pygame.draw.rect(surf, GREEN, r, 4, border_radius=14)
    f = pygame.font.Font(HEAD, 44)
    a, b = f.render("MEGA ", True, WHITE), f.render("SNAKE", True, GREEN)
    x = r.centerx - (a.get_width() + b.get_width()) // 2
    surf.blit(a, (x, r.centery - a.get_height() // 2))
    surf.blit(b, (x + a.get_width(), r.centery - b.get_height() // 2))


def arrow(surf, start, end, color=RED, width=22):
    sx, sy = start
    ex, ey = end
    ang = math.atan2(ey - sy, ex - sx)
    head = 58
    bx, by = ex - math.cos(ang) * head, ey - math.sin(ang) * head
    for col, w, h in ((BLACK, width + 12, head + 10), (color, width, head)):
        pygame.draw.line(surf, col, (sx, sy), (bx, by), w)
        left = (bx + math.cos(ang + math.pi / 2) * h * 0.6, by + math.sin(ang + math.pi / 2) * h * 0.6)
        right = (bx + math.cos(ang - math.pi / 2) * h * 0.6, by + math.sin(ang - math.pi / 2) * h * 0.6)
        tip = (ex + math.cos(ang) * (h - head), ey + math.sin(ang) * (h - head))
        pygame.draw.polygon(surf, col, [tip, left, right])


def ring(surf, center, r, color=RED, width=12):
    pygame.draw.circle(surf, BLACK, center, r, width + 10)
    pygame.draw.circle(surf, color, center, r, width)


def make(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rec = Recorder(Path(tempfile.mkdtemp(prefix="thumbclips-")))
    chaos = grab(rec, "chaos_max", 2.5)
    battle = grab(rec, "chaos_battle", 1.9)
    calm = grab(rec, "calm_snake", 1.5)

    # 1. THIS IS SNAKE?!
    b = board(chaos["img"])
    img, to = cover(punch_up(b), zoom=1.0)
    vignette(img, 200)
    shade = pygame.Surface((W, H), pygame.SRCALPHA)
    for x in range(W // 2):
        pygame.draw.line(shade, (0, 0, 0, int(170 * (1 - x / (W / 2)))), (x, 0), (x, H))
    img.blit(shade, (0, 0))
    text(img, "THIS IS", 150, WHITE, (40, 190), angle=3)
    text(img, "SNAKE?!", 210, YELLOW, (30, 330), stroke=12, angle=3)
    badge(img)
    pygame.image.save(img, str(out / "thumbnail_1_this_is_snake.png"))

    # 2. SNAKE vs MEGA SNAKE (before / after)
    left, _ = cover(gray(board(calm["img"]), 0.6), zoom=1.0)
    right, _ = cover(punch_up(board(battle["img"])), zoom=1.0)
    img = right.copy()
    mask = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), [(0, 0), (W * 0.52, 0), (W * 0.40, H), (0, H)])
    left_cut = left.copy()
    left_cut.set_colorkey(None)
    lc = pygame.Surface((W, H), pygame.SRCALPHA)
    lc.blit(left_cut, (0, 0))
    lc.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    img.blit(lc, (0, 0))
    pygame.draw.line(img, BLACK, (W * 0.52, 0), (W * 0.40, H), 26)
    pygame.draw.line(img, YELLOW, (W * 0.52, 0), (W * 0.40, H), 12)
    vignette(img, 120)
    text(img, "SNAKE", 120, (200, 200, 200), (W * 0.22, 140), anchor="center")
    text(img, "MEGA", 150, WHITE, (W * 0.73, 110), anchor="center")
    text(img, "SNAKE", 150, GREEN, (W * 0.73, 245), anchor="center")
    arrow(img, (W * 0.22, 520), (W * 0.58, 560), YELLOW)
    pygame.image.save(img, str(out / "thumbnail_2_snake_vs_mega.png"))

    # 3. I BROKE SNAKE (circle the meteor)
    target = battle["meteors"][0] if battle["meteors"] else (battle["heads"][0] if battle["heads"] else None)
    b = board(battle["img"])
    img, to = cover(punch_up(b, 1.4), focus=target, zoom=1.25)
    vignette(img, 220)
    bottom = pygame.Surface((W, 260), pygame.SRCALPHA)
    for y in range(260):
        pygame.draw.line(bottom, (0, 0, 0, int(200 * y / 260)), (0, y), (W, y))
    img.blit(bottom, (0, H - 260))
    if target:
        cx, cy = to(target)
        cx, cy = min(max(cx, 120), W - 120), min(max(cy, 120), H - 300)
        ring(img, (int(cx), int(cy)), 95)
        arrow(img, (cx + (330 if cx < W / 2 else -330), cy + 170), (cx + (100 if cx < W / 2 else -100), cy + 55))
    text(img, "I BROKE SNAKE", 170, WHITE, (W // 2, H - 125), anchor="center", stroke=12)
    badge(img)
    pygame.image.save(img, str(out / "thumbnail_3_i_broke_snake.png"))
    print("meteors:", battle["meteors"], "heads:", battle["heads"])


if __name__ == "__main__":
    pygame.font.init()
    make(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("thumbnails"))
