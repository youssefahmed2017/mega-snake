# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Record real MEGA SNAKE gameplay clips for the trailer, headless, with a bot playing.

    python tools/trailer/record.py [out_dir] [--only name1,name2]

Writes <name>.mp4 (1920x1080, 60 fps), <name>.wav (the game's own sound effects)
and <name>.json (markers) for every scene below. Renders faster than real time is
not guaranteed - a full run takes a few minutes.
"""
from __future__ import annotations

import sys
from pathlib import Path

from capture import Bot, Recorder, main  # noqa: E402  (capture sets up the headless game)
from constants import MODES, MAP_NAMES, SNAKE_SKINS
from events import EVENT_FRENZY, EVENT_GOLD_RUSH, EVENT_BLACKOUT, EVENT_HUNTER, EVENT_QUAKE, EVENT_MIRROR, \
    EventDirector, HAZARDS, HAZARD_SHOWER, HAZARD_ROCKFALL, HAZARD_METEOR
import random

SKINS = list(SNAKE_SKINS)


def start(mode: str, map_name: str = "Open", skin: str = "Classic", grow: int = 0):
    def setup(g):
        g.mode_idx = MODES.index(mode)
        g.map_name = map_name
        g.skin_idx = SKINS.index(skin)
        g.reset_run()
        g.state = main.STATE_PLAYING
        if grow:
            g.player.grow(grow)
    return setup


def force_event(eid: str, at: float, lead: float = 1.6):
    """Make the chaos-event director warn about `eid` at `at` and start it `lead` s later."""
    def each(g, t, rec):
        if t >= at and "ev" not in rec.markers:
            if g.event_director is None:
                g.event_director = EventDirector(random.Random(3))
            d = g.event_director
            d.active, d.incoming, d._next, d.countdown = None, None, eid, lead
            rec.mark("ev", t)
            rec.mark("event_start", t + lead)
    return each


def force_hazard(hid: str, at: float):
    def each(g, t, rec):
        key = "hz_" + hid
        if t >= at and key not in rec.markers:
            if g.hazard_roller:
                g.hazard_roller.active, g.hazard_roller.remaining = hid, HAZARDS[hid].duration
            g._on_hazard("start", hid)
            rec.mark(key, t)
    return each


def chain(*fns):
    def each(g, t, rec):
        for f in fns:
            f(g, t, rec)
    return each


def give(kind: str, at: float):
    def each(g, t, rec):
        if t >= at and ("pu_" + kind) not in rec.markers:
            g._activate_powerup(kind)
            rec.mark("pu_" + kind, t)
    return each


def menu_setup(state):
    def setup(g):
        g.reset_run()
        g.menu_index = 0
        g.state = state
    return setup


def menu_walk(g, t, rec):
    # glide down the menu like a player looking around, then back up to Start
    steps = {0.9: 1, 1.3: 1, 1.7: 1, 2.4: -1, 2.8: -1, 3.2: -1}
    for at, d in steps.items():
        if abs(t - at) < 0.5 / 60:
            g.menu_index = (g.menu_index + d) % len(main.MENU_ITEMS)
            g.sounds.play(g.sounds.menu_move)


def scenes():
    S = []
    add = lambda *a, **k: S.append((a, k))  # noqa: E731
    add("menu", 4.5, menu_setup(main.STATE_MENU), menu_walk)
    add("classic_goldrush", 9, start("Classic", "Open", "Inferno", grow=18), force_event(EVENT_GOLD_RUSH, 0.4, 1.4),
        preroll=6)
    add("frenzy_magnet", 8, start("Classic", "Desert", "Gold", grow=10),
        chain(force_event(EVENT_FRENZY, 0.2, 1.0), give(main.POWERUP_MAGNET, 1.3)), preroll=3)
    add("battle", 10, start("Battle", "Arena", "Void", grow=6), preroll=2, seed=4)
    add("hardcore_meteors", 9, start("Hardcore", "Volcano", "Classic", grow=8),
        chain(force_hazard(HAZARD_SHOWER, 0.5), force_hazard(HAZARD_ROCKFALL, 6.2)), preroll=2, seed=7)
    add("hunter", 9, start("Roguelite", "Pillars", "Ice", grow=10), force_event(EVENT_HUNTER, 0.2, 1.2),
        preroll=2, seed=5)
    add("blackout", 8, start("Classic", "Glacier", "Ice", grow=12), force_event(EVENT_BLACKOUT, 0.2, 1.2),
        preroll=3, seed=6)
    add("quake", 8, start("Walls", "Everest", "Classic", grow=12), force_event(EVENT_QUAKE, 0.2, 1.2),
        preroll=3, seed=8)
    add("mirror", 7, start("Classic", "Cross", "Void", grow=10), force_event(EVENT_MIRROR, 0.2, 1.2),
        preroll=3, seed=9)
    add("ghost_walls", 7, start("Walls", "Open", "Void", grow=14), give(main.POWERUP_GHOST, 0.3), preroll=3, seed=10)
    add("perks", 9, lambda g: (start("Roguelite", "Open", "Gold", grow=6)(g), g.stats.__setitem__("food_eaten", 7)),
        seed=11)
    add("coop", 10, start("Coop", "Cross", "Classic", grow=6), preroll=2, seed=12)
    for i, m in enumerate(MAP_NAMES):
        add(f"map_{m.lower()}", 3, start("Classic" if m == "Open" else "Walls", m, SKINS[i % len(SKINS)], grow=8),
            preroll=2, seed=20 + i)
    add("death_wall", 7, start("Walls", "Open", "Inferno", grow=45), preroll=14, seed=13,
        bot=Bot(suicide_after=4.2), tail_after_death=5.5)
    add("lan_menu", 3, menu_setup(main.STATE_LAN_MENU))
    add("achievements", 3, menu_setup(main.STATE_ACHIEVEMENTS))
    add("shop", 3, menu_setup(main.STATE_SHOP))
    return S


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else Path("trailer_clips")
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    rec = Recorder(out)
    for args, kw in scenes():
        if only and args[0] not in only:
            continue
        rec.scene(*args, **kw)
