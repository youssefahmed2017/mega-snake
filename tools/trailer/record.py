# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Record real MEGA SNAKE gameplay clips for the trailer, headless, with a bot playing.

    python tools/trailer/record.py [out_dir] [--only name1,name2]

Writes <name>.mp4 (1920x1080, 60 fps), <name>.wav (the game's own sound effects)
and <name>.json (markers) for every scene below - one or more per feature, so the
editor can show all of them. A full run takes 15-20 minutes.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pygame

from capture import Bot, Recorder, main  # noqa: E402  (capture sets up the headless game)
import network
from constants import MODES, MAP_NAMES, SNAKE_SKINS, GRID_W, GRID_H, GAME_VERSION, TRAIL_NAMES
from events import (EVENT_FRENZY, EVENT_GOLD_RUSH, EVENT_BLACKOUT, EVENT_HUNTER, EVENT_QUAKE, EVENT_MIRROR,
                    EventDirector, HAZARDS, HAZARD_SHOWER, HAZARD_ROCKFALL, HAZARD_METEOR, HAZARD_TREMOR,
                    HAZARD_SURGE)
from food import Food, PowerUp, Downerup

SKINS = list(SNAKE_SKINS)
P = main  # constants re-exported by main (POWERUP_*, FOOD_*, DOWNERUP_*)


# ---------------------------------------------------------------- setup helpers

def start(mode: str, map_name: str = "Open", skin: str = "Classic", grow: int = 0, extra=None):
    def setup(g):
        g.mode_idx = MODES.index(mode)
        g.map_name = map_name
        g.skin_idx = SKINS.index(skin)
        g.lan_role = None
        g.reset_run()
        g.state = P.STATE_PLAYING
        if grow:
            g.player.grow(grow)
        if extra:
            extra(g)
    return setup


def screen(state, **attrs):
    def setup(g):
        g.lan_role = None
        g.reset_run()
        for k, v in attrs.items():
            setattr(g, k, v)
        g.state = state
    return setup


def ahead(g, n: int):
    """A free cell n steps in front of the player's head (or the nearest free one)."""
    hx, hy = g.player.head
    dx, dy = g.player.direction
    occ = g.occupied_cells()
    for k in range(n, n + 8):
        x, y = hx + dx * k, hy + dy * k
        if g.mode_cfg()["wrap"]:
            x, y = x % GRID_W, y % GRID_H
        if 0 <= x < GRID_W and 0 <= y < GRID_H and (x, y) not in occ:
            return x, y
    for r in range(2, 10):
        for x in range(hx - r, hx + r + 1):
            for y in (hy - r, hy + r):
                if 0 <= x < GRID_W and 0 <= y < GRID_H and (x, y) not in occ:
                    return x, y
    return hx, hy


def once(key: str, at: float, fn):
    def each(g, t, rec):
        if t >= at and key not in rec.markers:
            rec.mark(key, t)
            fn(g, t, rec)
    return each


def chain(*fns):
    def each(g, t, rec):
        for f in fns:
            f(g, t, rec)
    return each


def force_event(eid: str, at: float, lead: float = 1.2):
    """Have the chaos-event director warn about `eid` at `at` and start it `lead` s later."""
    def fn(g, t, rec):
        if g.event_director is None:
            g.event_director = EventDirector(random.Random(3))
        d = g.event_director
        d.active, d.incoming, d._next, d.countdown = None, None, eid, lead
        rec.mark("event_start", t + lead)
    return once("ev_" + eid, at, fn)


def stack_event(eid: str, at: float):
    """Start an event's effect directly, on top of whatever the director runs (chaos shots)."""
    return once("stack_" + eid, at, lambda g, t, rec: g._on_event("start", eid))


def hazard(hid: str, at: float):
    def fn(g, t, rec):
        if g.hazard_roller:
            g.hazard_roller.active, g.hazard_roller.remaining = hid, HAZARDS[hid].duration
        g._on_hazard("start", hid)
    return once("hz_" + hid, at, fn)


def drop_powerup(kind: str, at: float, dist: int = 4):
    return once("pu_" + kind, at, lambda g, t, rec: g.powerups.append(PowerUp(*ahead(g, dist), kind)))


def drop_downer(kind: str, at: float, dist: int = 4):
    return once("dn_" + kind, at, lambda g, t, rec: g.downerups.append(Downerup(*ahead(g, dist), kind)))


def drop_food(kind: str, at: float, dist: int = 4):
    return once("fd_" + kind + str(at), at, lambda g, t, rec: g.foods.append(Food(*ahead(g, dist), kind)))


def activate(kind: str, at: float):
    return once("on_" + kind, at, lambda g, t, rec: g._activate_powerup(kind))


def seek_powerups(g, s):
    return [(p.x, p.y) for p in g.powerups]


def seek_downers(g, s):
    return [(d.x, d.y) for d in g.downerups]


def seek_portal(g, s):
    return [g.portal_pair[0]] if g.portal_pair and g.p1_portal_lock <= 0 else []


def menu_steps(steps):
    """steps: {time: callable(g)} for walking a menu like a player."""
    def each(g, t, rec):
        for at, fn in steps.items():
            if abs(t - at) < 0.5 / 60:
                fn(g)
    return each


def key(state_handler: str, k):
    return lambda g: getattr(g, state_handler)(k)


# ---------------------------------------------------------------- LAN: a real 4-player match over sockets

class LanGuests:
    """Three in-process guests that join the recording game's LAN lobby over real TCP,
    say hello like a real build, and then steer their snakes by sending input messages."""

    def __init__(self) -> None:
        self.clients = []
        self.links = []
        self.sent = {}

    def setup(self, g):
        g.lan_role = None
        g.lan_online = False
        g.map_idx = MAP_NAMES.index("Arena")
        g.lan_setup_index = 2  # Start Hosting
        g.local_ip = "192.168.1.20"  # the recorder has no LAN; show what a player would see
        g.state = P.STATE_LAN_SETUP
        g.handle_lan_setup_key(pygame.K_RETURN)

    def each(self, g, t, rec):
        for at in (0.7, 1.5, 2.3):
            if t >= at and len(self.clients) < [0.7, 1.5, 2.3].index(at) + 1:
                self.clients.append(network.Client("127.0.0.1"))
        for c in self.clients:
            if c is not None and c not in [x[0] for x in self.links]:
                r = c.poll_connect_result()
                if r:
                    c.link.send({"type": "hello", "version": GAME_VERSION})
                    self.links.append((c, c.link))
        for _, link in self.links:
            link.poll()  # drain snapshots
        if (t >= 3.6 and g.state == P.STATE_LAN_HOST_WAIT and "lan_start" not in rec.markers
                and len(g.lan_host.roster) >= 4):
            rec.mark("lan_start", t)
            g.handle_lan_host_wait_key(pygame.K_RETURN)
            for p in g.players:
                if p is not None:
                    p.grow(6)

    def steer(self, g, i):
        if i == 0:
            return None
        link = self.links[i - 1][1] if i - 1 < len(self.links) else None

        def send(d):
            if link and self.sent.get(i) != d:
                link.send({"type": "input", "dir": list(d)})
                self.sent[i] = d
        return send

    def close(self, g):
        for _, link in self.links:
            link.close()
        g._lan_teardown()


# ---------------------------------------------------------------- scenes

def scenes():
    S = []

    def add(name, seconds, setup, each=None, **kw):
        S.append(((name, seconds, setup, each), kw))

    # --- chaos (the hook and the finale)
    add("chaos_max", 9, start("Hardcore", "Volcano", "Inferno", grow=22),
        chain(force_event(EVENT_FRENZY, 0.0, 0.3), hazard(HAZARD_SHOWER, 0.6), stack_event(EVENT_GOLD_RUSH, 1.4),
              stack_event(EVENT_QUAKE, 2.2), hazard(HAZARD_SURGE, 3.0), stack_event(EVENT_MIRROR, 3.8)),
        preroll=6, seed=31)
    add("chaos_battle", 8, start("Battle", "Arena", "Void", grow=16),
        chain(force_event(EVENT_FRENZY, 0.0, 0.3), stack_event(EVENT_GOLD_RUSH, 0.8), hazard(HAZARD_SHOWER, 1.2),
              activate(P.POWERUP_MAGNET, 2.0), stack_event(EVENT_QUAKE, 2.8)), preroll=4, seed=32)
    add("chaos_dark", 8, start("Roguelite", "Pillars", "Ice", grow=14),
        chain(force_event(EVENT_BLACKOUT, 0.0, 0.3), stack_event(EVENT_HUNTER, 0.5), hazard(HAZARD_SHOWER, 1.0),
              stack_event(EVENT_QUAKE, 2.0)), preroll=4, seed=33)
    add("chaos_death", 9, start("Hardcore", "Everest", "Gold", grow=30),
        chain(force_event(EVENT_FRENZY, 0.0, 0.3), stack_event(EVENT_HUNTER, 0.4), hazard(HAZARD_SHOWER, 0.8),
              stack_event(EVENT_QUAKE, 1.8), hazard(HAZARD_SURGE, 2.6)),
        preroll=8, seed=34, bot=Bot(suicide_after=5.0), tail_after_death=6.5)
    add("calm_snake", 5, start("Classic", "Open", "Classic"), seed=35)

    # --- menus / title
    add("menu", 5, screen(P.STATE_MENU, menu_index=0),
        menu_steps({0.9: key("handle_menu_key", pygame.K_DOWN), 1.4: key("handle_menu_key", pygame.K_DOWN),
                    1.9: key("handle_menu_key", pygame.K_UP), 2.4: key("handle_menu_key", pygame.K_UP)}))
    mode_steps = {0.6 + 0.45 * i: key("handle_menu_key", pygame.K_RIGHT) for i in range(9)}
    add("menu_modes", 5, screen(P.STATE_MENU, menu_index=1, mode_idx=0), menu_steps(mode_steps))
    skin_steps = {0.6 + 0.6 * i: key("handle_menu_key", pygame.K_RIGHT) for i in range(5)}
    add("menu_skins", 4, screen(P.STATE_MENU, menu_index=2, skin_idx=0), menu_steps(skin_steps))

    # --- the basics
    add("food_types", 7, start("Classic", "Open", "Classic", grow=6),
        chain(drop_food(P.FOOD_GOLDEN, 0.2, 3), drop_food(P.FOOD_SPEED, 1.6, 3), drop_food(P.FOOD_SHRINK, 3.4, 3)),
        preroll=2, seed=40, bot=Bot(seek=lambda g, s: [(f.x, f.y) for f in g.foods if f.kind != P.FOOD_NORMAL]))
    add("combo", 8, start("Classic", "Desert", "Gold", grow=10),
        chain(force_event(EVENT_FRENZY, 0.0, 0.3), activate(P.POWERUP_MAGNET, 0.4)), preroll=3, seed=41)
    add("near_miss", 7, start("Walls", "Open", "Ice", grow=14), preroll=3, seed=42,
        bot=Bot(seek=lambda g, s: [min(((x, y) for x in range(GRID_W) for y in (0, GRID_H - 1)
                                         if (x, y) not in g.occupied_cells()),
                                        key=lambda c: abs(c[0] - s.head[0]) + abs(c[1] - s.head[1]))]))
    add("portals", 7, start("Classic", "Open", "Void", grow=10,
                            extra=lambda g: setattr(g, "portal_pair", ((22, 6), (6, 16)))),
        preroll=1, seed=43, bot=Bot(seek=seek_portal))
    for i, (kind, mode, extra) in enumerate([
            (P.POWERUP_GHOST, "Walls", None), (P.POWERUP_MAGNET, "Classic", None),
            (P.POWERUP_SLOWMO, "Classic", None), (P.POWERUP_MULT, "Classic", None),
            (P.POWERUP_FREEZE, "Battle", None), (P.POWERUP_TELEPORT, "Classic", None)]):
        add(f"pu_{kind}", 6, start(mode, ["Open", "Pillars", "Glacier", "Desert", "Arena", "Cross"][i],
                                   SKINS[i % 5], grow=10),
            drop_powerup(kind, 0.2, 3), preroll=2, seed=50 + i, bot=Bot(seek=seek_powerups))
    add("pu_shield", 7, start("Walls", "Open", "Gold", grow=16), activate(P.POWERUP_SHIELD, 0.3),
        preroll=3, seed=57, bot=Bot(suicide_after=1.2))
    add("bomb_defused", 7, start("Classic", "Open", "Inferno", grow=10),
        chain(activate(P.POWERUP_SHIELD, 0.1), drop_downer(P.DOWNERUP_BOMB, 0.5, 3)),
        preroll=2, seed=58, bot=Bot(seek=seek_downers))
    add("curse", 6, start("Classic", "Cross", "Void", grow=10), drop_downer(P.DOWNERUP_CURSE, 0.2, 3),
        preroll=2, seed=59, bot=Bot(seek=seek_downers))
    add("revive", 8, start("Coop", "Open", "Classic", grow=6),
        chain(once("kill", 0.4, lambda g, t, rec: g._kill_snake("p2", "down")),
              drop_powerup(P.POWERUP_REVIVE, 1.4, 3)), preroll=2, seed=60, bot=Bot(seek=seek_powerups))

    # --- every mode
    for i, (mode, mp, pre) in enumerate([("Classic", "Open", 4), ("Walls", "Glacier", 4), ("Maze", "Open", 30),
                                         ("Battle", "Arena", 4), ("Timed", "Desert", 14), ("Hardcore", "Volcano", 4),
                                         ("Coop", "Cross", 4), ("Daily", "Open", 4), ("Roguelite", "Pillars", 4)]):
        each = hazard(HAZARD_METEOR, 0.6) if mode == "Hardcore" else None
        add(f"mode_{mode.lower()}", 5, start(mode, mp, SKINS[i % 5], grow=10), each, preroll=pre, seed=70 + i)

    # --- chaos events, one at a time
    for i, (eid, mode, mp) in enumerate([(EVENT_FRENZY, "Classic", "Desert"), (EVENT_GOLD_RUSH, "Classic", "Open"),
                                         (EVENT_BLACKOUT, "Classic", "Glacier"), (EVENT_MIRROR, "Classic", "Cross"),
                                         (EVENT_HUNTER, "Roguelite", "Pillars"), (EVENT_QUAKE, "Walls", "Everest")]):
        add(f"ev_{eid}", 7, start(mode, mp, SKINS[(i + 1) % 5], grow=12), force_event(eid, 0.1, 1.0),
            preroll=3, seed=80 + i)

    # --- Hardcore hazards
    for i, hid in enumerate([HAZARD_METEOR, HAZARD_SHOWER, HAZARD_TREMOR, HAZARD_SURGE, HAZARD_ROCKFALL]):
        add(f"hz_{hid}", 7, start("Hardcore", ["Volcano", "Everest", "Desert", "Open", "Glacier"][i], SKINS[i % 5],
                                  grow=10), hazard(hid, 0.3), preroll=3, seed=90 + i)

    # --- Roguelite perks
    add("perk_pick", 8, start("Roguelite", "Open", "Gold", grow=6,
                              extra=lambda g: g.stats.__setitem__("food_eaten", 7)), seed=100)
    add("perk_dash", 6, start("Roguelite", "Pillars", "Void", grow=12,
                              extra=lambda g: g.perks.__setitem__("dash", 1)),
        once("dash", 1.0, lambda g, t, rec: g._try_dash()), preroll=3, seed=101, bot=Bot(suicide_after=0.8))
    add("perk_second_wind", 7, start("Roguelite", "Open", "Ice", grow=14,
                                     extra=lambda g: (g.perks.__setitem__("second_wind", 1),
                                                      setattr(g, "perk_lives", 1))),
        preroll=3, seed=102, bot=Bot(suicide_after=1.0))

    # --- every map
    for i, m in enumerate(MAP_NAMES):
        add(f"map_{m.lower()}", 3.5, start("Classic" if m == "Open" else "Walls", m, SKINS[i % 5], grow=8),
            preroll=2, seed=110 + i)

    # --- multiplayer
    add("lan_menu", 3.5, screen(P.STATE_LAN_MENU, lan_menu_index=0),
        menu_steps({0.8: key("handle_lan_menu_key", pygame.K_DOWN), 1.4: key("handle_lan_menu_key", pygame.K_DOWN),
                    2.0: key("handle_lan_menu_key", pygame.K_DOWN)}))
    lan = LanGuests()
    add("lan_4p", 14, lan.setup, lan.each, steer=lan.steer, seed=120, after=lan.close)

    # --- progression and polish
    add("trail_rainbow", 6, start("Classic", "Open", "Void", grow=12,
                                  extra=lambda g: setattr(g, "equipped_trail", "Rainbow")), preroll=2, seed=130)
    add("ghost_seed", 5, start("Walls", "Open", "Classic", grow=4), preroll=6, seed=131,
        bot=Bot(suicide_after=3.0), tail_after_death=5)
    add("ghost_replay", 7, start("Walls", "Open", "Inferno"), seed=132)
    add("initials", 6, start("Walls", "Open", "Gold", grow=30), preroll=12, seed=133,
        bot=Bot(suicide_after=0.5), tail_after_death=7)
    add("achievements", 4, screen(P.STATE_ACHIEVEMENTS),
        once("scroll", 1.4, lambda g, t, rec: g._ach_scroll_by(220)))
    add("shop", 4, screen(P.STATE_SHOP, shop_index=0),
        menu_steps({0.8: key("handle_shop_key", pygame.K_DOWN), 1.5: key("handle_shop_key", pygame.K_DOWN),
                    2.2: key("handle_shop_key", pygame.K_DOWN)}))
    add("quests", 3.5, screen(P.STATE_QUESTS))
    add("stats", 3.5, screen(P.STATE_STATS))
    add("leaderboard", 3.5, screen(P.STATE_LEADERBOARD))
    add("settings_display", 4, screen(P.STATE_SETTINGS, settings_tab=2, settings_index=0, prev_state=P.STATE_MENU,
                                      ), once("res", 0.0, lambda g, t, rec: g.settings.__setitem__("resolution", "4K")))
    add("settings_controller", 3.5, screen(P.STATE_SETTINGS, settings_tab=3, settings_index=0, pad_active=True,
                                           prev_state=P.STATE_MENU))
    add("colorblind", 5, start("Classic", "Open", "Classic", grow=8,
                               extra=lambda g: (setattr(g, "colorblind", True), g.powerups.append(
                                   PowerUp(*ahead(g, 6), P.POWERUP_SHIELD)))), preroll=1, seed=140)
    add("controller_play", 5, start("Classic", "Pillars", "Ice", grow=8,
                                    extra=lambda g: setattr(g, "pad_active", True)), preroll=2, seed=141)
    add("howto", 3.5, screen(P.STATE_HOWTO))
    add("changelog", 3.5, screen(P.STATE_CHANGELOG))
    add("update_check", 3, screen(P.STATE_UPDATE_CHECK, update_checker=None, update_check_anim=0.0))
    add("easter_egg", 4, screen(P.STATE_EASTER_WARNING, easter_stage=0))
    return S


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else Path("trailer_clips")
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    rec = Recorder(out)
    for (name, seconds, setup, each), kw in scenes():
        after = kw.pop("after", None)
        if only and name not in only:
            continue
        tries = 0
        while True:
            meta = rec.scene(name, seconds, setup, each, **kw)
            bot = kw.get("bot")
            planned = bot is not None and bot.suicide_after is not None
            early = meta["died"] and not planned and meta["markers"].get("death", 99) < seconds * 0.9
            if not early or tries >= 7:
                break
            tries += 1  # the bot died by accident: same scene, different luck
            kw["seed"] = kw.get("seed", 1) + 1000
            if bot is not None:
                bot._last.clear()
            print(f"    retrying {name} (died at {meta['markers']['death']:.1f}s)", flush=True)
        if after:
            after(rec.game)
        rec.game.colorblind = False
        rec.game.pad_active = False
        rec.game.equipped_trail = "None"
        rec.game.perks = {}
        rec.game.perk_lives = 0
        rec.game.curse_timer = 0.0
        rec.game.event_director = None
