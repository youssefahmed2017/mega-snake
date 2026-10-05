"""Resolution-independent drawing.

All game code lays things out in *logical* units (the 1028x528 canvas). Surfaces made
here (HSurface) are physically `k` times bigger, and the drawing helpers below scale
logical coordinates up to real pixels, so the same code renders crisply at 720p,
1080p or 4K instead of being a small canvas stretched to fit.

    gfx.surface(size)        like pygame.Surface(size), but k times denser
    gfx.draw.rect/circle/... like pygame.draw.*, taking logical coordinates
    gfx.Font(path, size)     renders text at physical size, reports logical metrics
    gfx.mouse_pos()          mouse position in logical units
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple

import pygame

_K = 1.0
_offset = (0, 0)       # where the canvas sits inside the window (letterboxing)
_fonts: List["Font"] = []


def scale() -> float:
    return _K


def asset_path(rel: str) -> str:
    """Bundled data files: next to this module, or inside the PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / rel)


def set_scale(k: float) -> None:
    global _K
    _K = k
    for f in _fonts:
        f._build()


def set_offset(offset: Tuple[int, int]) -> None:
    global _offset
    _offset = offset


def to_logical(pos) -> Tuple[float, float]:
    return ((pos[0] - _offset[0]) / _K, (pos[1] - _offset[1]) / _K)


def to_physical(pos) -> Tuple[int, int]:
    return (round(pos[0] * _K + _offset[0]), round(pos[1] * _K + _offset[1]))


def mouse_pos() -> Tuple[float, float]:
    return to_logical(pygame.mouse.get_pos())


def _edges(rect, k: float) -> pygame.Rect:
    """Scale a logical rect by snapping its *edges* (not its size), so neighbouring
    cells share a boundary instead of leaving one-pixel seams."""
    x, y, w, h = rect
    x0, y0 = round(x * k), round(y * k)
    x1, y1 = round((x + w) * k), round((y + h) * k)
    return pygame.Rect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


class HSurface(pygame.Surface):
    """A surface that is `k` physical pixels per logical unit but speaks logical units."""

    def __init__(self, size, flags: int = 0, k: Optional[float] = None, physical=None) -> None:
        k = _K if k is None else k
        lw, lh = max(1, round(size[0])), max(1, round(size[1]))
        phys = physical or (max(1, round(lw * k)), max(1, round(lh * k)))
        super().__init__(phys, flags)
        self.k = k
        self.lsize = (lw, lh)

    # --- logical-size queries -------------------------------------------------
    def get_width(self) -> int:
        return self.lsize[0]

    def get_height(self) -> int:
        return self.lsize[1]

    def get_size(self) -> Tuple[int, int]:
        return self.lsize

    def get_rect(self, **kw) -> pygame.Rect:
        r = pygame.Rect(0, 0, *self.lsize)
        for name, value in kw.items():
            setattr(r, name, value)
        return r

    def copy(self) -> "HSurface":
        c = HSurface(self.lsize, self.get_flags() & pygame.SRCALPHA, self.k)
        pygame.Surface.blit(c, self, (0, 0))
        c.set_alpha(self.get_alpha())
        return c

    # --- drawing in logical units ---------------------------------------------
    def blit(self, source, dest=(0, 0), area=None, special_flags: int = 0):
        k = self.k
        if isinstance(source, HSurface):
            if abs(source.k - k) > 1e-6:  # built at another resolution: resample
                size = (max(1, round(source.lsize[0] * k)), max(1, round(source.lsize[1] * k)))
                alpha = source.get_alpha()
                source = pygame.transform.smoothscale(source, size)
                if alpha is not None:
                    source.set_alpha(alpha)
                src_k = k
            else:
                src_k = source.k
        else:  # a plain surface is taken to be in logical pixels
            size = (max(1, round(source.get_width() * k)), max(1, round(source.get_height() * k)))
            alpha = source.get_alpha()
            source = pygame.transform.smoothscale(source, size) if source.get_flags() & pygame.SRCALPHA \
                or source.get_bitsize() >= 24 else pygame.transform.scale(source, size)
            if alpha is not None:
                source.set_alpha(alpha)
            src_k = k
        if isinstance(dest, pygame.Rect):
            dx, dy = dest.x, dest.y
        else:
            dx, dy = dest[0], dest[1]
        if area is not None:
            area = _edges(area, src_k)
        return pygame.Surface.blit(self, source, (round(dx * k), round(dy * k)), area, special_flags)

    def fill(self, color, rect=None, special_flags: int = 0):
        if rect is not None:
            rect = _edges(rect, self.k)
        return pygame.Surface.fill(self, color, rect, special_flags)

    def set_clip(self, rect=None) -> None:
        pygame.Surface.set_clip(self, None if rect is None else _edges(rect, self.k))

    def get_clip(self) -> pygame.Rect:
        c = pygame.Surface.get_clip(self)
        return pygame.Rect(round(c.x / self.k), round(c.y / self.k), round(c.w / self.k), round(c.h / self.k))


def surface(size, flags: int = 0) -> HSurface:
    return HSurface(size, flags)


def wrap(phys: pygame.Surface, k: Optional[float] = None) -> HSurface:
    """Adopt an already-physical-size surface (a rendered glyph run, a flipped band)
    as an HSurface of the matching logical size."""
    k = _K if k is None else k
    out = HSurface((phys.get_width() / k, phys.get_height() / k), pygame.SRCALPHA, k, phys.get_size())
    pygame.Surface.blit(out, phys, (0, 0))
    return out


def flip(surf: HSurface, flip_x: bool, flip_y: bool) -> HSurface:
    return wrap(pygame.transform.flip(surf, flip_x, flip_y), surf.k)


def zoom(surf: HSurface, factor: float) -> HSurface:
    """Smooth-scale an HSurface by `factor` (used for the golden-rush zoom pulse)."""
    size = (max(1, round(pygame.Surface.get_width(surf) * factor)),
            max(1, round(pygame.Surface.get_height(surf) * factor)))
    return wrap(pygame.transform.smoothscale(surf, size), surf.k)


# ---------------------------------------------------------------- pygame.draw.* ---

def _k(surf) -> float:
    return getattr(surf, "k", 1.0)


def _w(width, k: float) -> int:
    return 0 if width <= 0 else max(1, round(width * k))


def _r(radius, k: float) -> int:
    return radius if radius < 0 else (0 if radius <= 0 else max(1, round(radius * k)))


def _pt(p, k: float):
    return (p[0] * k, p[1] * k)


_RADIUS_KW = ("border_radius", "border_top_left_radius", "border_top_right_radius",
              "border_bottom_left_radius", "border_bottom_right_radius")


def _rect(surf, color, rect, width=0, **kw):
    k = _k(surf)
    for name in _RADIUS_KW:
        if name in kw:
            kw[name] = _r(kw[name], k)
    return pygame.draw.rect(surf, color, _edges(rect, k), _w(width, k), **kw)


def _circle(surf, color, center, radius, width=0, **kw):
    k = _k(surf)
    return pygame.draw.circle(surf, color, _pt(center, k), _r(radius, k), _w(width, k), **kw)


def _ellipse(surf, color, rect, width=0):
    k = _k(surf)
    return pygame.draw.ellipse(surf, color, _edges(rect, k), _w(width, k))


def _arc(surf, color, rect, start, stop, width=1):
    k = _k(surf)
    return pygame.draw.arc(surf, color, _edges(rect, k), start, stop, _w(width, k) or 1)


def _line(surf, color, start, end, width=1):
    k = _k(surf)
    return pygame.draw.line(surf, color, _pt(start, k), _pt(end, k), _w(width, k) or 1)


def _lines(surf, color, closed, points, width=1):
    k = _k(surf)
    return pygame.draw.lines(surf, color, closed, [_pt(p, k) for p in points], _w(width, k) or 1)


def _polygon(surf, color, points, width=0):
    k = _k(surf)
    return pygame.draw.polygon(surf, color, [_pt(p, k) for p in points], _w(width, k))


draw = SimpleNamespace(rect=_rect, circle=_circle, ellipse=_ellipse, arc=_arc, line=_line,
                       lines=_lines, polygon=_polygon)


# --------------------------------------------------------------------------- fonts ---

class Font:
    """Renders at physical size (so text is sharp at any resolution) but reports its
    metrics in logical units. Rebuilds itself when the resolution changes."""

    def __init__(self, path: Optional[str], size: float, bold: bool = False) -> None:
        self.path, self.pt, self.bold = path, size, bold
        self._cache: dict = {}
        _fonts.append(self)
        self._build()

    def _build(self) -> None:
        self._cache.clear()
        self._f = pygame.font.Font(self.path, max(1, round(self.pt * _K)))
        if self.bold:
            self._f.set_bold(True)

    def render(self, text: str, antialias: bool = True, color=(255, 255, 255), background=None) -> HSurface:
        """Cached: menus re-render the same labels every frame. The returned surface is
        shared, so call .copy() before changing its alpha."""
        key = (text, tuple(color))
        surf = self._cache.get(key)
        if surf is None:
            if len(self._cache) > 400:
                self._cache.clear()
            surf = self._cache[key] = wrap(self._f.render(text, True, color), _K)
        return surf

    def size(self, text: str) -> Tuple[int, int]:
        w, h = self._f.size(text)
        return round(w / _K), round(h / _K)

    def get_height(self) -> int:
        return round(self._f.get_height() / _K)

    def set_bold(self, bold: bool) -> None:
        self.bold = bold
        self._f.set_bold(bold)
