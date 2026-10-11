# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Cut a hook-first trailer: cold open -> freeze-frame "yep, that's me" -> rewind ->
title slam -> feature cuts on the beat -> drop montage -> payoff -> end card.

    # from clips recorded with record.py
    python tools/trailer/edit.py clips trailer_clips -o trailer.mp4 [--vertical]

    # from your own OBS recording (finds deaths/combos/power-ups by their sound)
    python tools/trailer/edit.py footage my_run.mp4 -o trailer.mp4 [--vertical]
        [--death 4:31.5] [--moments 0:42,1:10,2:05]

Needs ffmpeg on PATH, pygame-ce and numpy (already game dependencies).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

pygame.init()
import music  # noqa: E402
from music import BEAT, BAR  # noqa: E402
from audio import SR  # noqa: E402

FPS = 60
SRC_W, SRC_H = 1920, 1080
HEAD_FONT = str(ROOT / "assets/fonts/LilitaOne-Regular.ttf")
BODY_FONT = str(ROOT / "assets/fonts/VarelaRound-Regular.ttf")
ACCENT = (90, 200, 255)
GOLD = (255, 210, 80)
GREEN = (110, 230, 140)
WHITE = (250, 250, 250)
# The game's 528px board inside the 1028x578 canvas, in 1080p source pixels.
_K = SRC_W / 1028
BOARD_RECT = pygame.Rect(0, int(25 * _K), int(768 * _K), int(528 * _K))


# ---------------------------------------------------------------- sources

def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as wf:
        n, ch, sr = wf.getnframes(), wf.getnchannels(), wf.getframerate()
        a = np.frombuffer(wf.readframes(n), np.int16).astype(np.float32) / 32767
    a = a.reshape(-1, ch)
    if ch == 1:
        a = np.repeat(a, 2, axis=1)
    if sr != SR:
        idx = np.arange(int(len(a) * SR / sr)) * sr / SR
        a = np.stack([np.interp(idx, np.arange(len(a)), a[:, c]) for c in range(2)], 1).astype(np.float32)
    return a


def write_wav(path: Path, stereo: np.ndarray) -> None:
    data = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(data.tobytes())


class Source:
    def __init__(self, video: Path, wav: Optional[Path] = None, meta: Optional[dict] = None,
                 kind: str = "game") -> None:
        self.video = Path(video)
        self.audio = read_wav(wav) if wav and Path(wav).exists() else np.zeros((SR, 2), np.float32)
        self.meta = meta or {}
        self.kind = kind  # "game" (board on the left) | "ui" (full-frame menus) | "footage"

    def m(self, key: str, default: float = 0.0) -> float:
        return self.meta.get("markers", {}).get(key, default)

    def cue(self, sound: str, default: float = 0.0) -> float:
        """First time a game sound plays in this clip: the recorder's marker if it wrote one,
        else found by ear (footage.find_events on the clip's own audio)."""
        if "snd_" + sound in self.meta.get("markers", {}):
            return self.meta["markers"]["snd_" + sound]
        if not hasattr(self, "_found"):
            import footage
            self._found = footage.find_events(self.audio)
        hits = self._found.get(sound)
        return hits[0] if hits else default


class FrameReader:
    """Decodes a range of source frames (scaled/padded to 1920x1080) with ffmpeg."""

    def __init__(self, src: Source, i0: int, count: int) -> None:
        vf = (f"fps={FPS},scale={SRC_W}:{SRC_H}:force_original_aspect_ratio=decrease,"
              f"pad={SRC_W}:{SRC_H}:(ow-iw)/2:(oh-ih)/2")
        self.p = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-ss", f"{max(0, i0) / FPS:.4f}", "-i", str(src.video),
             "-frames:v", str(max(1, count)), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)  # we hang up early on purpose
        self.pos = max(0, i0) - 1
        self.cur: Optional[bytes] = None

    def get(self, i: int) -> bytes:
        while self.pos < i or self.cur is None:
            b = self.p.stdout.read(SRC_W * SRC_H * 3)
            if len(b) < SRC_W * SRC_H * 3:  # past the end: hold the last frame
                if self.cur is None:
                    self.cur = bytes(SRC_W * SRC_H * 3)
                self.pos = i
                break
            self.cur, self.pos = b, self.pos + 1
        return self.cur

    def close(self) -> None:
        self.p.stdout.close()
        self.p.kill()
        self.p.wait()


# ---------------------------------------------------------------- timeline model

@dataclass
class Cap:
    text: str
    style: str = "big"          # big | hook | hooksub | stat | tag | sub | small
    t0: float = 0.0
    t1: Optional[float] = None
    color: Tuple[int, int, int] = WHITE
    pop: bool = True            # False: no pop-in (a caption carried over from the previous shot)


@dataclass
class Shot:
    src: Optional[Source]
    t: float                   # source start time (seconds)
    dur: float                 # output duration (seconds)
    speed: float = 1.0
    reverse: bool = False
    freeze: bool = False
    caps: List[Cap] = field(default_factory=list)
    zoom: Tuple[float, float] = (1.0, 1.0)
    punch: float = 0.0         # zoom kick at the cut that settles back
    flash: float = 0.0         # white flash length at the cut
    shake: float = 0.0
    fx: Optional[str] = None   # vhs | freeze | dim | blur
    audio_gain: float = 1.0
    overlay: Optional[Callable] = None  # overlay(surface, local_t, layout)


@dataclass
class Edit:
    shots: List[Shot]
    sfx: List[Tuple[float, np.ndarray, float]] = field(default_factory=list)
    music: List[Tuple[float, np.ndarray, float]] = field(default_factory=list)


# ---------------------------------------------------------------- drawing helpers

_font_cache: Dict[tuple, pygame.font.Font] = {}
_text_cache: Dict[tuple, pygame.Surface] = {}


def font(path: str, size: int) -> pygame.font.Font:
    k = (path, size)
    if k not in _font_cache:
        _font_cache[k] = pygame.font.Font(path, size)
    return _font_cache[k]


def outlined(text: str, path: str, size: int, color, stroke: int, shadow: int = 0) -> pygame.Surface:
    k = (text, path, size, color, stroke, shadow)
    if k in _text_cache:
        return _text_cache[k]
    f = font(path, size)
    fg = f.render(text, True, color)
    bk = f.render(text, True, (8, 10, 16))
    w, h = fg.get_width() + stroke * 2 + shadow, fg.get_height() + stroke * 2 + shadow
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    if shadow:
        sh = f.render(text, True, (0, 0, 0))
        sh.set_alpha(150)
        for a in range(0, 360, 30):
            s.blit(sh, (stroke + shadow + round(math.cos(math.radians(a)) * stroke),
                        stroke + shadow + round(math.sin(math.radians(a)) * stroke)))
    for a in range(0, 360, 20):
        s.blit(bk, (stroke + round(math.cos(math.radians(a)) * stroke), stroke + round(math.sin(math.radians(a)) * stroke)))
    s.blit(fg, (stroke, stroke))
    _text_cache[k] = s
    return s


def wrap(text: str, f: pygame.font.Font, max_w: int) -> List[str]:
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if f.size(trial)[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


STYLES = {  # font, size (at 1080 tall/wide reference), stroke, y (0..1), color override
    "big": (HEAD_FONT, 104, 9, 0.17),
    "hook": (HEAD_FONT, 92, 8, 0.70),
    "hooksub": (BODY_FONT, 50, 6, 0.83),
    "stat": (HEAD_FONT, 190, 12, 0.46),
    "tag": (HEAD_FONT, 84, 8, 0.84),
    "sub": (BODY_FONT, 52, 6, 0.88),
    "small": (BODY_FONT, 40, 5, 0.93),
    "chapter": (HEAD_FONT, 44, 5, 0.055),
}


class Layout:
    def __init__(self, vertical: bool) -> None:
        self.vertical = vertical
        self.W, self.H = (1080, 1920) if vertical else (1920, 1080)
        self.bg_cache = None

    def scale_style(self, style: str) -> Tuple[str, int, int, float]:
        path, size, stroke, y = STYLES[style]
        if self.vertical:
            size = int(size * (0.86 if style != "stat" else 0.9))
            y = {"big": 0.16, "hook": 0.73, "hooksub": 0.82, "stat": 0.5, "tag": 0.80, "sub": 0.86,
                 "small": 0.93, "chapter": 0.075}[style]
        return path, size, stroke, y


def draw_caps(out: pygame.Surface, shot: Shot, tl: float, L: Layout) -> None:
    for c in shot.caps:
        t1 = shot.dur if c.t1 is None else c.t1
        if not (c.t0 <= tl < t1):
            continue
        age = tl - c.t0
        path, size, stroke, y = L.scale_style(c.style)
        f = font(path, size)
        lines = wrap(c.text, f, int(L.W * 0.88))
        surfs = [outlined(ln, path, size, c.color, stroke, shadow=6) for ln in lines]
        widest = max(x.get_width() for x in surfs)
        if widest > L.W * 0.94:  # a single word too wide for the frame (vertical): shrink to fit
            k = L.W * 0.94 / widest
            surfs = [pygame.transform.smoothscale_by(x, k) for x in surfs]
        # pop in: overshoot then settle; fade the last 0.12 s
        still = c.style in ("hook", "hooksub", "sub", "small", "chapter") or not c.pop
        pop = 1.0 if still else 1.0 + 0.35 * math.exp(-age * 18) * math.cos(age * 30)
        alpha = (min(1.0, age / 0.08) if c.pop else 1.0) * min(1.0, (t1 - tl) / 0.1)
        total_h = sum(s.get_height() for s in surfs) * 0.92
        cy = y * L.H - total_h / 2
        for s in surfs:
            if pop != 1.0:
                s = pygame.transform.smoothscale_by(s, max(0.2, pop))
            if alpha < 1:
                s = s.copy()
                s.set_alpha(int(255 * alpha))
            out.blit(s, (L.W // 2 - s.get_width() // 2, int(cy)))
            cy += s.get_height() * 0.92


_scan = None


def vhs(surf: pygame.Surface, tl: float, rng: random.Random) -> pygame.Surface:
    global _scan
    w, h = surf.get_size()
    out = pygame.Surface((w, h))
    out.fill((0, 0, 0))
    band = 24
    for y in range(0, h, band):
        dx = int(rng.gauss(0, 10)) if rng.random() < 0.7 else int(rng.gauss(0, 60))
        out.blit(surf, (dx, y), pygame.Rect(0, y, w, band))
    tint = pygame.Surface((w, h))
    tint.fill((40, 0, 90))
    out.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    if _scan is None or _scan.get_size() != (w, h):
        _scan = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 4):
            pygame.draw.line(_scan, (0, 0, 0, 90), (0, y), (w, y), 2)
    out.blit(_scan, (0, 0))
    # tracking-noise bar rolling up the screen
    by = int((1 - (tl * 1.7) % 1) * h)
    noise = pygame.Surface((w, 30))
    noise.fill((200, 200, 220))
    noise.set_alpha(60)
    out.blit(noise, (0, by))
    # VCR "<< REWIND" readout
    f = font(BODY_FONT, max(28, h // 22))
    x0, y0 = int(w * 0.05), int(h * 0.06)
    s = f.get_height() * 0.45
    for k in range(2):
        cx = x0 + k * s * 1.1
        pygame.draw.polygon(out, WHITE, [(cx + s, y0), (cx + s, y0 + 2 * s), (cx, y0 + s)])
    out.blit(f.render("REWIND", True, WHITE), (x0 + s * 2.6, y0 + s - f.get_height() / 2))
    return out


def blur(surf: pygame.Surface, size: Tuple[int, int], k: int = 40) -> pygame.Surface:
    small = pygame.transform.smoothscale(surf, (max(1, size[0] // k), max(1, size[1] // k)))
    small = pygame.transform.smoothscale(small, (max(1, size[0] // 8), max(1, size[1] // 8)))
    return pygame.transform.smoothscale(small, size)


# ---------------------------------------------------------------- render

def compose(frame: pygame.Surface, shot: Shot, tl: float, L: Layout, rng: random.Random) -> pygame.Surface:
    W, H = L.W, L.H
    p = tl / shot.dur if shot.dur else 0
    z = shot.zoom[0] + (shot.zoom[1] - shot.zoom[0]) * p
    z *= 1 + shot.punch * math.exp(-tl * 9)
    if shot.fx == "freeze":
        g = pygame.transform.grayscale(frame)
        g.set_alpha(170)
        frame = frame.copy()
        frame.blit(g, (0, 0))
    out = pygame.Surface((W, H))
    if L.vertical:
        src_rect = BOARD_RECT if (shot.src is not None and shot.src.kind == "game") else frame.get_rect()
        bg = blur(frame.subsurface(src_rect), (W, H), 30)
        bg.fill((90, 90, 100), special_flags=pygame.BLEND_RGB_MULT)
        out.blit(bg, (0, 0))
        fw = W
        fh = int(src_rect.h * fw / src_rect.w)
        cw, ch = src_rect.w / z, src_rect.h / z
        crop = pygame.Rect(0, 0, int(cw), int(ch))
        crop.center = src_rect.center
        fg = pygame.transform.smoothscale(frame.subsurface(crop.clamp(src_rect)), (fw, fh))
        out.blit(fg, (0, int(H * 0.5 - fh / 2 + H * 0.02)))
    else:
        if abs(z - 1) > 1e-3:
            crop = pygame.Rect(0, 0, int(W / z), int(H / z))
            focus = BOARD_RECT.center if (shot.src is not None and shot.src.kind == "game" and z > 1.04) else (W // 2, H // 2)
            crop.center = focus
            crop.clamp_ip(frame.get_rect())
            out.blit(pygame.transform.smoothscale(frame.subsurface(crop), (W, H)), (0, 0))
        else:
            out.blit(frame, (0, 0))
    if shot.fx == "vhs":
        out = vhs(out, tl, rng)
    elif shot.fx == "dim":
        out.fill((70, 70, 80), special_flags=pygame.BLEND_RGB_MULT)
    elif shot.fx == "blur":
        out = blur(out, (W, H), 25)
        out.fill((80, 80, 95), special_flags=pygame.BLEND_RGB_MULT)
    if shot.fx == "freeze":
        vig = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(10):
            pygame.draw.rect(vig, (0, 0, 0, 22), vig.get_rect().inflate(-i * W // 30, -i * H // 30), W // 60)
        out.blit(vig, (0, 0))
    if shot.shake:
        a = shot.shake * math.exp(-tl * 6)
        if a > 0.5:
            out.scroll(int(rng.uniform(-a, a)), int(rng.uniform(-a, a)))
    if shot.overlay:
        shot.overlay(out, tl, L)
    draw_caps(out, shot, tl, L)
    if shot.flash and tl < shot.flash:
        fl = pygame.Surface((W, H))
        fl.fill(WHITE)
        fl.set_alpha(int(255 * (1 - tl / shot.flash) ** 1.6))
        out.blit(fl, (0, 0))
    return out


def src_time(shot: Shot, tl: float) -> float:
    if shot.freeze:
        return shot.t
    return shot.t - tl * shot.speed if shot.reverse else shot.t + tl * shot.speed


def render(edit: Edit, out_path: Path, vertical: bool, preview: bool = False) -> None:
    L = Layout(vertical)
    rng = random.Random(1)
    out_path = Path(out_path)
    tmp_video = out_path.with_suffix(".video.mp4")
    tmp_audio = out_path.with_suffix(".wav")
    # quantize to whole frames so audio and video can't drift apart
    starts, t = [], 0.0
    for s in edit.shots:
        starts.append(round(t * FPS))
        t += s.dur
    total_frames = round(t * FPS)
    ends = starts[1:] + [total_frames]

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L.W}x{L.H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "ultrafast" if preview else "medium",
         "-crf", "28" if preview else "17", "-pix_fmt", "yuv420p", str(tmp_video)], stdin=subprocess.PIPE)
    black = pygame.Surface((SRC_W, SRC_H))
    black.fill((6, 8, 12))
    for si, shot in enumerate(edit.shots):
        n = ends[si] - starts[si]
        idxs = [int(round(src_time(shot, f / FPS) * FPS)) for f in range(n)]
        reader = cache = None
        if shot.src is not None:
            if shot.reverse:
                need = set(idxs)
                lo = min(need)
                reader = FrameReader(shot.src, lo, max(need) - lo + 1)
                cache = {}
                for i in sorted(need):
                    cache[i] = reader.get(i)
                reader.close()
                reader = None
            else:
                reader = FrameReader(shot.src, idxs[0], idxs[-1] - idxs[0] + 2)
        for f in range(n):
            tl = f / FPS
            if shot.src is None:
                frame = black
            else:
                b = cache[idxs[f]] if cache is not None else reader.get(idxs[f])
                frame = pygame.image.frombuffer(b, (SRC_W, SRC_H), "RGB")
            img = compose(frame, shot, tl, L, rng)
            ff.stdin.write(pygame.image.tobytes(img, "RGB"))
        if reader:
            reader.close()
        print(f"  shot {si + 1}/{len(edit.shots)}  {starts[si] / FPS:6.2f}s  {shot.caps[0].text if shot.caps else ''}",
              flush=True)
    ff.stdin.close()
    ff.wait()

    # ---- audio
    mix = np.zeros((int(total_frames / FPS * SR) + SR * 4, 2), np.float32)
    game = np.zeros_like(mix)
    for si, shot in enumerate(edit.shots):
        if shot.src is None or shot.freeze or shot.audio_gain <= 0:
            continue
        a0 = int(starts[si] / FPS * SR)
        n = int((ends[si] - starts[si]) / FPS * SR)
        pos = (np.array([src_time(shot, i / SR) for i in (0, n)]) * SR)
        sidx = np.linspace(pos[0], pos[1], n).astype(np.int64)
        sidx = np.clip(sidx, 0, len(shot.src.audio) - 1)
        seg = shot.src.audio[sidx] * shot.audio_gain
        fade = min(240, n // 2)
        if fade:
            seg[:fade] *= np.linspace(0, 1, fade)[:, None]
            seg[-fade:] *= np.linspace(1, 0, fade)[:, None]
        game[a0:a0 + n] += seg
    for t0, sig, gain in edit.music:
        music._place(mix, sig * 0.62, t0, gain)
    for t0, sig, gain in edit.sfx:
        music._place(mix, sig, t0, gain)
    mix += game * 0.95
    mix = mix[: int(total_frames / FPS * SR)]
    mix[-int(SR * 0.4):] *= np.linspace(1, 0, int(SR * 0.4))[:, None]
    write_wav(tmp_audio, music.master(mix))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp_video), "-i", str(tmp_audio), "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "224k", "-movflags", "+faststart", "-shortest", str(out_path)], check=True)
    tmp_video.unlink()
    tmp_audio.unlink()
    print(f"wrote {out_path}  ({total_frames / FPS:.1f}s, {'1080x1920' if vertical else '1920x1080'})")


# ---------------------------------------------------------------- overlays

def logo_overlay(sub: str = "", lines: Tuple[str, ...] = (), slam_at: float = 0.0):
    def draw(out: pygame.Surface, tl: float, L: Layout) -> None:
        W, H = L.W, L.H
        age = tl - slam_at
        if age < 0:
            return
        size = int((210 if not L.vertical else 150))
        k = 1 + 0.6 * math.exp(-age * 14)
        y = H * (0.36 if not L.vertical else 0.38)
        for word, col, dy in (("MEGA", WHITE, -0.55), ("SNAKE", GREEN, 0.45)):
            s = outlined(word, HEAD_FONT, size, col, 12, shadow=10)
            if k != 1:
                s = pygame.transform.smoothscale_by(s, k)
            out.blit(s, (W // 2 - s.get_width() // 2, int(y + dy * size * k - s.get_height() / 2)))
        cy = y + size * 1.25
        if sub and age > 0.25:
            s = outlined(sub, BODY_FONT, 54 if not L.vertical else 44, ACCENT, 6)
            s = s.copy()
            s.set_alpha(int(255 * min(1, (age - 0.25) / 0.2)))
            out.blit(s, (W // 2 - s.get_width() // 2, int(cy)))
            cy += s.get_height() + 30
        for i, ln in enumerate(lines):
            if age > 0.6 + i * 0.25:
                s = outlined(ln, BODY_FONT, 44 if not L.vertical else 36, WHITE if i else GOLD, 5)
                out.blit(s, (W // 2 - s.get_width() // 2, int(cy)))
                cy += s.get_height() + 8
    return draw


def beats(n: float) -> float:
    return n * BEAT


# ---------------------------------------------------------------- the clips trailer

def clips_trailer(d: Path) -> Edit:
    """The full ~2 minute trailer: a chaos cold open, then every feature, act by act,
    each act cut to its own section of the music."""
    from constants import MODE_DESC
    from events import EVENTS, HAZARDS

    cache: Dict[str, Source] = {}

    def S(name: str) -> Source:
        if name not in cache:
            meta = json.loads((d / f"{name}.json").read_text())
            ui = name.startswith(("menu", "lan_menu", "achievements", "shop", "quests", "stats", "leaderboard",
                                  "settings", "howto", "changelog", "update", "easter"))
            cache[name] = Source(d / f"{name}.mp4", d / f"{name}.wav", meta, "ui" if ui else "game")
        return cache[name]

    shots: List[Shot] = []
    sfx: List[Tuple[float, np.ndarray, float]] = []
    mus: List[Tuple[float, np.ndarray, float]] = []
    T = [0.0]

    def add(s: Shot) -> Shot:
        shots.append(s)
        T[0] += s.dur
        return s

    def act(chapter: str, items, punch: float = 0.06, flash: float = 0.1):
        """items: (clip, source time, length in bars, caption, subcaption)"""
        for i, (name, t0, bars, cap, sub) in enumerate(items):
            src = S(name)
            caps = [Cap(chapter, "chapter", color=ACCENT, pop=i == 0)]
            if cap:
                caps.append(Cap(cap, "big"))
            if sub:
                caps.append(Cap(sub, "sub", 0.15))
            add(Shot(src, max(0.0, t0), bars * BAR, punch=punch, flash=flash if i == 0 else flash * 0.6, caps=caps,
                     audio_gain=0.8))

    def es(name: str) -> float:
        return S(name).m("event_start", 1.0)

    # ---- 1. COLD OPEN: pure chaos on a drop, no context
    sfx.append((0.0, music.impact(), 1.0))
    pov = "POV: you just wanted to play Snake"
    hook = [("chaos_max", 1.2, 2), ("chaos_battle", 1.6, 2), ("chaos_dark", 1.4, 2), ("hz_shower", 1.4, 1),
            ("chaos_max", 3.0, 1), ("ev_hunter", es("ev_hunter") + 1.5, 1), ("chaos_battle", 3.4, 1),
            ("hz_rockfall", 0.8, 1), ("ev_quake", es("ev_quake") + 0.2, 1), ("chaos_dark", 3.4, 1),
            ("chaos_max", 3.5, 0.5), ("ev_mirror", es("ev_mirror") + 0.3, 0.5), ("chaos_battle", 4.2, 0.5),
            ("hz_surge", 1.5, 0.5), ("ev_blackout", es("ev_blackout") + 1.0, 0.5), ("chaos_max", 2.5, 0.5)]
    for i, (name, t0, b) in enumerate(hook):
        add(Shot(S(name), t0, b * BEAT, punch=0.09, shake=14 if i == 0 else 0, flash=0.15 if i == 0 else 0,
                 audio_gain=0.7, caps=[Cap(pov, "big", pop=i == 0)]))
    mus.append((0.0, music.song([("drop", 4, False)]), 1.0))

    # ---- 2. HARD STOP: it started as just snake
    sfx.append((T[0], music.record_scratch(), 1.0))
    add(Shot(S("calm_snake"), 0.6, 3.0, audio_gain=1.0, caps=[Cap("it started as just snake.", "hook", 0.35)]))
    sfx.append((T[0], music.riser(1.5), 0.9))
    add(Shot(None, 0, 1.5, caps=[Cap("then I kept adding stuff.", "hook", 0.1)]))

    # ---- 3. TITLE
    title_t = T[0]
    sfx.append((title_t, music.impact(), 1.0))
    add(Shot(S("menu"), 0.4, BAR * 2, flash=0.5, shake=18, zoom=(1.0, 1.05), fx="dim", audio_gain=0.5,
             overlay=logo_overlay("the snake game that got WAY out of hand")))

    # ---- 4. THE BASICS (verse, 9 bars)
    act("THE BASICS", [
        ("food_types", S("food_types").cue("golden", 0.6) - 0.5, 1, "GOLDEN, SPEED + SHRINK FOOD", None),
        ("combo", 1.2, 1, "CHAIN COMBOS", "every bite climbs the scale"),
        ("near_miss", max(0.0, S("near_miss").cue("near_miss", 1.2) - 0.7), 1, "NEAR MISSES SLOW TIME", None),
        ("portals", max(0.0, S("portals").cue("portal", 1.5) - 1.0), 1, "PORTALS", None),
        ("pu_ghost", S("pu_ghost").cue("powerup", 0.6) - 0.2, 0.5, "GHOST", None),
        ("pu_magnet", S("pu_magnet").cue("powerup", 0.6) - 0.1, 0.5, "MAGNET", None),
        ("pu_slowmo", S("pu_slowmo").cue("powerup", 0.6) - 0.1, 0.5, "SLOW-MO", None),
        ("pu_mult2x", S("pu_mult2x").cue("powerup", 0.6) - 0.1, 0.5, "2X SCORE", None),
        ("pu_freeze", S("pu_freeze").cue("freeze", 0.6) - 0.2, 0.5, "FREEZE", "rivals stop dead"),
        ("pu_teleport", S("pu_teleport").cue("teleport", 0.6) - 0.3, 0.5, "TELEPORT", None),
        ("pu_shield", 1.0, 1, "SHIELD = CLUTCH SAVE", None),
        ("bomb_defused", 0.4, 0.5, "BOMBS", None),
        ("curse", max(0.0, S("curse").cue("curse", 0.8) - 0.3), 0.5, "CURSES", "controls flipped"),
    ])
    # ---- 5. NINE MODES (build, 9 bars, riser)
    modes = ["Classic", "Walls", "Maze", "Battle", "Timed", "Hardcore", "Coop", "Daily", "Roguelite"]
    act("9 MODES", [(f"mode_{m.lower()}", 0.5, 1, ("CO-OP" if m == "Coop" else m.upper()), MODE_DESC[m])
                    for m in modes])
    # ---- 6. CHAOS (drop, 9 bars)
    sfx.append((T[0], music.impact(), 0.8))
    act("CHAOS EVENTS", [(f"ev_{e}", es(f"ev_{e}") - 0.25, 1, EVENTS[e].name, EVENTS[e].desc)
                         for e in ("frenzy", "gold_rush", "blackout", "mirror", "hunter", "quake")], punch=0.08)
    act("HARDCORE HAZARDS", [(f"hz_{h}", 0.15, 1 if h == "shower" else 0.5, HAZARDS[h].name, HAZARDS[h].desc)
                             for h in ("shower", "meteor", "tremor", "surge", "rockfall")], punch=0.08)
    # ---- 7. ROGUELITE + MAPS (break, 5 bars, riser)
    act("ROGUELITE", [("perk_pick", S("perk_pick").m("perk", 1.5) - 0.3, 1.5, "PICK A PERK EVERY 8 FOODS", None),
                      ("perk_dash", 0.7, 0.75, "PHASE DASH", None),
                      ("perk_second_wind", 1.0, 0.75, "SECOND WIND", "survive one fatal crash")])
    act("8 MAPS", [(f"map_{m}", 0.8, 0.25, None, None) for m in
                   ("open", "pillars", "cross", "arena", "volcano", "everest", "desert", "glacier")],
        punch=0.05, flash=0.0)
    for i, m in enumerate(("OPEN", "PILLARS", "CROSS", "ARENA", "VOLCANO", "EVEREST", "DESERT", "GLACIER")):
        shots[-8 + i].caps.append(Cap(m, "tag", color=GOLD))
    # ---- 8. MULTIPLAYER (verse, 6 bars)
    ls = S("lan_4p").m("lan_start", 3.6)
    act("MULTIPLAYER", [("lan_menu", 0.4, 1, "LAN OR ONLINE", None),
                        ("lan_4p", 1.0, 1, "HOST A ROOM, FRIENDS JOIN", None),
                        ("lan_4p", ls + 1.2, 2, "UP TO 4 PLAYERS", None),
                        ("revive", 1.0, 1, "REVIVE YOUR TEAMMATE", None),
                        ("mode_coop", 2.0, 1, "OR CO-OP ON ONE KEYBOARD", None)])
    # ---- 9. PROGRESSION (build, 6 bars)
    ini = S("initials").m("death", 1.5)
    act("UNLOCK EVERYTHING", [("achievements", 0.3, 1, "45 ACHIEVEMENTS", None),
                              ("menu_skins", 0.4, 1, "SKINS", None),
                              ("shop", 0.4, 0.5, "SHOP", None),
                              ("trail_rainbow", 1.0, 0.5, "TRAILS", None),
                              ("quests", 0.3, 0.5, "DAILY QUESTS", None),
                              ("stats", 0.3, 0.5, "STATS", None),
                              ("initials", ini + 1.6, 0.5, "LEADERBOARDS", None),
                              ("leaderboard", 0.3, 0.5, "LEADERBOARDS", None),
                              ("ghost_replay", 1.5, 1, "RACE YOUR BEST RUN'S GHOST", None)])
    # ---- 10. POLISH (verse, 4 bars)
    act("THE DETAILS", [("settings_display", 0.4, 0.5, "UP TO 4K", None),
                        ("colorblind", 0.8, 0.5, "COLOR-BLIND MODE", None),
                        ("settings_controller", 0.4, 0.5, "CONTROLLER SUPPORT", None),
                        ("controller_play", 1.0, 0.5, "PLAY ON A GAMEPAD", None),
                        ("howto", 0.4, 0.5, "BUILT-IN GUIDE", None),
                        ("update_check", 0.3, 0.5, "AUTO-UPDATES", None),
                        ("easter_egg", 0.3, 1, None, "...and a secret we're not telling you about")])
    # ---- 11. RECAP (build, 2 bars, riser)
    for src, t0, cap in (("ev_gold_rush", 4.0, "9 MODES"), ("map_volcano", 1.0, "6 CHAOS EVENTS"),
                         ("perk_pick", 4.0, "8 PERKS"), ("lan_4p", ls + 4.0, "4 PLAYERS")):
        add(Shot(S(src), t0, BEAT * 2, punch=0.08, fx="dim", audio_gain=0.4, caps=[Cap(cap, "stat", color=GOLD)]))
    # ---- 12. FINALE (drop, 6 bars) - ends on the crash
    sfx.append((T[0], music.impact(), 0.8))
    one = [("chaos_max", 2.0), ("lan_4p", ls + 3.0), ("ev_gold_rush", es("ev_gold_rush") + 0.6), ("hz_shower", 2.2),
           ("mode_battle", 2.0), ("combo", 2.4), ("perk_dash", 0.9), ("ev_hunter", es("ev_hunter") + 2.0),
           ("trail_rainbow", 2.5), ("portals", max(0.0, S("portals").cue("portal", 1.5) - 0.3)),
           ("ev_quake", es("ev_quake") + 0.4), ("chaos_battle", 2.6)]
    half = [("chaos_dark", 2.6), ("pu_freeze", 1.2), ("ev_frenzy", es("ev_frenzy") + 1.0), ("mode_maze", 2.0),
            ("chaos_max", 3.3), ("revive", 1.8), ("map_volcano", 1.6), ("ev_blackout", es("ev_blackout") + 1.5),
            ("pu_ghost", 1.4), ("hz_rockfall", 0.6), ("chaos_battle", 4.0), ("mode_timed", 2.0)]
    for name, t0 in one:
        add(Shot(S(name), t0, BEAT, punch=0.09, audio_gain=0.7))
    for name, t0 in half:
        add(Shot(S(name), t0, BEAT / 2, punch=0.12, audio_gain=0.7))
    cd = S("chaos_death")
    dt = cd.m("death", 6.0)
    add(Shot(cd, dt - BAR * 1.5, BAR * 1.5, zoom=(1.0, 1.12), audio_gain=0.8))
    # ---- 13. PAYOFF: the music cuts out on the crash
    add(Shot(cd, dt, 4.6, audio_gain=1.0, caps=[Cap("GG.", "hook", 0.9), Cap("it's not just snake anymore.", "hooksub", 1.6)]))
    # ---- 14. END CARD
    end_t = T[0]
    add(Shot(S("menu"), 1.0, BAR * 3 + 0.8, fx="blur", audio_gain=0, flash=0.3,
             overlay=logo_overlay("FREE  ·  Windows  ·  macOS  ·  Linux",
                                  ("github.com/youssefahmed2017/mega-snake",
                                   "9 modes · 8 maps · chaos events · online co-op"))))

    mus.append((title_t, music.song([("intro", 2), ("verse", 9, False), ("build", 9, True), ("drop", 9, False),
                                     ("break", 5, True), ("verse", 6, False), ("build", 6, False),
                                     ("verse", 4, False), ("build", 2, True), ("drop", 6, False)]), 1.0))
    mus.append((end_t, music.song([("end", 3)]), 1.0))
    print(f"timeline: {T[0]:.1f}s, {len(shots)} shots")
    return Edit(shots, sfx, mus)


# ---------------------------------------------------------------- your own footage

def parse_time(s: str) -> float:
    parts = [float(p) for p in s.split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def footage_trailer(path: Path, death: Optional[float], moments: List[float], work: Path) -> Edit:
    import footage  # sound-based highlight finder
    wav = work / (path.stem + ".audio.wav")
    if not wav.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(SR),
                        str(wav)], check=True)
    src = Source(path, wav, kind="footage")
    length = len(src.audio) / SR
    found = footage.find_events(src.audio)
    print("detected:", {k: len(v) for k, v in found.items()})
    deaths = found.get("death", [])
    if death is None:
        death = deaths[-1] if deaths else max(0.0, length - 3.0)
    highlights = moments or footage.best_moments(found, length, count=12, avoid=death)
    print(f"death at {death:.1f}s, highlights: {', '.join(f'{h:.1f}' for h in highlights)}")
    labels = footage.label_moments(found, highlights)

    shots: List[Shot] = []
    sfx: List[Tuple[float, np.ndarray, float]] = []
    mus: List[Tuple[float, np.ndarray, float]] = []
    T = [0.0]

    def add(s: Shot) -> None:
        shots.append(s)
        T[0] += s.dur

    sfx.append((0.0, music.drone(6.4), 0.9))
    add(Shot(src, max(0, death - 2.9), 2.6, zoom=(1.0, 1.1), caps=[Cap("this run was going GREAT", "hooksub", 0.3, 2.4)]))
    sfx.append((T[0], music.record_scratch(), 1.0))
    add(Shot(src, max(0, death - 0.3), 2.8, freeze=True, fx="freeze", zoom=(1.1, 1.22),
             caps=[Cap("*record scratch*", "small", 0.0, 0.8), Cap("yep. that's me.", "hook", 0.25),
                   Cap("you're probably wondering how I got here.", "hooksub", 1.0)]))
    sfx.append((T[0], music.rewind(1.25), 1.0))
    add(Shot(src, max(1.0, death - 0.3), 1.25, speed=min(20.0, max(4.0, death / 1.25 / 6)), reverse=True, fx="vhs",
             audio_gain=0))
    title_t = T[0]
    sfx.append((title_t, music.impact(), 1.0))
    add(Shot(src, min(2.0, length / 4), BAR * 2, flash=0.5, shake=18, fx="blur", audio_gain=0,
             overlay=logo_overlay("the snake game that got WAY out of hand")))
    feat = highlights[:8]
    for h, lab in zip(feat, labels[:8]):
        add(Shot(src, max(0, h - 0.5), BAR, punch=0.06, flash=0.1, caps=[Cap(lab, "big")] if lab else []))
    while len(feat) < 8:  # very short footage: pad with evenly spaced moments
        add(Shot(src, length * len(feat) / 9, BAR, punch=0.06, flash=0.1))
        feat.append(0)
    sfx.append((T[0], music.impact(), 0.8))
    rest = highlights[8:] or highlights
    k = 0
    for bar in range(8):
        n = 2 if bar < 6 else 4
        for _ in range(n):
            h = rest[k % len(rest)] + (k // len(rest)) * 0.9
            add(Shot(src, max(0, h - 0.3), BAR / n, punch=0.08))
            k += 1
    sfx.append((T[0], music.whoosh(0.5, up=False), 0.8))
    add(Shot(src, max(0, death - 2.4), min(7.0, length - max(0, death - 2.4)),
             caps=[Cap("so anyway...", "hooksub", 0.2, 2.2), Cap("...that's how I got here.", "hook", 2.6, 5.4)]))
    end_t = T[0]
    add(Shot(src, min(2.0, length / 4), BAR * 2 + 0.8, fx="blur", audio_gain=0, flash=0.3,
             overlay=logo_overlay("FREE  ·  Windows  ·  macOS  ·  Linux",
                                  ("github.com/youssefahmed2017/mega-snake",))))
    mus.append((title_t, music.song([("intro", 2), ("build", 8), ("drop", 8)]), 1.0))
    mus.append((end_t, music.song([("end", 3)]), 1.0))
    return Edit(shots, sfx, mus)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["clips", "footage"])
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("trailer.mp4"))
    ap.add_argument("--vertical", action="store_true", help="1080x1920 for Shorts/TikTok/Reels")
    ap.add_argument("--preview", action="store_true", help="fast, low-quality encode")
    ap.add_argument("--death", type=parse_time, help="(footage) time of the death to use as the hook")
    ap.add_argument("--moments", type=lambda s: [parse_time(x) for x in s.split(",")], default=[],
                    help="(footage) comma-separated highlight times, e.g. 0:42,1:10")
    a = ap.parse_args()
    if a.mode == "clips":
        ed = clips_trailer(a.input)
    else:
        work = a.output.resolve().parent
        ed = footage_trailer(a.input, a.death, a.moments, work)
    render(ed, a.output, a.vertical, a.preview)
