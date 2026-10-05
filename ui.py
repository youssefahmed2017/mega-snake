"""Mouse-first widget toolkit: a per-frame hotspot record plus the drawing helpers
(buttons, toggles, sliders, arrows, scrollbars) shared by every menu screen.

Screens register a `Hot` for each clickable region while they draw; `Game` routes
mouse events to whichever hotspot is under the cursor. Keyboard handling is left
untouched - a click just points the same selection index at a row and replays the
same key a player would have pressed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import pygame

import gfx
from constants import ACCENT, TEXT, TEXT_DIM

PANEL = (30, 32, 42)
PANEL_HOVER = (42, 46, 62)
BORDER = (60, 64, 80)
TRACK = (40, 42, 54)


@dataclass
class Hot:
    rect: pygame.Rect
    attr: Optional[str] = None   # Game attribute pointed at `index` while hovered/clicked
    index: int = 0
    click: Optional[Callable[[], None]] = None
    adjust: Optional[Callable[[int], None]] = None      # mouse wheel: +1 up, -1 down
    drag: Optional[Callable[[Tuple[int, int]], None]] = None  # cursor pos while button held


def hovered(rect: pygame.Rect) -> bool:
    return rect.collidepoint(gfx.mouse_pos())


_sel = {"key": None, "t0": 0}
_ORN_W = 64


def _ornament(h: int, color, alpha: int) -> pygame.Surface:
    """One side of the selector, pointing right (toward the text): a tapering
    line, a small diamond and a chevron. The other side is this, flipped."""
    surf = gfx.surface((_ORN_W, h), pygame.SRCALPHA)
    cy = h // 2
    for x in range(0, 36):  # line fades in toward the diamond
        a = int(alpha * (x / 36) ** 1.6 * 0.7)
        gfx.draw.line(surf, (*color, a), (x, cy), (x, cy))
    gfx.draw.polygon(surf, (*color, alpha), [(41, cy), (45, cy - 4), (49, cy), (45, cy + 4)])
    gfx.draw.lines(surf, (*color, alpha), False, [(53, cy - 8), (61, cy), (53, cy + 8)], 2)
    return surf


def draw_row_highlight(surf: pygame.Surface, rect: pygame.Rect, selected: bool) -> None:
    """Hollow Knight-style selector: ornate  --<> >   text   < <>--  brackets that
    slide in from the sides, then gently breathe."""
    if not selected:
        return
    now = pygame.time.get_ticks()
    key = (rect.x, rect.y, rect.w)
    if _sel["key"] != key:
        _sel["key"], _sel["t0"] = key, now
    p = min(1.0, (now - _sel["t0"]) / 190)
    ease = 1 - (1 - p) ** 3
    pulse = 0.5 + 0.5 * math.sin(now / 240)
    color = tuple(int(c + (255 - c) * 0.35 * pulse) for c in ACCENT)
    orn = _ornament(rect.h + 4, color, int(255 * ease))
    slide = (1 - ease) * 22 + pulse * 2.5
    surf.blit(orn, (rect.left - _ORN_W + 6 - slide, rect.top - 2))
    surf.blit(gfx.flip(orn, True, False), (rect.right - 6 + slide, rect.top - 2))


def draw_button(surf: pygame.Surface, rect: pygame.Rect, label: str, font: pygame.font.Font,
                primary: bool = False, enabled: bool = True) -> None:
    over = enabled and hovered(rect)
    fill = PANEL_HOVER if over else PANEL
    edge = ACCENT if (primary or over) and enabled else BORDER
    gfx.draw.rect(surf, fill, rect, border_radius=8)
    gfx.draw.rect(surf, edge, rect, width=2, border_radius=8)
    color = (TEXT if over or primary else TEXT_DIM) if enabled else (80, 84, 98)
    text = font.render(label, True, color)
    surf.blit(text, (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2))


def draw_toggle(surf: pygame.Surface, rect: pygame.Rect, on: bool) -> None:
    gfx.draw.rect(surf, ACCENT if on else TRACK, rect, border_radius=rect.h // 2)
    r = rect.h // 2 - 3
    cx = rect.right - rect.h // 2 if on else rect.x + rect.h // 2
    gfx.draw.circle(surf, (245, 247, 252) if on else (130, 134, 150), (cx, rect.centery), r)


def draw_slider(surf: pygame.Surface, track: pygame.Rect, frac: float, active: bool = False) -> None:
    frac = max(0.0, min(1.0, frac))
    gfx.draw.rect(surf, TRACK, track, border_radius=track.h // 2)
    if frac > 0:
        fill = pygame.Rect(track.x, track.y, max(track.h, int(track.w * frac)), track.h)
        gfx.draw.rect(surf, ACCENT, fill, border_radius=track.h // 2)
    knob_r = track.h + 3 + (2 if active or hovered(track.inflate(0, 20)) else 0)
    gfx.draw.circle(surf, (245, 247, 252), (track.x + int(track.w * frac), track.centery), knob_r)


def draw_arrow(surf: pygame.Surface, rect: pygame.Rect, direction: int) -> None:
    color = ACCENT if hovered(rect) else TEXT_DIM
    cx, cy, h = rect.centerx, rect.centery, min(rect.h, 14) // 2
    if direction < 0:
        pts = [(cx + h // 2, cy - h), (cx + h // 2, cy + h), (cx - h // 2, cy)]
    else:
        pts = [(cx - h // 2, cy - h), (cx - h // 2, cy + h), (cx + h // 2, cy)]
    gfx.draw.polygon(surf, color, pts)


def draw_scrollbar(surf: pygame.Surface, track: pygame.Rect, offset: float, content_h: float,
                   view_h: float) -> pygame.Rect:
    """Draws a vertical scrollbar and returns the thumb rect (for hit-testing)."""
    gfx.draw.rect(surf, TRACK, track, border_radius=track.w // 2)
    if content_h <= view_h:
        return pygame.Rect(track.x, track.y, track.w, track.h)
    thumb_h = max(28, int(track.h * view_h / content_h))
    span = content_h - view_h
    thumb_y = track.y + int((track.h - thumb_h) * (offset / span))
    thumb = pygame.Rect(track.x, thumb_y, track.w, thumb_h)
    gfx.draw.rect(surf, ACCENT if hovered(track) else BORDER, thumb, border_radius=track.w // 2)
    return thumb


class SnakeCursor:
    """A little snake that replaces the system mouse pointer. The head sits exactly
    on the real pointer position (so clicks land where you see them); the body
    trails behind and settles wherever you stop. It flicks its tongue and perks up
    over anything clickable."""

    SEGS = 8
    SPACING = 4.2

    def __init__(self) -> None:
        self.pts = [[-100.0, -100.0] for _ in range(self.SEGS)]
        self.heading = (1.0, 0.0)
        self.started = False

    def update(self, target) -> None:
        tx, ty = target
        if not self.started:
            self.pts = [[float(tx) - i * self.SPACING, float(ty)] for i in range(self.SEGS)]
            self.started = True
        self.pts[0][0], self.pts[0][1] = tx, ty
        for i in range(1, self.SEGS):
            px, py = self.pts[i - 1]
            x, y = self.pts[i]
            dx, dy = px - x, py - y
            dist = math.hypot(dx, dy)
            if dist > self.SPACING:
                k = (dist - self.SPACING) / dist
                self.pts[i][0] += dx * k
                self.pts[i][1] += dy * k
        hx, hy = self.pts[0][0] - self.pts[2][0], self.pts[0][1] - self.pts[2][1]
        n = math.hypot(hx, hy)
        if n > 1.5:
            self.heading = (hx / n, hy / n)

    def draw(self, surf: pygame.Surface, head_color, body_color, excited: bool) -> None:
        now = pygame.time.get_ticks()
        for i in range(self.SEGS - 1, 0, -1):
            x, y = self.pts[i]
            r = 3.3 - 1.8 * (i / self.SEGS)
            shade = tuple(int(c * (0.78 + 0.22 * (1 - i / self.SEGS))) for c in body_color)
            gfx.draw.circle(surf, (10, 12, 16), (int(x), int(y)), int(r + 1))
            gfx.draw.circle(surf, shade, (int(x), int(y)), int(r))
        hx, hy = self.pts[0]
        ux, uy = self.heading
        px, py = -uy, ux
        scale = 1.2 if excited else 1.0
        tongue_out = excited or (now // 90) % 24 < 3
        if tongue_out:
            bx, by = hx + ux * 4.5 * scale, hy + uy * 4.5 * scale
            tipx, tipy = hx + ux * 10 * scale, hy + uy * 10 * scale
            gfx.draw.line(surf, (235, 70, 90), (bx, by), (tipx, tipy), 2)
            for sgn in (-1, 1):
                gfx.draw.line(surf, (235, 70, 90), (tipx, tipy),
                                 (tipx + (ux + sgn * px * 0.7) * 2.5, tipy + (uy + sgn * py * 0.7) * 2.5), 1)
        gfx.draw.circle(surf, (10, 12, 16), (int(hx), int(hy)), int(4.6 * scale + 1))
        gfx.draw.circle(surf, head_color, (int(hx), int(hy)), int(4.6 * scale))
        for sgn in (-1, 1):
            ex, ey = hx + ux * 1.6 * scale + px * 2.2 * sgn * scale, hy + uy * 1.6 * scale + py * 2.2 * sgn * scale
            gfx.draw.circle(surf, (250, 250, 250), (int(ex), int(ey)), int(1.5 * scale))
            gfx.draw.circle(surf, (15, 15, 20), (int(ex + ux * 0.6), int(ey + uy * 0.6)), 1)
