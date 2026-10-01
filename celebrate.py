
"""A standalone release celebration for Mega Snake.

Run it directly: python celebrate.py
Starts with a cinematic 3-2-1 intro, then rolls into the release credits.
Press Esc, Enter, Space, or close the window to quit; it never touches your save file.
"""
from __future__ import annotations

import colorsys
import math
import random

import pygame

try:
    import numpy as np
    HAVE_AUDIO = True
except ImportError:
    HAVE_AUDIO = False

W, H = 1100, 680
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
        surf.blit(
            rot,
            (self.x - rot.get_width() / 2, self.y - rot.get_height() / 2),
        )


def draw_background(screen, t):
    screen.fill(BG)
    for i in range(0, W, 3):
        hue = ((i / W) + t * 0.05) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.5, 0.07)
        pygame.draw.line(
            screen,
            (int(r * 255), int(g * 255), int(b * 255)),
            (i, 0),
            (i, H),
        )


def draw_centered(screen, font, text, center_y, color, alpha=255):
    surface = font.render(text, True, color)
    surface.set_alpha(max(0, min(255, alpha)))
    screen.blit(
        surface,
        (W // 2 - surface.get_width() // 2, center_y - surface.get_height() // 2),
    )


def play_intro_sound(sounds, index):
    if 0 <= index < len(sounds) and sounds[index]:
        sounds[index].play()



def draw_stats_screen(screen, big, mid, small, tiny, t):
    """Draw the fake post-release developer statistics finale."""
    stats_start = 4.0 + len(VERSIONS) * 0.22 + 1.5
    age = max(0.0, t - stats_start)
    alpha = int(255 * min(1.0, age / 0.5))

    if alpha <= 0:
        return

    # Slightly darken the scene behind the stats.
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, int(75 * alpha / 255)))
    screen.blit(overlay, (0, 0))

    pulse = 0.98 + 0.02 * math.sin(t * 3)
    title_font = pygame.font.SysFont(
        "consolas,arial",
        int(42 * pulse),
        bold=True,
    )
    title = title_font.render("POST-RELEASE STATISTICS", True, GOLD)
    title.set_alpha(alpha)
    screen.blit(
        title,
        (W // 2 - title.get_width() // 2, 48),
    )

    sub = small.render(
        "totally legitimate engineering metrics",
        True,
        (170, 170, 185),
    )
    sub.set_alpha(alpha)
    screen.blit(
        sub,
        (W // 2 - sub.get_width() // 2, 98),
    )

    panel_w, panel_h = 620, 300
    panel_x = (W - panel_w) // 2
    panel_y = 145

    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((8, 8, 14, int(235 * alpha / 255)))
    pygame.draw.rect(
        panel,
        (75, 75, 95, int(220 * alpha / 255)),
        panel.get_rect(),
        2,
    )
    pygame.draw.rect(
        panel,
        (GOLD[0], GOLD[1], GOLD[2], int(100 * alpha / 255)),
        pygame.Rect(8, 8, panel_w - 16, panel_h - 16),
        1,
    )
    screen.blit(panel, (panel_x, panel_y))

    stats = [
        ("Releases deployed", "12"),
        ("Bugs eliminated", "12"),
        ("Time elapsed", "< 1 hour"),
        ("Dead tired", "TRUE"),
        ("Sanity remaining", "3%"),
        ("Chat status", "FINALLY"),
    ]

    left_x = panel_x + 34
    right_x = panel_x + panel_w - 34
    row_y = panel_y + 28

    for label, value in stats:
        label_surface = small.render(label, True, (205, 205, 218))
        value_surface = small.render(
            value,
            True,
            GOLD if value in {"TRUE", "FINALLY", "3%"} else (235, 235, 242),
        )
        label_surface.set_alpha(alpha)
        value_surface.set_alpha(alpha)

        screen.blit(label_surface, (left_x, row_y))
        screen.blit(
            value_surface,
            (right_x - value_surface.get_width(), row_y),
        )
        row_y += 35

    divider_y = panel_y + 238
    pygame.draw.line(
        screen,
        (100, 100, 120, int(160 * alpha / 255)),
        (panel_x + 30, divider_y),
        (panel_x + panel_w - 30, divider_y),
        1,
    )

    caption = tiny.render(
        "statistically exhausted, technically shipped",
        True,
        (150, 150, 165),
    )
    caption.set_alpha(alpha)
    screen.blit(
        caption,
        (W // 2 - caption.get_width() // 2, panel_y + 258),
    )

    # The original tagline gets a final curtain-call treatment.
    foot = mid.render(
        "snake, but with way too many features",
        True,
        GOLD,
    )
    foot.set_alpha(int(alpha * (0.65 + 0.35 * math.sin(t * 4) ** 2)))
    screen.blit(
        foot,
        (W // 2 - foot.get_width() // 2, H - 74),
    )

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
    intro_big = pygame.font.SysFont("consolas,arial", 84, bold=True)
    intro_sub = pygame.font.SysFont("consolas,arial", 28, bold=True)
    mid = pygame.font.SysFont("consolas,arial", 24, bold=True)
    small = pygame.font.SysFont("consolas,arial", 17)
    tiny = pygame.font.SysFont("consolas,arial", 13)

    # ---- Cinematic intro ----
    # 0.0-1.0  : title card
    # 1.0-1.6  : 3...
    # 1.6-2.2  : 2...
    # 2.2-2.8  : 1...
    # 2.8-4.0  : WE SHIPPED IT
    INTRO_DURATION = 4.0

    confetti = [Confetti() for _ in range(160)]
    t0 = pygame.time.get_ticks() / 1000.0

    if audio_ok:
        fanfare = [523, 659, 784, 1046]
        sounds = [make_tone(f, 0.22, 0.22, "square") for f in fanfare]
        pop = make_tone(140, 0.05, 0.15, "saw")
        intro_hit = make_tone(392, 0.16, 0.24, "sine")
        intro_final = make_tone(1046, 0.5, 0.3, "square")
    else:
        sounds, pop, intro_hit, intro_final = [], None, None, None

    intro_played = [False, False, False, False]
    played = [False] * 4
    shown = 0
    next_reveal = INTRO_DURATION
    stats_start = INTRO_DURATION + len(VERSIONS) * 0.22 + 1.5
    running = True

    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        t = pygame.time.get_ticks() / 1000.0 - t0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (
                pygame.K_ESCAPE,
                pygame.K_RETURN,
                pygame.K_SPACE,
            ):
                running = False

        # Cinematic intro sound cues: one soft hit per countdown number,
        # followed by the existing fanfare when "WE SHIPPED IT" lands.
        countdown_starts = [1.0, 1.6, 2.2]
        for i, start in enumerate(countdown_starts):
            if t >= start and not intro_played[i]:
                play_intro_sound([intro_hit], 0)
                intro_played[i] = True

        if t >= 2.8 and not intro_played[3]:
            if intro_final:
                intro_final.play()
            intro_played[3] = True

        # Existing release fanfare starts only after the cinematic intro.
        for i, start in enumerate([INTRO_DURATION, INTRO_DURATION + 0.18,
                                   INTRO_DURATION + 0.36, INTRO_DURATION + 0.54]):
            if t >= start and not played[i] and sounds:
                sounds[i].play()
                played[i] = True

        # Release credits begin after the intro.
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

        draw_background(screen, t)

        # Confetti stays alive behind both the intro and the credits.
        for c in confetti:
            c.update(dt)
            c.draw(screen)
        confetti[:] = confetti[:260]

        if t < INTRO_DURATION:
            # Fade away the title card during the opening second.
            title_alpha = int(255 * min(1.0, t / 0.5))
            if t > 3.3:
                title_alpha = int(255 * max(0.0, 1.0 - (t - 3.3) / 0.7))

            if t < 2.95:
                draw_centered(
                    screen,
                    intro_big,
                    "THE MEGA SNAKE TEAM",
                    210,
                    GOLD,
                    title_alpha,
                )
                draw_centered(
                    screen,
                    intro_sub,
                    "PRESENTS",
                    300,
                    (210, 210, 225),
                    title_alpha,
                )
                draw_centered(
                    screen,
                    intro_sub,
                    "== THE RELEASE SURVIVAL CEREMONY ==",
                    355,
                    (170, 170, 190),
                    int(title_alpha * 0.9),
                )
                draw_centered(
                    screen,
                    intro_sub,
                    "v1.8.x",
                    410,
                    GOLD,
                    title_alpha,
                )

                # Countdown overlays the title card at the last second.
                countdown = None
                if 1.0 <= t < 1.6:
                    countdown = "3..."
                elif 1.6 <= t < 2.2:
                    countdown = "2..."
                elif 2.2 <= t < 2.8:
                    countdown = "1..."

                if countdown:
                    pulse = 0.92 + 0.08 * math.sin(t * 24)
                    count_alpha = int(255 * pulse)
                    draw_centered(
                        screen,
                        intro_big,
                        countdown,
                        520,
                        (245, 245, 250),
                        count_alpha,
                    )
            else:
                # Big final reveal before transitioning to the credits.
                reveal_t = t - 2.8
                scale_pulse = 1.0 + 0.04 * math.sin(reveal_t * 10)
                reveal_alpha = int(255 * min(1.0, reveal_t / 0.15))
                final_font = pygame.font.SysFont(
                    "consolas,arial",
                    int(92 * scale_pulse),
                    bold=True,
                )
                draw_centered(
                    screen,
                    final_font,
                    "WE SHIPPED IT",
                    300,
                    GOLD,
                    reveal_alpha,
                )
                draw_centered(
                    screen,
                    mid,
                    "v1.8.x RELEASE RUN",
                    375,
                    (225, 225, 235),
                    int(reveal_alpha * 0.9),
                )

        else:
            if t >= stats_start and shown >= len(VERSIONS):
                # Feature #5: fake developer statistics finale.
                draw_stats_screen(screen, big, mid, small, tiny, t)
            else:
                # Existing release-credit screen.
                title_hue = (t * 0.1) % 1.0
                tr, tg, tb = colorsys.hsv_to_rgb(title_hue, 0.75, 1.0)
                title = big.render(
                    "WE SHIPPED IT",
                    True,
                    (int(tr * 255), int(tg * 255), int(tb * 255)),
                )
                bob = math.sin(t * 3) * 4
                screen.blit(
                    title,
                    (W // 2 - title.get_width() // 2, 30 + bob),
                )

                sub = mid.render(
                    "12 versions, under an hour, 0 surviving bugs",
                    True,
                    GOLD,
                )
                screen.blit(
                    sub,
                    (W // 2 - sub.get_width() // 2, 90),
                )

                y = 150
                for i, (ver, desc) in enumerate(VERSIONS[:shown]):
                    reveal_start = (
                        INTRO_DURATION
                        if i < shown - 1
                        else next_reveal - 0.22
                    )
                    fade = min(1.0, max(0.0, (t - reveal_start) * 4))
                    color = tuple(
                        int(c * fade + BG[j] * (1 - fade))
                        for j, c in enumerate((230, 230, 240))
                    )
                    is_last = i == len(VERSIONS) - 1 and shown == len(VERSIONS)
                    line_color = GOLD if is_last else color
                    line = small.render(f"{ver}", True, line_color)
                    d = tiny.render(f"- {desc}", True, (150, 150, 165))
                    screen.blit(line, (W // 2 - 220, y))
                    screen.blit(
                        d,
                        (W // 2 - 220 + line.get_width() + 10, y + 2),
                    )
                    y += 28

                if shown >= len(VERSIONS):
                    pulse = 0.6 + 0.4 * math.sin(t * 4)
                    foot = mid.render(
                        "snake, but with way too many features",
                        True,
                        GOLD,
                    )
                    foot.set_alpha(int(255 * pulse))
                    screen.blit(
                        foot,
                        (W // 2 - foot.get_width() // 2, H - 70),
                    )

                hint = tiny.render(
                    "Enter / Esc / click close to exit",
                    True,
                    (120, 120, 135),
                )
                screen.blit(
                    hint,
                    (W // 2 - hint.get_width() // 2, H - 24),
                )

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
