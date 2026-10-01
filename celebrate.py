"""A quick standalone celebration: v1.8.1 -> v1.8.14 in under an hour.

Run it directly: python celebrate.py
Confetti, a little fanfare, the version run scrolling up like credits.
Press Esc or close the window to quit; it never touches your save file.
"""
from __future__ import annotations

import colorsys
import math
import random
import sys

import pygame

try:
    import numpy as np
    HAVE_AUDIO = True
except ImportError:
    HAVE_AUDIO = False

W, H = 900, 640
BG = (10, 10, 16)
GOLD = (255, 200, 60)

VERSIONS = [
    ("v1.8.2", "easter egg fixes"),
    ("v1.8.3", "mac update SSL crash"),
    ("v1.8.4", "death pause"),
    ("v1.8.5", "trails you can actually see"),
    ("v1.8.6", "the update LOOP"),
    ("v1.8.7", "LAN/Online chat"),
    ("v1.8.8", "font auto-detect"),
    ("v1.8.9", "T = pause + chat, hjkl"),
    ("v1.8.10", "idle disconnects"),
    ("v1.8.11", "version mismatch check"),
    ("v1.8.12", "disconnect-on-high-score"),
    ("v1.8.13", "mac chat font (almost)"),
    ("v1.8.14", "chat ACTUALLY works"),
]


def make_tone(freq, dur, vol=0.3, kind="sine"):
    if not HAVE_AUDIO:
        return None
    sr = 44100
    n = int(sr * dur)
    t = np.linspace(0, dur, n, False)
    if kind == "square":
        wave = np.sign(np.sin(freq * 2 * math.pi * t))
    elif kind == "saw":
        wave = 2 * (t * freq - np.floor(0.5 + t * freq))
    else:
        wave = np.sin(freq * 2 * math.pi * t)
    env = np.minimum(1, np.minimum(t / 0.01, (dur - t) / 0.05 + 0.05))
    wave = (wave * env * vol * 32767).astype(np.int16)
    stereo = np.column_stack([wave, wave])
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


class Confetti:
    __slots__ = ("x", "y", "vx", "vy", "color", "size", "spin", "angle", "life")

    def __init__(self):
        self.reset(burst=False)

    def reset(self, burst=True):
        self.x = random.uniform(0, W)
        self.y = random.uniform(-H, 0) if not burst else H * random.uniform(0.3, 0.9)
        self.vx = random.uniform(-40, 40)
        self.vy = random.uniform(-520, -260) if burst else random.uniform(40, 120)
        hue = random.random()
        r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
        self.color = (int(r * 255), int(g * 255), int(b * 255))
        self.size = random.uniform(4, 8)
        self.spin = random.uniform(-10, 10)
        self.angle = random.uniform(0, 360)
        self.life = 1.0

    def update(self, dt):
        self.vy += 650 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt * 60
        if self.y > H + 20 or self.x < -20 or self.x > W + 20:
            self.reset(burst=False)
            self.y = random.uniform(-40, -5)

    def draw(self, surf):
        s = pygame.Surface((self.size, self.size * 1.6), pygame.SRCALPHA)
        s.fill(self.color)
        rot = pygame.transform.rotate(s, self.angle)
        surf.blit(rot, (self.x - rot.get_width() / 2, self.y - rot.get_height() / 2))


def main():
    pygame.init()
    try:
        pygame.mixer.init()
        audio_ok = HAVE_AUDIO
    except pygame.error:
        audio_ok = False

    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("MEGA SNAKE - SHIPPED IT")
    clock = pygame.time.Clock()

    big = pygame.font.SysFont("consolas,arial", 46, bold=True)
    mid = pygame.font.SysFont("consolas,arial", 24, bold=True)
    small = pygame.font.SysFont("consolas,arial", 17)
    tiny = pygame.font.SysFont("consolas,arial", 13)

    confetti = [Confetti() for _ in range(160)]
    t0 = pygame.time.get_ticks() / 1000.0
    shown = 0
    next_reveal = 0.0

    if audio_ok:
        fanfare = [523, 659, 784, 1046]
        sounds = [make_tone(f, 0.22, 0.22, "square") for f in fanfare]
        pop = make_tone(140, 0.05, 0.15, "saw")
    else:
        sounds, pop = [], None

    played = [False] * 4
    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        t = pygame.time.get_ticks() / 1000.0 - t0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                running = False

        for i, start in enumerate([0.0, 0.18, 0.36, 0.54]):
            if t >= start and not played[i] and sounds:
                sounds[i].play()
                played[i] = True

        if t >= next_reveal and shown < len(VERSIONS):
            shown += 1
            next_reveal = t + 0.22
            if pop:
                pop.play()
            for _ in range(14):
                c = Confetti()
                c.x = W / 2 + random.uniform(-80, 80)
                c.y = 150 + shown * 28
                c.vx = random.uniform(-180, 180)
                c.vy = random.uniform(-260, -60)
                confetti.append(c)

        screen.fill(BG)
        for i in range(0, W, 3):
            hue = ((i / W) + t * 0.05) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.5, 0.07)
            pygame.draw.line(screen, (int(r * 255), int(g * 255), int(b * 255)), (i, 0), (i, H))

        for c in confetti:
            c.update(dt)
            c.draw(screen)
        confetti[:] = confetti[:260]  # cap how many burst-added pieces pile up

        title_hue = (t * 0.1) % 1.0
        tr, tg, tb = colorsys.hsv_to_rgb(title_hue, 0.75, 1.0)
        title = big.render("WE SHIPPED IT", True, (int(tr * 255), int(tg * 255), int(tb * 255)))
        bob = math.sin(t * 3) * 4
        screen.blit(title, (W // 2 - title.get_width() // 2, 30 + bob))

        sub = mid.render("12 versions, under an hour, 0 surviving bugs", True, GOLD)
        screen.blit(sub, (W // 2 - sub.get_width() // 2, 90))

        y = 150
        for i, (ver, desc) in enumerate(VERSIONS[:shown]):
            fade = min(1.0, (t - (0.0 if i < shown - 1 else next_reveal - 0.22)) * 4)
            color = tuple(int(c * fade + BG[j] * (1 - fade)) for j, c in enumerate((230, 230, 240)))
            is_last = i == len(VERSIONS) - 1 and shown == len(VERSIONS)
            line_color = GOLD if is_last else color
            line = small.render(f"{ver}", True, line_color)
            d = tiny.render(f"- {desc}", True, (150, 150, 165))
            screen.blit(line, (W // 2 - 220, y))
            screen.blit(d, (W // 2 - 220 + line.get_width() + 10, y + 2))
            y += 28

        if shown >= len(VERSIONS):
            pulse = 0.6 + 0.4 * math.sin(t * 4)
            foot = mid.render("snake, but with way too many features", True, GOLD)
            a = int(255 * pulse)
            foot.set_alpha(a)
            screen.blit(foot, (W // 2 - foot.get_width() // 2, H - 70))

        hint = tiny.render("Enter / Esc / click close to exit", True, (120, 120, 135))
        screen.blit(hint, (W // 2 - hint.get_width() // 2, H - 24))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
