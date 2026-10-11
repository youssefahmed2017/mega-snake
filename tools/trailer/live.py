# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Join a real online room with bot players and film what the first bot sees.

    python tools/trailer/live.py ROOMCODE [out.mp4] [--bots 3] [--minutes 12]

Bot 1 runs a full game client (a normal guest, rendered at 720p, filmed at 30 fps
in real time); bots 2-3 are bare connections that steer from the same snapshots.
All of them only send inputs - the host's game stays the only simulation.
Touch STOP next to the output file to end early.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["HOME"] = tempfile.mkdtemp(prefix="megasnake-live-")
# boot straight into 720p windowed (cheap enough to film in real time)
_save = Path(os.environ["HOME"]) / ".megasnake"
_save.mkdir()
(_save / "save.json").write_text(json.dumps({"settings": {"resolution": "720p", "fullscreen": False}}))

import build_info  # noqa: E402

build_info.STORE = "recorder"
import pygame  # noqa: E402

pygame.event.get = lambda *a, **k: []
import main  # noqa: E402
import network  # noqa: E402
from constants import GAME_VERSION  # noqa: E402
from capture_bot import Bot  # noqa: E402

ARROWS = {(0, -1): pygame.K_UP, (0, 1): pygame.K_DOWN, (-1, 0): pygame.K_LEFT, (1, 0): pygame.K_RIGHT}
SLOT_INDEX = {"p2": 1, "p3": 2, "p4": 3}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def run(code: str, out: Path, bots: int, minutes: float) -> None:
    g = main.Game()
    g.settings["show_fps"] = False
    g.lan_online = True
    g.online_code_input = network.normalize_room_code(code)
    g.state = main.STATE_ONLINE_JOIN_CODE
    g.handle_online_join_code_key(pygame.K_RETURN)
    log("bot 1 joining", g.online_code_input)

    extra = [network.OnlineClient(main.ONLINE_SERVER_URL, code, GAME_VERSION) for _ in range(bots - 1)]
    links = [None] * len(extra)
    retry_at = [0.0] * len(extra)
    rejoin_at = None
    bot = Bot()
    sent = {}

    w, h = main.display.get_size()
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                           "-r", "30", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                           "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    marks = {"matches": []}
    stop = out.with_name("STOP")
    t0 = last = time.monotonic()
    frame = 0
    last_state = None
    while time.monotonic() - t0 < minutes * 60 and not stop.exists():
        now = time.monotonic()
        dt = now - last
        last = now
        for i, c in enumerate(extra):
            if links[i] is None:
                if c is None:
                    if now >= retry_at[i]:
                        extra[i] = network.OnlineClient(main.ONLINE_SERVER_URL, code, GAME_VERSION)
                    continue
                r = c.poll_connect_result()
                if r:
                    links[i] = c.link
                    log(f"bot {i + 2} joined as {c.link.my_slot}")
                elif r is False:
                    log(f"bot {i + 2} failed: {c.error} (retrying in 5s)")
                    extra[i], retry_at[i] = None, now + 5
            else:
                links[i].poll()  # drain; bot 1's client already has the same snapshots
                if not links[i].connected:
                    log(f"bot {i + 2} lost its seat (retrying in 5s)")
                    links[i], extra[i], retry_at[i] = None, None, now + 5
        if g.state in (main.STATE_LAN_ERROR, main.STATE_MENU, main.STATE_LAN_MENU):
            if rejoin_at is None:
                log("bot 1 is out:", g.lan_error_msg or g.state, "(rejoining in 5s)")
                rejoin_at = now + 5
            elif now >= rejoin_at:
                rejoin_at = None
                g.lan_online = True
                g.online_code_input = network.normalize_room_code(code)
                g.state = main.STATE_ONLINE_JOIN_CODE
                g.handle_online_join_code_key(pygame.K_RETURN)
        if g.state != last_state:
            log("state:", g.state, "slot:", getattr(g.lan_link, "my_slot", None))
            if g.state == main.STATE_PLAYING and last_state != main.STATE_PAUSED:
                marks["matches"].append(frame / 30)
            last_state = g.state
        if g.state == main.STATE_PLAYING and g.lan_role == "client":
            mine = SLOT_INDEX.get(getattr(g.lan_link, "my_slot", ""), 1)
            for idx in range(1, 4):
                p = g.players[idx] if idx < len(g.players) else None
                if p is None or not g.players_alive[idx]:
                    continue
                if idx == mine:
                    apply = lambda d: g.handle_playing_key(ARROWS[d])  # noqa: E731
                else:
                    link = next((l for l in links if l is not None and SLOT_INDEX.get(l.my_slot) == idx), None)
                    if link is None:
                        continue

                    def apply(d, link=link, idx=idx):
                        if sent.get(idx) != d:
                            link.send({"type": "input", "dir": list(d)})
                            sent[idx] = d
                bot.decide(g, p, now - t0, apply)
        g._frame(min(dt, 0.05))
        # film at a steady 30 fps of wall-clock time
        while frame < (time.monotonic() - t0) * 30:
            ff.stdin.write(pygame.image.tobytes(main.display, "RGB"))
            frame += 1
        main.clock.tick(60)
    ff.stdin.close()
    ff.wait()
    for l in links:
        if l:
            l.close()
    out.with_suffix(".json").write_text(json.dumps(marks))
    log("done", out, f"{frame / 30:.0f}s")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    bots = int(sys.argv[sys.argv.index("--bots") + 1]) if "--bots" in sys.argv else 3
    minutes = float(sys.argv[sys.argv.index("--minutes") + 1]) if "--minutes" in sys.argv else 12
    if "--bots" in sys.argv:
        args.remove(str(bots))
    if "--minutes" in sys.argv:
        args.remove(sys.argv[sys.argv.index("--minutes") + 1])
    run(args[0], Path(args[1] if len(args) > 1 else "live_match.mp4"), bots, minutes)
