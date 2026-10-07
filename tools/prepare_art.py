# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Turn the raw ChatGPT art in assets/source/ into game-ready sprites in assets/art/.

    pip install numpy scipy pygame-ce      (dev-only; the game itself doesn't need scipy)
    python tools/prepare_art.py

What it does:
  * keys the flat-magenta backgrounds out of the sprite sheets, and un-mixes the anti-aliased
    edge pixels (outline blended with magenta) so there are no pink fringes,
  * splits each sheet into individual sprites by finding the separate blobs,
  * removes the fake checkerboard "transparency" baked into wall_tile.png,
  * cleans up the sidebar panel and pulls the grass tufts out of the board background.
Re-run it any time you replace a file in assets/source/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pygame
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "assets" / "source", ROOT / "assets" / "art"
NAVY = np.array([10, 12, 20], dtype=float)  # the outline colour used by every sprite
MAGENTA = np.array([255, 0, 255], dtype=float)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((1, 1))


def load(name: str) -> np.ndarray:
    surf = pygame.image.load(str(SRC / name))
    return pygame.surfarray.array3d(surf).swapaxes(0, 1).astype(float)  # (H, W, 3)


def save(name: str, rgba: np.ndarray, max_dim: int | None = None, size: tuple | None = None) -> None:
    rgba = rgba.copy()
    rgba[rgba[..., 3] < 1, :3] = NAVY  # so scaling can't bleed magenta/white into edges
    h, w = rgba.shape[:2]
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = rgba[..., :3].swapaxes(0, 1).astype(np.uint8)
    pygame.surfarray.pixels_alpha(surf)[:] = rgba[..., 3].swapaxes(0, 1).astype(np.uint8)
    if size:
        surf = pygame.transform.smoothscale(surf, size)
    elif max_dim and max(w, h) > max_dim:
        s = max_dim / max(w, h)
        surf = pygame.transform.smoothscale(surf, (round(w * s), round(h * s)))
    pygame.image.save(surf, str(OUT / name))
    print(f"  {name:<22} {surf.get_width()}x{surf.get_height()}")


def key_magenta(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lo = np.minimum(r, b)
    strict = (lo > 140) & (g < 0.3 * lo)        # unmistakably the background magenta
    loose = (lo > 60) & (g < 0.5 * lo)          # edge pixels that are mostly magenta
    labels, _ = ndimage.label(loose | strict)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    bg = strict | (np.isin(labels, border[border > 0]) & loose)
    ring = ndimage.binary_dilation(bg, iterations=3) & ~bg
    if ring.any() and np.median(rgb[ring].mean(axis=1)) > 70:
        return _key_flat(rgb, bg)  # outline-free art: its edges aren't navy, so un-mixing can't work
    # Anti-aliased ring: outline pixels blended with magenta. pix = N*(1-t) + M*t.
    t = np.clip((lo - 12) / 240.0, 0, 1)
    t = np.where(ring, t, 0.0)
    alpha = 1.0 - t
    safe = np.maximum(alpha, 0.05)[..., None]
    color = np.clip((rgb - t[..., None] * MAGENTA) / safe, 0, 255)
    alpha = np.where(alpha < 0.06, 0.0, alpha)
    alpha = np.where(bg, 0.0, alpha) * 255
    return np.dstack([color, alpha])


def _key_flat(rgb: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """Keying for art WITHOUT dark outlines: shave the magenta-tinted edge pixels off, recolour the
    edge from the nearest clean interior pixel, and rebuild a soft anti-aliased alpha."""
    fg = ~ndimage.binary_dilation(bg, iterations=1)
    clean = ~ndimage.binary_dilation(bg, iterations=3)
    if not clean.any():
        clean = fg
    _, (iy, ix) = ndimage.distance_transform_edt(~clean, return_indices=True)
    color = rgb[iy, ix]
    alpha = ndimage.gaussian_filter(fg.astype(float), 0.8) * 255
    alpha = np.where(bg, 0.0, alpha)
    return np.dstack([color, alpha])


def split_blobs(rgba: np.ndarray, merge: int, expected: int | None = None, rows: int | None = None):
    """Return sprite crops, ordered left-to-right within top-to-bottom rows."""
    solid = rgba[..., 3] > 40
    merged = ndimage.binary_dilation(solid, iterations=merge)
    labels, n = ndimage.label(merged)
    boxes = []
    for i in range(1, n + 1):
        ys, xs = np.where((labels == i) & solid)
        if len(ys) < 800:  # specks
            continue
        boxes.append((ys.min(), ys.max() + 1, xs.min(), xs.max() + 1))
    # Detached bits (a sparkle next to an apple, a fuse spark) show up as extra small blobs: fold the
    # smallest one into its nearest neighbour until the count is right.
    while expected and len(boxes) > expected:
        boxes.sort(key=lambda b: (b[1] - b[0]) * (b[3] - b[2]))
        y0, y1, x0, x1, *_ = boxes.pop(0)
        cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
        j = min(range(len(boxes)), key=lambda k: (cx - (boxes[k][2] + boxes[k][3]) / 2) ** 2
                + (cy - (boxes[k][0] + boxes[k][1]) / 2) ** 2)
        by0, by1, bx0, bx1 = boxes[j][:4]
        boxes[j] = (min(y0, by0), max(y1, by1), min(x0, bx0), max(x1, bx1))
    if expected and len(boxes) != expected:
        raise SystemExit(f"expected {expected} sprites, found {len(boxes)}: {boxes}")
    if rows and rows > 1:
        boxes.sort(key=lambda b: (b[0] + b[1]) / 2)
        per = len(boxes) // rows
        boxes = sum((sorted(boxes[i * per:(i + 1) * per], key=lambda b: b[2]) for i in range(rows)), [])
    else:
        boxes.sort(key=lambda b: b[2])
    pad = 3
    h, w = rgba.shape[:2]
    return [rgba[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] for y0, y1, x0, x1 in boxes]


def centre_on_spine(rgba: np.ndarray, at: float) -> np.ndarray:
    """Pad the sprite so the vertical middle of its body (measured in the column `at` of the way
    along, away from any protruding eyes/tip) sits exactly on the sprite's centre line. Without this
    the head and the body beads are drawn on slightly different lines and the snake looks crooked."""
    h, w = rgba.shape[:2]
    col = rgba[:, int(w * at), 3] > 128
    rows = np.where(col)[0]
    spine = (rows.min() + rows.max() + 1) / 2
    shift = int(round(h / 2 - spine))          # >0: spine is above centre, pad on top
    if shift == 0:
        return rgba
    pad = np.zeros((abs(shift), w, 4))
    pad[..., :3] = NAVY
    return np.vstack([pad, rgba]) if shift > 0 else np.vstack([rgba, pad])


def sheet(source: str, names: list[str], merge: int, rows: int = 1, max_dim: int = 256) -> None:
    if not (SRC / source).exists():
        print(f"  (skipped: no {source})")
        return
    rgba = key_magenta(load(source))
    if names[:2] == ["snake_head", "snake_body"] and len(split_blobs(rgba, merge)) == 3:
        names = ["snake_head", "snake_body", "snake_tail"]  # newer sheets have no corner piece
    sprites = split_blobs(rgba, merge, expected=len(names), rows=rows)
    spine_at = {"snake_head": 0.12, "snake_body": 0.5, "snake_tail": 0.12}
    for name, sp in zip(names, sprites):
        if name in spine_at:
            sp = centre_on_spine(sp, spine_at[name])
        save(name + ".png", sp, max_dim=max_dim)


def _tongue_source() -> str:
    return "tongue_sheet.png" if (SRC / "tongue_sheet.png").exists() else "tounge_sheet.png"


def prepare_tongue(frames: int = 10) -> None:
    """tongue_sheet.png: `frames` tongue poses left to right, root on the left of each, pointing right.
    ChatGPT never spaces them evenly, so each pose is found as its own blob and then re-placed on a
    shared canvas with its ROOT at the left-centre: every output frame is the same size and the tongue
    grows from exactly the same point, so it can't jump around in game."""
    rgba = key_magenta(load(_tongue_source()))
    poses = split_blobs(rgba, 6, expected=frames)
    roots = []
    for p in poses:
        solid = p[..., 3] > 128
        cols = np.where(solid.any(axis=0))[0]
        first = solid[:, cols[0]:cols[0] + max(3, len(cols) // 12)]
        rows = np.where(first.any(axis=1))[0]
        roots.append((cols[0], (rows.min() + rows.max()) / 2))
    width = max(p.shape[1] - rx for p, (rx, _) in zip(poses, roots))
    half = max(max(ry, p.shape[0] - ry) for p, (_, ry) in zip(poses, roots))
    h = int(np.ceil(half * 2)) + 2
    for i, (p, (rx, ry)) in enumerate(zip(poses, roots)):
        canvas = np.zeros((h, width + 2, 4))
        canvas[..., :3] = p[0, 0, :3]
        top = int(round(h / 2 - ry))
        crop = p[:, rx:]
        canvas[top:top + crop.shape[0], 1:1 + crop.shape[1]] = crop
        save(f"tongue_{i}.png", canvas, max_dim=256)


def prepare_wall() -> None:
    """wall_tile.png has a fake grey/white 'transparent' checkerboard painted in."""
    rgb = load("wall_tile.png")
    corner = rgb[:8, :8].reshape(-1, 3).mean(axis=0)
    if corner[1] < 0.4 * min(corner[0], corner[2]):  # flat magenta background: plain cut-out
        rgba = key_magenta(rgb)
        ys, xs = np.where(rgba[..., 3] > 40)
        save("wall_tile.png", rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1], max_dim=192)
        return
    lum = rgb.mean(axis=2)
    light = (rgb.min(axis=2) > 150) & ((rgb.max(axis=2) - rgb.min(axis=2)) < 30)
    labels, _ = ndimage.label(light)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    bg = np.isin(labels, border[border > 0]) & light
    ring = ndimage.binary_dilation(bg, iterations=3) & ~bg
    bgc = np.array([225.0, 225.0, 225.0])
    t = np.where(ring, np.clip((lum - 14) / (225 - 14), 0, 1), 0.0)
    alpha = 1 - t
    color = np.clip((rgb - t[..., None] * bgc) / np.maximum(alpha, 0.05)[..., None], 0, 255)
    alpha = np.where(bg | (alpha < 0.06), 0, alpha) * 255
    rgba = np.dstack([color, alpha])
    ys, xs = np.where(alpha > 40)
    save("wall_tile.png", rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1], max_dim=192)


def prepare_title() -> None:
    rgba = key_magenta(load("title.png"))
    ys, xs = np.where(rgba[..., 3] > 40)
    save("title.png", rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1], max_dim=1100)


def prepare_sidebar() -> None:
    rgb = load("sidebar_bg.png")
    if rgb.shape[:2] == (1774, 887):  # the first (cartoon) panel had a leaf right under the legend text
        region = rgb[1495:1742, 52:300]
        leafy = (region[..., 1] > 120) & (region[..., 1] > region[..., 0] + 40)
        if leafy.mean() > 0.05:
            rgb[1495:1742, 52:300] = rgb[1400, 450].copy()
    surf = pygame.Surface((rgb.shape[1], rgb.shape[0]))
    pygame.surfarray.pixels3d(surf)[:] = rgb.swapaxes(0, 1).astype(np.uint8)
    pygame.image.save(pygame.transform.smoothscale(surf, (443, 887)), str(OUT / "sidebar_bg.png"))
    print("  sidebar_bg.png         443x887")


def prepare_decor() -> bool:
    """decor_sheet.png: 4 small floor accents in a row (replaces the tufts cut from board_bg)."""
    if not (SRC / "decor_sheet.png").exists():
        return False
    for i, sp in enumerate(split_blobs(key_magenta(load("decor_sheet.png")), 10, expected=4)):
        save(f"tuft_{i}.png", sp, max_dim=96)
    return True


def prepare_board() -> None:
    """Pull the grass tufts out of board_bg.png (the checker itself is redrawn in code so it
    lines up with the game's cells)."""
    rgb = load("board_bg.png")
    g = rgb[..., 1]
    tuft = (g < 30) | (g > 110)  # dark outline or bright leaf, vs the teal checker (g ~ 47-62)
    tuft = ndimage.binary_closing(tuft, iterations=2)
    labels, n = ndimage.label(ndimage.binary_dilation(tuft, iterations=3))
    kept = []
    for i in range(1, n + 1):
        ys, xs = np.where((labels == i) & tuft)
        if len(ys) < 300:
            continue
        kept.append((ys.min(), ys.max() + 1, xs.min(), xs.max() + 1, len(ys)))
    kept.sort(key=lambda b: -b[4])
    alpha_full = ndimage.gaussian_filter(ndimage.binary_dilation(tuft, iterations=1).astype(float), 0.8) * 255
    for idx, (y0, y1, x0, x1, _) in enumerate(kept[:4]):
        crop = np.dstack([rgb[y0:y1, x0:x1], alpha_full[y0:y1, x0:x1]])
        save(f"tuft_{idx}.png", crop, max_dim=96)
    tones = {"dark": [9, 47, 62], "light": [12, 62, 78]}
    (OUT / "board_tones.json").write_text(json.dumps(tones))
    print(f"  board tufts: {min(4, len(kept))} (found {len(kept)})")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("snake");   sheet("snake_sheet.png", ["snake_head", "snake_body", "snake_curve", "snake_tail"], merge=14)
    print("food");    sheet("food_sheet.png", ["food_normal", "food_golden", "food_speed", "food_shrink"], merge=14, max_dim=192)
    print("powerups"); sheet("powerup_sheet.png", ["pu_ghost", "pu_magnet", "pu_shield", "pu_slowmo",
                                                  "pu_mult", "pu_freeze", "pu_teleport", "pu_revive"],
                          merge=1, rows=2, max_dim=192)
    print("hazards"); sheet("hazard_sheet.png", ["hz_bomb", "hz_curse"], merge=16, max_dim=192)
    def step(label, fn, source):
        print(label)
        if (SRC / source).exists():
            fn()
        else:
            print(f"  (skipped: no {source})")

    step("tongue", prepare_tongue, _tongue_source())
    step("wall", prepare_wall, "wall_tile.png")
    step("title", prepare_title, "title.png")
    step("sidebar", prepare_sidebar, "sidebar_bg.png")
    print("decor")
    if not prepare_decor():
        step("board", prepare_board, "board_bg.png")
    step("menu", lambda: (pygame.image.save(pygame.image.load(str(SRC / "menu_bg.png")), str(OUT / "menu_bg.png")),
                          print("  menu_bg.png")), "menu_bg.png")


if __name__ == "__main__":
    main()
