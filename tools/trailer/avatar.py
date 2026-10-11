# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""YouTube profile picture (800x800, shown as a circle) - three variants.

    python tools/trailer/avatar.py [out_dir]

  1. S-snake  - a snake curled into an "S" in the game's flat two-tone sprite style,
                on the key art's night sky with the moon
  2. sprite   - the game's real head + body sprites (assets/art), close up
  3. monogram - "MS" in the wordmark's letter-spaced accent blue with its diamond
Drawn at 3x and scaled down for clean edges. Also writes *_circle_preview.png
showing how YouTube crops it, at full size and at 48px.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1))
ROOT = Path(__file__).resolve().parents[2]
BODY = str(ROOT / "assets/fonts/VarelaRound-Regular.ttf")
S = 800
K = 3                      # supersampling
N = S * K
SKY_TOP, SKY_BOT = (14, 24, 34), (22, 52, 64)
ACCENT = (90, 200, 255)
GREEN_DARK, GREEN, GREEN_LIGHT = (36, 160, 84), (46, 196, 104), (118, 224, 160)
EYE = (20, 40, 44)


def sky(moon=True, stars=True) -> pygame.Surface:
    s = pygame.Surface((N, N))
    for y in range(N):
        t = y / N
        pygame.draw.line(s, tuple(int(a + (b - a) * t) for a, b in zip(SKY_TOP, SKY_BOT)), (0, y), (N, y))
    if stars:
        for x, y, r in ((0.22, 0.2, 5), (0.78, 0.16, 6), (0.86, 0.42, 4), (0.15, 0.62, 4), (0.66, 0.84, 5),
                        (0.35, 0.86, 3), (0.9, 0.7, 4)):
            pygame.draw.circle(s, (220, 235, 245) if r > 4 else ACCENT, (int(x * N), int(y * N)), r * K)
    if moon:
        c, r = (int(0.74 * N), int(0.27 * N)), int(0.085 * N)
        pygame.draw.circle(s, (238, 240, 242), c, r)
        pygame.draw.circle(s, (210, 214, 220), (c[0] + r // 3, c[1] + r // 4), int(r * 0.78), 0)
        pygame.draw.circle(s, (238, 240, 242), (c[0] - r // 6, c[1] - r // 8), int(r * 0.8))
    return s


def s_path(n=400):
    """An S: top arc (opening left) into a bottom arc (opening right), head at the top end."""
    pts = []
    cx, r = N * 0.5, N * 0.165
    top, bot = (cx, N * 0.5 - r), (cx, N * 0.5 + r)
    for i in range(n // 2):  # head end: starts upper-right, sweeps over the top and down the left
        a = math.radians(-20 - 250 * i / (n // 2))
        pts.append((top[0] + math.cos(a) * r, top[1] + math.sin(a) * r))
    for i in range(n // 2):  # bottom arc: from the middle, down the right side, round to lower-left
        a = math.radians(-90 + 250 * i / (n // 2))
        pts.append((bot[0] + math.cos(a) * r, bot[1] + math.sin(a) * r))
    return pts


def draw_snake(surf, pts, thick):
    n = len(pts)
    def rad(i):  # taper toward the tail
        return thick * (1.0 if i < n * 0.55 else max(0.25, 1 - (i - n * 0.55) / (n * 0.45) * 0.8))
    for i in range(n - 1, -1, -1):  # shadow
        x, y = pts[i]
        pygame.draw.circle(surf, (6, 12, 18), (x + thick * 0.12, y + thick * 0.22), rad(i) + thick * 0.05)
    for i in range(n - 1, -1, -1):  # dark outline/side
        pygame.draw.circle(surf, GREEN_DARK, pts[i], rad(i))
    for i in range(n - 1, -1, -1):  # light belly band (lower half, like the sprites)
        x, y = pts[i]
        pygame.draw.circle(surf, GREEN_LIGHT, (x, y + rad(i) * 0.28), rad(i) * 0.78)
    for i in range(n - 1, -1, -1):  # main body colour on top
        x, y = pts[i]
        pygame.draw.circle(surf, GREEN, (x - rad(i) * 0.05, y - rad(i) * 0.2), rad(i) * 0.72)
    # head: a touch wider, pill eyes, forked tongue pointing the way it's heading
    hx, hy = pts[0]
    ang = math.radians(-15)  # look right, out of the S's top terminal
    fx, fy = math.cos(ang), math.sin(ang)
    px, py = -fy, fx
    tip = (hx + fx * thick * 1.15, hy + fy * thick * 1.15)
    tl = thick * 0.75
    fork = [(tip[0] + fx * tl * 0.7 + px * tl * 0.35, tip[1] + fy * tl * 0.7 + py * tl * 0.35),
            (tip[0] + fx * tl * 0.7 - px * tl * 0.35, tip[1] + fy * tl * 0.7 - py * tl * 0.35)]
    w = max(2, int(thick * 0.16))
    pygame.draw.line(surf, (235, 70, 90), (hx + fx * thick * 0.8, hy + fy * thick * 0.8), tip, w)
    for f in fork:
        pygame.draw.line(surf, (235, 70, 90), tip, f, w)
    pygame.draw.circle(surf, GREEN_DARK, (hx, hy), thick * 1.1)
    pygame.draw.circle(surf, GREEN_LIGHT, (hx, hy + thick * 0.3), thick * 0.86)
    pygame.draw.circle(surf, GREEN, (hx - thick * 0.05, hy - thick * 0.2), thick * 0.8)
    for side in (-1, 1):
        ex, ey = hx + fx * thick * 0.35 + px * side * thick * 0.42, hy + fy * thick * 0.35 + py * side * thick * 0.42
        eye = pygame.Surface((int(thick * 0.34), int(thick * 0.62)), pygame.SRCALPHA)
        pygame.draw.rect(eye, EYE, eye.get_rect(), border_radius=int(thick * 0.17))
        eye = pygame.transform.rotate(eye, -math.degrees(ang) + 90)
        surf.blit(eye, eye.get_rect(center=(ex, ey)))


def finish(big: pygame.Surface, out: Path, name: str) -> None:
    img = pygame.transform.smoothscale(big, (S, S))
    pygame.image.save(img, str(out / f"{name}.png"))
    # preview: the circle crop YouTube applies, and how it looks at 48px
    prev = pygame.Surface((S + 200, S), pygame.SRCALPHA)
    prev.fill((24, 24, 24))
    circ = pygame.Surface((S, S), pygame.SRCALPHA)
    circ.blit(img, (0, 0))
    mask = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (S // 2, S // 2), S // 2)
    circ.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    prev.blit(circ, (0, 0))
    prev.blit(pygame.transform.smoothscale(circ, (48, 48)), (S + 76, S // 2 - 24))
    prev.blit(pygame.transform.smoothscale(circ, (98, 98)), (S + 51, S // 2 - 160))
    pygame.image.save(prev, str(out / f"{name}_circle_preview.png"))


def make(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    # 1. S-snake
    big = sky(moon=False)
    draw_snake(big, s_path(), N * 0.075)
    finish(big, out, "avatar_1_s_snake")

    # 2. the real head + tongue sprites, close up
    big = sky(moon=True)
    head = pygame.image.load(str(ROOT / "assets/art/snake_head.png")).convert_alpha()
    body = pygame.image.load(str(ROOT / "assets/art/snake_body.png")).convert_alpha()
    hs = N * 0.44 / head.get_width()
    head = pygame.transform.smoothscale_by(head, hs)
    body = pygame.transform.smoothscale_by(body, hs)
    y = int(N * 0.56)
    hx = int(N * 0.40)
    for i in range(4):  # body segments trailing off to the left
        big.blit(body, (hx - int(body.get_width() * 0.8) * (i + 1), y - body.get_height() // 2 + 4 * K))
    big.blit(head, (hx, y - head.get_height() // 2))
    finish(big, out, "avatar_2_sprite")

    # 3. monogram
    big = sky(moon=False, stars=True)
    f = pygame.font.Font(BODY, int(N * 0.40))
    letters = [f.render(ch, True, ACCENT) for ch in "MS"]
    gap = int(N * 0.005)
    total = sum(l.get_width() for l in letters) + gap
    x, y = N // 2 - total // 2, N // 2 - f.get_height() // 2 - int(N * 0.04)
    glow = pygame.Surface((N, N), pygame.SRCALPHA)
    gx = x
    for l in letters:
        m = pygame.mask.from_surface(l, 40).to_surface(setcolor=(*ACCENT, 255), unsetcolor=(*ACCENT, 0))
        glow.blit(m, (gx, y))
        gx += l.get_width() + gap
    for k in (14, 6):
        glow = pygame.transform.smoothscale(pygame.transform.smoothscale(glow, (N // k, N // k)), (N, N))
    glow.set_alpha(160)
    big.blit(glow, (0, 0))
    for ch, l in zip("MS", letters):
        big.blit(f.render(ch, True, (4, 6, 10)), (x + 3 * K, y + 5 * K))
        big.blit(l, (x, y))
        x += l.get_width() + gap
    ly, cx, half = y + f.get_height() + int(N * 0.01), N // 2, int(N * 0.26)
    for side in (-1, 1):
        for i in range(half):
            a = (1 - i / half) ** 1.5
            pygame.draw.line(big, tuple(int(c * a + 14 * (1 - a)) for c in ACCENT),
                             (cx + side * (10 * K + i), ly), (cx + side * (10 * K + i + 1), ly), 3 * K)
    d = 9 * K
    pygame.draw.polygon(big, ACCENT, [(cx, ly - d), (cx + d, ly), (cx, ly + d), (cx - d, ly)])
    finish(big, out, "avatar_3_monogram")


if __name__ == "__main__":
    make(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("thumbnails"))
