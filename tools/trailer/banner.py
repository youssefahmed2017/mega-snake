# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""YouTube channel banner (2560x1440) in the same look as the thumbnails.

    python tools/trailer/banner.py [out_dir]

Everything that matters sits inside YouTube's 1546x423 "safe on every device"
strip in the middle; the rest of the key art only shows on TVs and wide desktops.
Also writes banner_safe_area_preview.png with that strip outlined, for checking.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1))

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from thumbnail import wordmark, spaced, grade  # noqa: E402  (shared title treatment)

BW, BH = 2560, 1440
SAFE = pygame.Rect((BW - 1546) // 2, (BH - 423) // 2, 1546, 423)


def make(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    key = pygame.image.load(str(ROOT / "assets/art/menu_bg.png")).convert()
    s = max(BW / key.get_width(), BH / key.get_height())
    big = pygame.transform.smoothscale(key, (int(key.get_width() * s), int(key.get_height() * s)))
    img = pygame.Surface((BW, BH))
    img.blit(big, ((BW - big.get_width()) // 2, (BH - big.get_height()) // 2))
    img = grade(img, sat=1.05)

    # a soft dark band behind the text so it reads over the hills
    band = pygame.Surface((BW, SAFE.h + 160), pygame.SRCALPHA)
    for y in range(band.get_height()):
        t = 1 - abs(y / band.get_height() * 2 - 1)
        pygame.draw.line(band, (8, 14, 22, int(120 * t ** 1.5)), (0, y), (BW, y))
    img.blit(band, (0, SAFE.y - 80))

    ly = wordmark(img, BW // 2, SAFE.y + 40, size=150)
    spaced(img, "THE SNAKE GAME THAT GOT WAY OUT OF HAND", 40, (225, 235, 245), (BW // 2, ly + 62), gap=8, alpha=225)
    spaced(img, "Free  ·  Windows  ·  macOS  ·  Linux", 32, (150, 200, 225), (BW // 2, ly + 128), gap=3, alpha=210)
    pygame.image.save(img, str(out / "youtube_banner.png"))

    prev = img.copy()
    pygame.draw.rect(prev, (255, 80, 80), SAFE, 6)
    f = pygame.font.Font(None, 48)
    prev.blit(f.render("safe area: visible on all devices", True, (255, 80, 80)), (SAFE.x, SAFE.bottom + 14))
    pygame.image.save(prev, str(out / "banner_safe_area_preview.png"))


if __name__ == "__main__":
    make(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("thumbnails"))
