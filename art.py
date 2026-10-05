"""Sprite cache for the processed art in assets/art/ (see tools/prepare_art.py).

Every lookup returns an HSurface at the right pixel density for the current
resolution, or None when the file is missing - callers then fall back to the old
vector drawing, so the game still runs without (or with only some of) the art.
"""
from __future__ import annotations

import colorsys
import os
from typing import Dict, Optional, Tuple

import numpy as np
import pygame

import gfx

# The snake sprites are painted in this green; skins recolour it by shifting hue.
_REF_BODY = (61, 187, 107)


def _rgb_to_hsv(rgb: np.ndarray):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rc = nz & (mx == r)
    gc = nz & (mx == g) & ~rc
    bc = nz & ~rc & ~gc
    h[rc] = ((g - b)[rc] / d[rc]) % 6
    h[gc] = (b - r)[gc] / d[gc] + 2
    h[bc] = (r - g)[bc] / d[bc] + 4
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return h / 6.0, s, mx


def _hsv_to_rgb(h, s, v):
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    out = np.zeros(h.shape + (3,))
    for k, (rr, gg, bb) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k
        out[m, 0], out[m, 1], out[m, 2] = rr[m], gg[m], bb[m]
    return out


def recolor(surf: pygame.Surface, target: Tuple[int, int, int]) -> pygame.Surface:
    """Shift the sprite's green pixels toward `target`, leaving the navy outline, the
    white eyes and anything non-green alone."""
    ref_h, ref_s, ref_v = colorsys.rgb_to_hsv(*(c / 255 for c in _REF_BODY))
    th, ts, tv = colorsys.rgb_to_hsv(*(c / 255 for c in target))
    rgb = pygame.surfarray.array3d(surf).astype(float) / 255
    alpha = pygame.surfarray.array_alpha(surf)
    h, s, v = _rgb_to_hsv(rgb)
    green = (s > 0.25) & (h > 80 / 360) & (h < 175 / 360)
    nh = np.where(green, (h - ref_h + th) % 1.0, h)
    ns = np.where(green, np.clip(s * ts / ref_s, 0, 1), s)
    nv = np.where(green, np.clip(v * tv / ref_v, 0, 1), v)
    out = surf.copy()
    pygame.surfarray.pixels3d(out)[:] = (_hsv_to_rgb(nh, ns, nv) * 255).astype(np.uint8)
    pygame.surfarray.pixels_alpha(out)[:] = alpha
    return out


class Art:
    def __init__(self, folder: str) -> None:
        self.raw: Dict[str, pygame.Surface] = {}
        self._tinted: Dict[Tuple[str, Tuple[int, int, int]], pygame.Surface] = {}
        self._cache: Dict[tuple, gfx.HSurface] = {}
        if os.path.isdir(folder):
            for fn in os.listdir(folder):
                if fn.lower().endswith(".png"):
                    self.raw[fn[:-4]] = pygame.image.load(os.path.join(folder, fn)).convert_alpha()

    def snake_palette(self, tint: Optional[Tuple[int, int, int]]) -> Tuple[tuple, tuple, tuple]:
        """(shadow, base, belly) colours of the snake art, recoloured for a skin. The smooth body is
        drawn with these, so it matches the head sprite exactly."""
        key = ("palette", tint)
        hit = self._tinted.get(key)
        if hit is None:
            base, belly = (38, 191, 101), (114, 222, 157)
            body = self.raw.get("snake_body")
            if body is not None:
                w, h = body.get_size()
                base, belly = tuple(body.get_at((w // 2, int(h * 0.3)))[:3]), tuple(body.get_at((w // 2, int(h * 0.85)))[:3])
            shadow = tuple(int(c * 0.78) for c in base)
            swatch = pygame.Surface((3, 1), pygame.SRCALPHA)
            for i, c in enumerate((shadow, base, belly)):
                swatch.set_at((i, 0), (*c, 255))
            if tint is not None:
                swatch = recolor(swatch, tint)
            hit = tuple(tuple(swatch.get_at((i, 0))[:3]) for i in range(3))
            self._tinted[key] = hit
        return hit

    def has(self, name: str) -> bool:
        return name in self.raw

    def clear(self) -> None:
        """Drop scaled copies (the resolution changed)."""
        self._cache.clear()

    def get(self, name: str, w: Optional[float] = None, h: Optional[float] = None, rot: int = 0,
            flip: bool = False, tint: Optional[Tuple[int, int, int]] = None,
            alpha: Optional[int] = None, fit: Optional[float] = None, angle: float = 0.0,
            vflip: bool = False) -> Optional[gfx.HSurface]:
        """Sprite scaled to w x h *logical* units (give one to keep the aspect ratio).
        `rot` is counter-clockwise degrees, multiples of 90 only; `angle` is ANY counter-clockwise
        angle (smoothly resampled; w/h still describe the unrotated sprite, the result is its
        rotated bounding box); `vflip` mirrors top-bottom first; `tint` recolours the snake."""
        src = self.raw.get(name)
        if src is None:
            return None
        k = gfx.scale()
        angle = round(angle / 4.0) * 4.0 % 360  # 4-degree steps keep the cache small and look continuous
        key = (name, w, h, fit, rot % 360, flip, tint, alpha, angle, vflip, round(k, 4))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        if tint is not None:
            tkey = (name, tint)
            if tkey not in self._tinted:
                self._tinted[tkey] = recolor(src, tint)
            src = self._tinted[tkey]
        if flip:
            src = pygame.transform.flip(src, True, False)
        if vflip:
            src = pygame.transform.flip(src, False, True)
        if rot % 360:
            src = pygame.transform.rotate(src, rot % 360)
        sw, sh = src.get_size()
        if fit is not None:  # fit inside a fit x fit box, keeping the aspect ratio
            w, h = sw * fit / max(sw, sh), sh * fit / max(sw, sh)
        elif w is None and h is None:
            w, h = sw / 4, sh / 4
        elif h is None:
            h = w * sh / sw
        elif w is None:
            w = h * sw / sh
        size = (max(1, round(w * k)), max(1, round(h * k)))
        scaled = pygame.transform.smoothscale(src, size)
        if angle:
            scaled = pygame.transform.rotozoom(scaled, angle, 1.0)
        sprite = gfx.wrap(scaled, k)
        if alpha is not None:
            sprite.set_alpha(alpha)
        self._cache[key] = sprite
        return sprite
