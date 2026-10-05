"""Generate a starter tongue animation sheet at assets/source/tongue_sheet.png.

Ten equal cells in one row, on flat magenta like the other sheets. Every cell is the SAME size and
the tongue's root is at the LEFT-CENTRE of its cell, so the game can anchor all frames to the mouth.
Frames play in order: poke out, fork opens, wiggle left/right, pull back.

Replace this file with ChatGPT art any time (see assets/ART_PROMPTS.md, "tongue_sheet"), then run
tools/prepare_art.py - no code changes needed.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import pygame

CELLS, CW, CH, SS = 10, 256, 128, 4          # frames, cell size, supersampling
NAVY, RED, LIGHT, MAGENTA = (10, 12, 20), (232, 71, 90), (255, 140, 150), (255, 0, 255)

# (length, fork spread 0-1, curl -1..1) per frame
FRAMES = [(40, 0.0, 0.0), (95, 0.0, 0.0), (145, 0.1, 0.0), (190, 0.3, 0.0), (218, 0.5, 0.0),
          (222, 0.8, 0.5), (222, 0.45, -0.55), (222, 0.8, 0.4), (170, 0.3, 0.0), (80, 0.0, 0.0)]


def draw_frame(length: float, spread: float, curl: float) -> pygame.Surface:
    W, H = CW * SS, CH * SS
    surf = pygame.Surface((W, H))
    surf.fill(MAGENTA)
    cy = H // 2
    width = 40 * SS
    out = 7 * SS                      # outline thickness

    def shaft_points(n=24):
        fork_x = length * 0.72 * SS
        return [(i / n * fork_x, cy + curl * 22 * SS * (i / n) ** 2) for i in range(n + 1)]

    pts = shaft_points()
    fx, fy = pts[-1]
    prongs = []
    plen = length * 0.28 * SS
    for sgn in (-1, 1):
        ang = sgn * (0.10 + 0.55 * spread) + curl * 0.35
        prongs.append((fx + math.cos(ang) * plen, fy + math.sin(ang) * plen))

    def stroke(color, extra):
        w = width + extra
        for a, b in zip(pts, pts[1:]):
            pygame.draw.line(surf, color, a, b, int(w))
        for p in pts:
            pygame.draw.circle(surf, color, p, int(w / 2))
        for tip in prongs:
            pw = int(w * 0.62)
            pygame.draw.line(surf, color, (fx, fy), tip, pw)
            pygame.draw.circle(surf, color, tip, pw // 2)
        pygame.draw.circle(surf, color, (fx, fy), int(w / 2))

    stroke(NAVY, out * 2)
    stroke(RED, 0)
    # highlight stripe along the top of the shaft
    for a, b in zip(pts, pts[1:]):
        pygame.draw.line(surf, LIGHT, (a[0], a[1] - width * 0.22), (b[0], b[1] - width * 0.22), int(width * 0.2))
    return pygame.transform.smoothscale(surf, (CW, CH))


def main() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1))
    sheet = pygame.Surface((CW * CELLS, CH))
    sheet.fill(MAGENTA)
    for i, (length, spread, curl) in enumerate(FRAMES):
        sheet.blit(draw_frame(length, spread, curl), (i * CW, 0))
    out = Path(__file__).resolve().parent.parent / "assets" / "source" / "tongue_sheet.png"
    pygame.image.save(sheet, str(out))
    print(f"wrote {out} ({CW * CELLS}x{CH}, {CELLS} frames)")


if __name__ == "__main__":
    main()
