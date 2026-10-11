# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""YouTube thumbnails (1280x720) in the game's own visual identity.

    python tools/trailer/thumbnail.py [out_dir]

Replays two of record.py's scenes with the same seeds and grabs clean frames (the
in-game announcer and achievement pop-ups hidden), then composes three designs
around the menu key art (assets/art/menu_bg.png) and the game's letter-spaced
wordmark:
  1. key art     - the moonlit river landscape with the wordmark in the sky
  2. logo + card - wordmark on the left, a framed gameplay screenshot on the right
  3. cinematic   - full-bleed graded gameplay, letterboxed, wordmark on the lower third
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


ACCENT = (90, 200, 255)
BODY = str(ROOT / "assets/fonts/VarelaRound-Regular.ttf")


def wordmark(surf, cx, y, size=96, gap=None, color=ACCENT, glow=True):
    """The game's own title treatment (see Game._draw_menu_title): letter-spaced Varela
    Round in the accent blue, a soft shadow, and a thin fading rule with a diamond."""
    f = pygame.font.Font(BODY, size)
    gap = int(size * 0.18) if gap is None else gap
    letters = [f.render(ch, True, color) for ch in "MEGA SNAKE"]
    total = sum(l.get_width() for l in letters) + gap * (len(letters) - 1)
    if glow:
        # soft halo: the letters' alpha as a mask, blurred, alpha-blended (not added)
        g = pygame.Surface((total + 240, f.get_height() + 240), pygame.SRCALPHA)
        x = 120
        for l in letters:
            m = pygame.mask.from_surface(l, 40).to_surface(setcolor=(*color, 255), unsetcolor=(*color, 0))
            g.blit(m, (x, 120))
            x += l.get_width() + gap
        for k in (10, 5):
            small = pygame.transform.smoothscale(g, (max(1, g.get_width() // k), max(1, g.get_height() // k)))
            g = pygame.transform.smoothscale(small, g.get_size())
        g.set_alpha(150)
        surf.blit(g, (cx - total // 2 - 120, y - 120))
    x = cx - total // 2
    for ch, l in zip("MEGA SNAKE", letters):
        s = f.render(ch, True, (4, 6, 10))
        surf.blit(s, (x + size // 25, y + size // 17))
        surf.blit(l, (x, y))
        x += l.get_width() + gap
    ly = y + f.get_height() + size // 8
    half = int(total * 0.42)
    for side in (-1, 1):
        for i in range(half):
            a = (1 - i / half) ** 1.5
            c = tuple(int(cc * a + 10 * (1 - a)) for cc in color)
            pygame.draw.line(surf, c, (cx + side * (size // 6 + i), ly), (cx + side * (size // 6 + i + 1), ly), max(2, size // 40))
    d = size // 10
    pygame.draw.polygon(surf, color, [(cx, ly - d), (cx + d, ly), (cx, ly + d), (cx - d, ly)])
    return ly


def spaced(surf, s, size, color, center, gap=6, font=BODY, alpha=255):
    f = pygame.font.Font(font, size)
    letters = [f.render(ch, True, color) for ch in s]
    total = sum(l.get_width() for l in letters) + gap * (len(letters) - 1)
    x, y = center[0] - total // 2, center[1] - f.get_height() // 2
    for l in letters:
        if alpha < 255:
            l.set_alpha(alpha)
        surf.blit(l, (x, y))
        x += l.get_width() + gap


def grade(surf: pygame.Surface, lift=(6, 12, 18), sat=1.1, contrast=1.08) -> pygame.Surface:
    """Gentle cinematic grade: a touch more contrast, cool shadows."""
    a = pygame.surfarray.array3d(surf).astype(np.float32)
    gray = a.mean(axis=2, keepdims=True)
    a = gray + (a - gray) * sat
    a = (a - 128) * contrast + 128
    a = a + np.array(lift, np.float32) * (1 - a / 255)
    return pygame.surfarray.make_surface(np.clip(a, 0, 255).astype(np.uint8))


def soft_shadow(surf, rect, radius=28, spread=40, alpha=170):
    sh = pygame.Surface((rect.w + spread * 2, rect.h + spread * 2), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, alpha), pygame.Rect(spread, spread, rect.w, rect.h), border_radius=radius)
    small = pygame.transform.smoothscale(sh, (sh.get_width() // 10, sh.get_height() // 10))
    sh = pygame.transform.smoothscale(small, sh.get_size())
    surf.blit(sh, (rect.x - spread, rect.y - spread + 14))


def rounded(img: pygame.Surface, radius: int) -> pygame.Surface:
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    out.blit(img, (0, 0))
    mask = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


def make(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rec = Recorder(Path(tempfile.mkdtemp(prefix="thumbclips-")))
    chaos = grab(rec, "chaos_max", 2.5)
    battle = grab(rec, "chaos_battle", 1.9)
    key = pygame.image.load(str(ROOT / "assets/art/menu_bg.png")).convert()

    # 1. KEY ART - the menu landscape (its river is the snake), the wordmark in the sky
    img, _ = cover(key)
    img = grade(img, sat=1.05)
    ly = wordmark(img, W // 2, 205, size=96)
    spaced(img, "OFFICIAL TRAILER", 26, (225, 235, 245), (W // 2, ly + 44), gap=9, alpha=215)
    pygame.image.save(img, str(out / "thumbnail_1_key_art.png"))

    # 2. LOGO + GAMEPLAY CARD - wordmark left, a framed screenshot right, on the key art
    img, _ = cover(key)
    img.fill((150, 160, 170), special_flags=pygame.BLEND_RGB_MULT)
    shot = grade(board(battle["img"]))
    cw = 700
    card = pygame.transform.smoothscale(shot, (cw, int(cw * shot.get_height() / shot.get_width())))
    r = card.get_rect(midright=(W - 48, H // 2 + 6))
    soft_shadow(img, r)
    img.blit(rounded(card, 18), r)
    pygame.draw.rect(img, ACCENT, r.inflate(6, 6), 3, border_radius=20)
    lx = (r.left) // 2 + 8
    f = pygame.font.Font(BODY, 84)
    for i, (word, col) in enumerate((("MEGA", ACCENT), ("SNAKE", ACCENT))):
        letters = [f.render(ch, True, col) for ch in word]
        gap = 14
        total = sum(l.get_width() for l in letters) + gap * (len(letters) - 1)
        x, y = lx - total // 2, 200 + i * 108
        for l, ch in zip(letters, word):
            img.blit(f.render(ch, True, (4, 6, 10)), (x + 3, y + 5))
            img.blit(l, (x, y))
            x += l.get_width() + gap
    ly = 200 + 2 * 108 + 6
    for side in (-1, 1):
        for i in range(150):
            a = (1 - i / 150) ** 1.5
            pygame.draw.line(img, tuple(int(c * a + 10 * (1 - a)) for c in ACCENT), (lx + side * (14 + i), ly),
                             (lx + side * (15 + i), ly), 3)
    pygame.draw.polygon(img, ACCENT, [(lx, ly - 8), (lx + 8, ly), (lx, ly + 8), (lx - 8, ly)])
    spaced(img, "OFFICIAL TRAILER", 24, (225, 235, 245), (lx, ly + 52), gap=7, alpha=220)
    spaced(img, "Windows · macOS · Linux", 20, (160, 190, 210), (lx, ly + 92), gap=2, alpha=200)
    pygame.image.save(img, str(out / "thumbnail_2_logo_and_gameplay.png"))

    # 3. CINEMATIC - full-bleed gameplay, graded and letterboxed, wordmark on the lower third
    b = board(chaos["img"])
    img, _ = cover(grade(b, lift=(4, 8, 16), sat=1.0, contrast=1.05), zoom=1.0)
    fade = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(H):
        t = min(1.0, max(0.0, (y - H * 0.25) / (H * 0.45)))
        pygame.draw.line(fade, (6, 9, 14, int(245 * t ** 1.1)), (0, y), (W, y))
    img.blit(fade, (0, 0))
    vignette(img, 150)
    bar = 46
    pygame.draw.rect(img, (0, 0, 0), (0, 0, W, bar))
    pygame.draw.rect(img, (0, 0, 0), (0, H - bar, W, bar))
    ly = wordmark(img, W // 2, 420, size=92)
    spaced(img, "OFFICIAL TRAILER", 24, (225, 235, 245), (W // 2, ly + 42), gap=9, alpha=220)
    pygame.image.save(img, str(out / "thumbnail_3_cinematic.png"))


if __name__ == "__main__":
    pygame.font.init()
    make(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("thumbnails"))
