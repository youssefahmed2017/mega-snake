# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""The dev cheat console: only built into dev builds (build_info.DEV, see tools/build_dev.py).

Press ` (or F10) to drop it down, type `help`. It drives the one authoritative `Game` directly, so every
command here is just a poke at the same fields the game itself uses. Nothing here is ever created in a normal
build (`Game.dev` stays None), and the dev build keeps its save in ~/.megasnake-dev so cheating can't touch
real progress. Gameplay commands refuse to run in LAN/online games (the host is authoritative).
"""
from __future__ import annotations

import random
import shlex
import sys
from collections import deque
from typing import Callable, Dict, List, Optional, Tuple

import pygame

import gfx
import persistence
from achievements import ACHIEVEMENTS, ACHIEVEMENTS_BY_ID
from constants import (
    ARCADE_MODES, DOWNERUP_BOMB, DOWNERUP_CURSE, DOWNERUP_SHRINK, FOOD_GOLDEN, FOOD_NORMAL, FOOD_SPEED, GRID_H, GRID_W,
    LUCKY_EFFECTS, MODES, POWERUP_COLORS, POWERUP_DURATIONS, REVERSED_LEVEL_SECONDS, REVERSED_MAX_LEVEL, SNAKE_SKINS,
    TRAIL_EFFECTS,
)
from enemy import EnemySnake
from events import EVENTS, HAZARDS, PERKS, EventDirector
from food import Downerup, Food, LuckyBlock, PowerUp, random_free_cell
from settings_defs import SETTING_DEFS

TEXT = (225, 232, 240)
DIM = (130, 145, 165)
OK = (110, 230, 150)
ERR = (255, 110, 110)
ACCENT = (92, 200, 255)
WARN = (255, 200, 87)

PANEL_H = 360
LINE_H = 17
MAX_LOG = 400
MAX_HISTORY = 100


class CmdError(Exception):
    """A user-facing command failure: shown in red, nothing else happens."""


class Cmd:
    def __init__(self, fn: Callable, name: str, usage: str, doc: str, run: bool, args: Optional[Callable]) -> None:
        self.fn, self.name, self.usage, self.doc, self.run, self.args = fn, name, usage, doc, run, args


COMMANDS: Dict[str, Cmd] = {}
ALIASES = {"?": "help", "cls": "clear", "tele": "tp", "ts": "timescale", "gm": "god", "exit": "quit"}


def cmd(name: str, usage: str = "", doc: str = "", run: bool = False, args: Optional[Callable] = None):
    """Register a command. run=True means it needs a live solo run (playing or paused)."""
    def deco(fn):
        COMMANDS[name] = Cmd(fn, name, usage, doc, run, args)
        return fn
    return deco


def _pick(word: str, options: List[str], what: str) -> str:
    """Case-insensitive exact or unique-prefix match of `word` among `options`."""
    w = word.lower()
    for o in options:
        if o.lower() == w:
            return o
    hits = [o for o in options if o.lower().startswith(w)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise CmdError(f"unknown {what} '{word}'  (options: {', '.join(options)})")
    raise CmdError(f"'{word}' is ambiguous: {', '.join(hits)}")


def _num(word: str, current: float = 0) -> float:
    """'50' sets, '+50' / '-50' add."""
    try:
        v = float(word)
    except ValueError:
        raise CmdError(f"'{word}' is not a number")
    return current + v if word[0] in "+-" else v


def _bool(word: Optional[str], current: bool) -> bool:
    if word is None or word.lower() == "toggle":
        return not current
    if word.lower() in ("1", "on", "true", "yes", "y"):
        return True
    if word.lower() in ("0", "off", "false", "no", "n"):
        return False
    raise CmdError(f"'{word}': use on/off")


class DevConsole:
    def __init__(self, game) -> None:
        self.g = game
        self.M = sys.modules[type(game).__module__]  # main.py's module, whether it is __main__ or imported
        self.open = False
        self.input = ""
        self.cursor = 0
        self.history: List[str] = []
        self.hist_pos = 0
        self.log: List[Tuple[str, Tuple[int, int, int]]] = []
        self.scroll = 0
        self.aliases: Dict[str, str] = {}
        self.timers: List[list] = []  # [seconds left, fn]
        # Switches the rest of the game reads (see main.py's _phased / move_interval / _frame):
        self.god = False
        self.speed_mult = 1.0
        self.time_scale = 1.0
        self.frozen = False
        self.pause_when_open = True
        self.debug = False
        self.out("MEGA SNAKE dev console. Type `help`.  ` or F10 closes it.", ACCENT)

    # ---------- output ----------

    def out(self, text: str, color=TEXT) -> None:
        for line in str(text).split("\n"):
            while line and self.M.font_tiny.size(line)[0] > self.M.SCREEN_W - 40:
                cut = len(line)
                while cut > 1 and self.M.font_tiny.size(line[:cut])[0] > self.M.SCREEN_W - 40:
                    cut -= 1
                self.log.append((line[:cut], color))
                line = "   " + line[cut:]
            self.log.append((line, color))
        del self.log[:-MAX_LOG]
        self.scroll = 0

    def ok(self, text: str) -> None:
        self.out(text, OK)

    # ---------- frame hooks ----------

    def adjust_dt(self, dt: float) -> float:
        """Called every frame by Game._frame: console pause, freeze, time scale and delayed commands."""
        if self.open and self.pause_when_open:
            return 0.0
        if self.frozen:
            return 0.0
        dt *= self.time_scale
        for t in list(self.timers):
            t[0] -= dt
            if t[0] <= 0:
                self.timers.remove(t)
                try:
                    t[1]()
                except Exception as e:  # a delayed command must never take the game down
                    self.out(f"delayed command failed: {e}", ERR)
        return dt

    def later(self, seconds: float, fn: Callable) -> None:
        self.timers.append([seconds, fn])

    # ---------- input ----------

    def _text_state_blocks_hotkey(self) -> bool:
        g, M = self.g, self.M
        return bool(g.chat_active or g.state in (M.STATE_LAN_JOIN_IP, M.STATE_ONLINE_JOIN_CODE, M.STATE_ENTER_INITIALS))

    def toggle(self) -> None:
        self.open = not self.open
        if self.open:
            pygame.key.start_text_input()
            self.scroll = 0
        elif not self.g.chat_active:
            pygame.key.stop_text_input()

    def handle_event(self, event: pygame.event.Event) -> bool:
        """True when the console used the event (the game must not see it)."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F10 or (event.key == pygame.K_BACKQUOTE and not self._text_state_blocks_hotkey()):
                self.toggle()
                return True
        if not self.open:
            return False
        if event.type == pygame.TEXTINPUT:
            text = "".join(c for c in event.text if c not in "`~" and c.isprintable())
            self.input = self.input[:self.cursor] + text + self.input[self.cursor:]
            self.cursor += len(text)
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll + event.y * 3)
            return True
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            return True
        if event.type != pygame.KEYDOWN:
            return event.type == pygame.KEYUP
        k, mods = event.key, getattr(event, "mod", 0)
        ctrl = bool(mods & pygame.KMOD_CTRL)
        if k == pygame.K_ESCAPE:
            self.toggle()
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            line, self.input, self.cursor = self.input.strip(), "", 0
            if line:
                self.out("> " + line, DIM)
                if not self.history or self.history[-1] != line:
                    self.history.append(line)
                    del self.history[:-MAX_HISTORY]
                self.hist_pos = len(self.history)
                self.run_line(line)
        elif k == pygame.K_BACKSPACE:
            if self.cursor:
                self.input = self.input[:self.cursor - 1] + self.input[self.cursor:]
                self.cursor -= 1
        elif k == pygame.K_DELETE:
            self.input = self.input[:self.cursor] + self.input[self.cursor + 1:]
        elif k == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
        elif k == pygame.K_RIGHT:
            self.cursor = min(len(self.input), self.cursor + 1)
        elif k == pygame.K_HOME:
            self.cursor = 0
        elif k == pygame.K_END:
            self.cursor = len(self.input)
        elif k == pygame.K_UP:
            if self.history:
                self.hist_pos = max(0, self.hist_pos - 1)
                self.input = self.history[self.hist_pos]
                self.cursor = len(self.input)
        elif k == pygame.K_DOWN:
            self.hist_pos = min(len(self.history), self.hist_pos + 1)
            self.input = self.history[self.hist_pos] if self.hist_pos < len(self.history) else ""
            self.cursor = len(self.input)
        elif k == pygame.K_PAGEUP:
            self.scroll += 8
        elif k == pygame.K_PAGEDOWN:
            self.scroll = max(0, self.scroll - 8)
        elif k == pygame.K_TAB:
            self._complete()
        elif ctrl and k == pygame.K_l:
            self.log.clear()
        elif ctrl and k == pygame.K_u:
            self.input, self.cursor = "", 0
        elif ctrl and k == pygame.K_v:
            try:
                pygame.scrap.init()
                raw = pygame.scrap.get_text() if hasattr(pygame.scrap, "get_text") else ""
                text = "".join(c for c in (raw or "") if c.isprintable())
                self.input = self.input[:self.cursor] + text + self.input[self.cursor:]
                self.cursor += len(text)
            except Exception:
                pass
        return True

    def _complete(self) -> None:
        head = self.input[:self.cursor]
        parts = head.split(" ")
        if len(parts) == 1:
            pool = sorted(set(COMMANDS) | set(self.aliases))
            word = parts[0]
        else:
            c = COMMANDS.get(ALIASES.get(parts[0], parts[0]))
            if not c or not c.args or len(parts) != 2:
                return
            pool, word = c.args(self), parts[1]
        hits = [p for p in pool if p.lower().startswith(word.lower())]
        if not hits:
            return
        common = hits[0]
        for h in hits[1:]:
            while not h.lower().startswith(common.lower()):
                common = common[:-1]
        if len(hits) == 1:
            common += " "
        elif len(common) == len(word):
            self.out("  ".join(hits), DIM)
        rest = self.input[self.cursor:]
        self.input = " ".join(parts[:-1] + [common]).lstrip() + rest
        self.cursor = len(self.input) - len(rest)

    # ---------- running commands ----------

    def run_line(self, line: str, depth: int = 0) -> None:
        for piece in line.split(";"):
            piece = piece.strip()
            if piece:
                self._run_one(piece, depth)

    def _run_one(self, line: str, depth: int) -> None:
        if depth > 8:
            self.out("alias loop?", ERR)
            return
        try:
            words = shlex.split(line)
        except ValueError as e:
            self.out(f"parse error: {e}", ERR)
            return
        if not words:
            return
        name = words[0].lower()
        if name in self.aliases:
            self.run_line(" ".join([self.aliases[name]] + [shlex.quote(w) for w in words[1:]]), depth + 1)
            return
        name = ALIASES.get(name, name)
        c = COMMANDS.get(name)
        if c is None:
            hits = [n for n in COMMANDS if n.startswith(name)]
            if len(hits) == 1:
                c = COMMANDS[hits[0]]
            else:
                self.out(f"unknown command '{name}'" + (f"  (did you mean: {', '.join(hits)})" if hits else "  (try `help`)"), ERR)
                return
        try:
            if c.run:
                self.need_run()
            c.fn(self, words[1:])
        except CmdError as e:
            self.out(str(e), ERR)
            if c.usage and "usage" not in str(e):
                self.out(f"usage: {c.name} {c.usage}", DIM)
        except Exception as e:  # a bad command must never crash the game
            self.out(f"{type(e).__name__}: {e}", ERR)

    def need_run(self) -> None:
        g, M = self.g, self.M
        if g.lan_role is not None:
            raise CmdError("cheats are off in LAN/online games")
        if g.state not in (M.STATE_PLAYING, M.STATE_PAUSED, M.STATE_PERK_PICK):
            raise CmdError("start a run first (try `mode classic`)")

    # ---------- drawing ----------

    def draw(self, screen) -> None:
        M, g = self.M, self.g
        badge = ["DEV"]
        if self.god:
            badge.append("GOD")
        if self.frozen:
            badge.append("FROZEN")
        if self.time_scale != 1.0:
            badge.append(f"time x{self.time_scale:g}")
        if self.speed_mult != 1.0:
            badge.append(f"speed x{self.speed_mult:g}")
        if not self.pause_when_open:
            badge.append("live")
        tag = M.font_tiny.render("  ".join(badge), True, WARN)
        screen.blit(tag, (6, 4) if not self.open else (6, PANEL_H + 4))
        if self.debug:
            self._draw_debug(screen)
        if not self.open:
            return
        w = M.SCREEN_W
        panel = gfx.surface((w, PANEL_H), pygame.SRCALPHA)
        panel.fill((8, 11, 18, 232))
        gfx.draw.rect(panel, (*ACCENT, 255), pygame.Rect(0, PANEL_H - 2, w, 2))
        rows = (PANEL_H - 44) // LINE_H
        total = len(self.log)
        self.scroll = min(self.scroll, max(0, total - rows))
        end = total - self.scroll
        shown = self.log[max(0, end - rows):end]
        y = PANEL_H - 38 - len(shown) * LINE_H
        for text, color in shown:
            panel.blit(M.font_tiny.render(text, True, color), (10, y))
            y += LINE_H
        if self.scroll:
            panel.blit(M.font_tiny.render(f"^ scrolled {self.scroll}", True, DIM), (w - 110, 6))
        iy = PANEL_H - 30
        gfx.draw.rect(panel, (20, 26, 38, 255), pygame.Rect(6, iy - 3, w - 12, 24), border_radius=5)
        prompt = "> "
        panel.blit(M.font_small.render(prompt + self.input, True, TEXT), (12, iy - 2))
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            cx = 12 + M.font_small.size(prompt + self.input[:self.cursor])[0]
            gfx.draw.rect(panel, (*ACCENT, 255), pygame.Rect(cx, iy, 2, 17))
        screen.blit(panel, (0, 0))

    def _draw_debug(self, screen) -> None:
        g, M = self.g, self.M
        lines = [
            f"state {g.state}  mode {g.mode_name()}  solo {g.lan_role is None}",
            f"score {g.score}  combo {g.combo}  len {len(g.player.body)}  head {g.player.head}  dir {g.player.direction}",
            f"tick {g.move_interval() * 1000:.0f}ms  alive {g.player_alive}  t {g.time_alive:.1f}s",
            f"foods {len(g.foods)}  powerups {len(g.powerups)}  downerups {len(g.downerups)}  lucky {len(g.luckyblocks)}",
            f"rivals {len(g.rivals)}  obstacles {len(g.obstacles)}  portals {bool(g.portal_pair)}",
            f"active {{{', '.join(f'{k}:{v:.0f}' for k, v in g.active_powerups.items())}}}",
            f"curse {g.curse_timer:.1f}  invinc {g.invincible_timer:.1f}  warp {g.warp_timer:.1f}  boost {g.speed_boost_timer:.1f}",
        ]
        d = g.event_director
        if d:
            lines.append(f"event {d.active or '-'} ({d.remaining:.0f}s)  next {d._next} in {d.countdown:.0f}s")
        y = 4
        for ln in lines:
            r = M.font_tiny.render(ln, True, TEXT)
            screen.blit(r, (M.SCREEN_W - r.get_width() - 6, y + (PANEL_H if self.open else 0)))
            y += LINE_H


# =====================================================================================================
# commands
# =====================================================================================================

def _all_states(c: DevConsole) -> Dict[str, str]:
    return {k[6:].lower(): v for k, v in vars(c.M).items() if k.startswith("STATE_") and isinstance(v, str)}


def _modes(c: DevConsole) -> List[str]:
    return list(MODES) + list(ARCADE_MODES)


def _powerup_kinds() -> List[str]:
    return list(POWERUP_COLORS)


def _free_cell(c: DevConsole, a: List[str]) -> Tuple[int, int]:
    """x y from the args, else a random free cell."""
    if len(a) >= 2:
        x, y = int(_num(a[0])), int(_num(a[1]))
        if not (0 <= x < GRID_W and 0 <= y < GRID_H):
            raise CmdError(f"({x}, {y}) is off the {GRID_W}x{GRID_H} board")
        return x, y
    return random_free_cell(c.g.occupied_cells())


@cmd("help", "[command]", "List commands, or show one command's usage.")
def _help(c: DevConsole, a: List[str]) -> None:
    if a:
        name = ALIASES.get(a[0].lower(), a[0].lower())
        k = COMMANDS.get(name)
        if not k:
            raise CmdError(f"no command '{a[0]}'")
        c.out(f"{k.name} {k.usage}", ACCENT)
        c.out("  " + k.doc, TEXT)
        return
    c.out("Commands (`help <cmd>` for details; separate several with ;  Tab completes, Up/Down = history):", ACCENT)
    groups = [
        ("Console", "help clear echo alias exec repeat debug quit"),
        ("Run & modes", "mode state restart pause kill win level"),
        ("Player", "god score combo coins grow shrink length tp dir lives"),
        ("Time", "timescale speed freeze step timer keeplive"),
        ("Items", "give spawn lucky portal obstacle clear"),
        ("Chaos", "event hazard perk meteor"),
        ("Progress", "ach arcade skin trail streak quest resetsave"),
        ("Settings & fx", "set get sound shake announce toast seed"),
    ]
    for title, names in groups:
        c.out(f"  {title}: {names}", TEXT)


@cmd("clear", "[foods|powerups|downerups|lucky|obstacles|rivals|all]", "No args: clear this console. Else remove those things from the board.")
def _clear(c: DevConsole, a: List[str]) -> None:
    if not a:
        c.log.clear()
        return
    c.need_run()
    g = c.g
    what = _pick(a[0], ["foods", "powerups", "downerups", "lucky", "obstacles", "rivals", "all"], "thing")
    if what in ("foods", "all"):
        g.foods.clear()
    if what in ("powerups", "all"):
        g.powerups.clear()
    if what in ("downerups", "all"):
        g.downerups.clear()
    if what in ("lucky", "all"):
        g.luckyblocks.clear()
    if what in ("obstacles", "all"):
        g.obstacles.clear()
        g.temp_obstacles = set()
    if what in ("rivals", "all"):
        g.rivals.clear()
    if what in ("foods", "all") and not g.foods and g.mode_cfg().get("food", True):
        g._spawn_food()  # a board with no food at all would just stall some modes
    c.ok(f"cleared {what}")


@cmd("echo", "<text>", "Print text.")
def _echo(c: DevConsole, a: List[str]) -> None:
    c.out(" ".join(a))


@cmd("alias", "<name> <commands...>", "Define a shortcut, e.g. alias rich coins 9999;score 5000. No args: list them.")
def _alias(c: DevConsole, a: List[str]) -> None:
    if not a:
        for k, v in c.aliases.items():
            c.out(f"  {k} = {v}")
        return
    if len(a) < 2:
        raise CmdError("give the alias a command")
    if a[0].lower() in COMMANDS:
        raise CmdError("that name is a built-in command")
    c.aliases[a[0].lower()] = " ".join(a[1:])
    c.ok(f"alias {a[0]} set")


@cmd("exec", "<commands...>", "Run several commands (same as separating them with ;).")
def _exec(c: DevConsole, a: List[str]) -> None:
    c.run_line(" ".join(a))


@cmd("repeat", "<n> <command...>", "Run a command n times.")
def _repeat(c: DevConsole, a: List[str]) -> None:
    if len(a) < 2:
        raise CmdError("usage error")
    for _ in range(min(500, int(_num(a[0])))):
        c.run_line(" ".join(shlex.quote(w) for w in a[1:]))


@cmd("debug", "[on|off]", "Toggle the live state overlay (top right).")
def _debug(c: DevConsole, a: List[str]) -> None:
    c.debug = _bool(a[0] if a else None, c.debug)
    c.ok(f"debug overlay {'on' if c.debug else 'off'}")


@cmd("quit", "", "Close the game immediately (no save of the current run).")
def _quit(c: DevConsole, a: List[str]) -> None:
    pygame.quit()
    sys.exit(0)


# ---------- run & modes ----------

@cmd("mode", "<name|list>", "Start a fresh run in a mode (Classic, Walls, ... or an Arcade mode).", args=lambda c: _modes(c))
def _mode(c: DevConsole, a: List[str]) -> None:
    g, M = c.g, c.M
    if g.lan_role is not None:
        raise CmdError("leave the multiplayer game first")
    if not a or a[0] == "list":
        c.out("modes: " + ", ".join(_modes(c)))
        return
    name = _pick(" ".join(a), _modes(c), "mode")
    if name in ARCADE_MODES:
        g.arcade_unlocked = True
        g.start_arcade(name)
    else:
        g.mode_idx = MODES.index(name)
        g.reset_run()
        g.state = M.STATE_PLAYING
    c.ok(f"started {name}")


@cmd("state", "<name|list>", "Jump straight to a screen (menu, shop, achievements, settings, game_over...).",
     args=lambda c: list(_all_states(c)))
def _state(c: DevConsole, a: List[str]) -> None:
    states = _all_states(c)
    if not a or a[0] == "list":
        c.out("states: " + ", ".join(states))
        return
    c.g.state = states[_pick(a[0], list(states), "state")]
    c.ok(f"state = {c.g.state}")


@cmd("restart", "", "Restart the current mode's run.")
def _restart(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if g.lan_role is not None:
        raise CmdError("not in multiplayer")
    if g.arcade_mode:
        g.start_arcade(g.arcade_mode)
    else:
        g.reset_run()
        g.state = c.M.STATE_PLAYING
    c.ok("restarted")


@cmd("pause", "", "Pause or resume the run (the same as P).", run=True)
def _pause(c: DevConsole, a: List[str]) -> None:
    M, g = c.M, c.g
    if g.state == M.STATE_PLAYING:
        g.pause_index = 0
        g.state = M.STATE_PAUSED
    elif g.state == M.STATE_PAUSED:
        g.state = M.STATE_PLAYING


@cmd("kill", "", "Kill the snake (game over as normal).", run=True)
def _kill(c: DevConsole, a: List[str]) -> None:
    c.g._kill_snake("p1", "Killed from the dev console.")


@cmd("win", "", "Win the current run: Maze Escape exit, or end a timed run now.", run=True)
def _win(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if g.arcade_mode == "Maze Escape":
        g._arcade_win()
    else:
        g._time_up()


@cmd("level", "<n>", "Reversed arcade mode: jump to level n (spawns the hunters you'd have met by then).", run=True)
def _level(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if g.arcade_mode != "Reversed":
        raise CmdError("only in the Reversed arcade mode")
    n = max(1, min(REVERSED_MAX_LEVEL, int(_num(a[0]))))
    while g.reversed_level < n:
        g.rivals.append(g._reversed_hunter(len(g.rivals)))
        g.reversed_level += 1
    g.time_alive = max(g.time_alive, (n - 1) * REVERSED_LEVEL_SECONDS)
    c.ok(f"level {g.reversed_level}, {len(g.rivals)} hunters")


# ---------- player ----------

@cmd("god", "[on|off]", "Can't die: walls, bodies, hunters, meteors and bombs all pass through you.")
def _god(c: DevConsole, a: List[str]) -> None:
    c.god = _bool(a[0] if a else None, c.god)
    c.ok(f"god mode {'ON' if c.god else 'off'}")


@cmd("score", "<n|+n|-n>", "Set or add to the score.", run=True)
def _score(c: DevConsole, a: List[str]) -> None:
    c.g.score = max(0, int(_num(a[0], c.g.score)))
    c.ok(f"score = {c.g.score}")


@cmd("combo", "<n>", "Set the combo (1-20) and refresh its timer.", run=True)
def _combo(c: DevConsole, a: List[str]) -> None:
    g = c.g
    g.combo = max(1, min(20, int(_num(a[0], g.combo))))
    g.combo_timer = g.combo_window
    c.ok(f"combo = {g.combo}")


@cmd("coins", "<n|+n|-n>", "Set or add to your coin wallet (saved).")
def _coins(c: DevConsole, a: List[str]) -> None:
    g = c.g
    g.wallet = max(0, int(_num(a[0], g.wallet)))
    g.save_wallet()
    c.ok(f"wallet = {g.wallet}")


@cmd("grow", "[n]", "Grow by n segments (default 1).", run=True)
def _grow(c: DevConsole, a: List[str]) -> None:
    c.g.player.grow(int(_num(a[0])) if a else 1)


@cmd("shrink", "[n]", "Lose n segments (default 1).", run=True)
def _shrink(c: DevConsole, a: List[str]) -> None:
    c.g.player.shrink(int(_num(a[0])) if a else 1)


@cmd("length", "<n>", "Make the snake exactly n long (grows over the next steps).", run=True)
def _length(c: DevConsole, a: List[str]) -> None:
    p = c.g.player
    n = max(1, int(_num(a[0])))
    have = len(p.body) + p.grow_pending
    if n > have:
        p.grow(n - have)
    else:
        p.grow_pending = max(0, p.grow_pending - (have - n))
        p.shrink(max(0, len(p.body) - n))


@cmd("tp", "<x> <y>", "Teleport the whole snake so its head is at x y (the board is 32x22, origin top-left).", run=True)
def _tp(c: DevConsole, a: List[str]) -> None:
    if len(a) < 2:
        raise CmdError("need x and y")
    p = c.g.player
    x, y = _free_cell(c, a)
    hx, hy = p.head
    p.body = deque(((bx + x - hx) % GRID_W, (by + y - hy) % GRID_H) for bx, by in p.body)
    p.prev_body = list(p.body)
    c.ok(f"head at {p.head}")


@cmd("dir", "<up|down|left|right>", "Turn the snake.", run=True)
def _dir(c: DevConsole, a: List[str]) -> None:
    d = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    c.g.player.set_direction(d[_pick(a[0], list(d), "direction")])


@cmd("lives", "<n>", "Set Second Wind lives (Roguelite).", run=True)
def _lives(c: DevConsole, a: List[str]) -> None:
    c.g.perk_lives = max(0, int(_num(a[0])))
    c.ok(f"lives = {c.g.perk_lives}")


# ---------- time ----------

@cmd("timescale", "<x>", "Run the whole game at x speed (0.1 - 8). One grid step per frame is the ceiling.")
def _timescale(c: DevConsole, a: List[str]) -> None:
    c.time_scale = max(0.05, min(8.0, _num(a[0]))) if a else 1.0
    c.ok(f"time scale x{c.time_scale:g}")


@cmd("speed", "<x>", "Multiply the snake's move speed (0.2 - 5). 1 = normal.")
def _speed(c: DevConsole, a: List[str]) -> None:
    c.speed_mult = max(0.2, min(5.0, _num(a[0]))) if a else 1.0
    c.ok(f"speed x{c.speed_mult:g}")


@cmd("freeze", "[on|off]", "Freeze the game clock entirely; use `step` to advance one grid step at a time.")
def _freeze(c: DevConsole, a: List[str]) -> None:
    c.frozen = _bool(a[0] if a else None, c.frozen)
    c.ok(f"time {'FROZEN' if c.frozen else 'running'}")


@cmd("step", "[n]", "Advance n grid steps (default 1) of the run, e.g. while frozen.", run=True)
def _step(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if g.state != c.M.STATE_PLAYING:
        raise CmdError("only while playing")
    for _ in range(max(1, min(200, int(_num(a[0])) if a else 1))):
        if g.state == c.M.STATE_PLAYING and g.player_alive:
            g._tick()


@cmd("timer", "<seconds>", "Set the remaining time of a timed run.", run=True)
def _timer(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if g.time_remaining is None:
        raise CmdError("this mode has no timer")
    g.time_remaining = max(0.0, _num(a[0], g.time_remaining))
    c.ok(f"time left {g.time_remaining:.1f}s")


@cmd("keeplive", "[on|off]", "Keep the game running while the console is open (default: it pauses).")
def _keeplive(c: DevConsole, a: List[str]) -> None:
    c.pause_when_open = not _bool(a[0] if a else None, not c.pause_when_open)
    c.ok("game keeps running behind the console" if not c.pause_when_open else "game pauses while the console is open")


# ---------- items ----------

_FOODS = {"normal": FOOD_NORMAL, "golden": FOOD_GOLDEN, "speed": FOOD_SPEED}
_DOWNERUPS = {"bomb": DOWNERUP_BOMB, "curse": DOWNERUP_CURSE, "shrink": DOWNERUP_SHRINK, "mushroom": DOWNERUP_SHRINK}


def _spawn_names() -> List[str]:
    return list(_FOODS) + _powerup_kinds() + ["bomb", "curse", "mushroom", "lucky", "hunter", "rival"]


@cmd("give", "<powerup|all> [seconds]", "Activate a power-up on yourself right now, optionally with a custom duration.",
     run=True, args=lambda c: _powerup_kinds() + ["all"])
def _give(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if not a:
        raise CmdError("which power-up?")
    kinds = _powerup_kinds() if a[0].lower() == "all" else [_pick(a[0], _powerup_kinds(), "power-up")]
    for k in kinds:
        if k == "revive":
            continue
        g._activate_powerup(k)
        if len(a) > 1 and k in g.active_powerups:
            g.active_powerups[k] = float(a[1])
    c.ok("gave " + ", ".join(k for k in kinds if k != "revive"))


@cmd("spawn", "<thing> [x y]", "Spawn food (normal/golden/speed), a power-up, bomb/curse/mushroom, lucky, hunter or rival.",
     run=True, args=lambda c: _spawn_names())
def _spawn(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if not a:
        raise CmdError("spawn what?  " + ", ".join(_spawn_names()))
    what = _pick(a[0], _spawn_names(), "thing")
    x, y = _free_cell(c, a[1:])
    if what in _FOODS:
        g.foods.append(Food(x, y, _FOODS[what], temp=True))
    elif what in _DOWNERUPS:
        g.downerups.append(Downerup(x, y, _DOWNERUPS[what]))
    elif what == "lucky":
        g.luckyblocks.append(LuckyBlock(x, y))
    elif what == "hunter":
        g._spawn_hunter()
    elif what == "rival":
        g.rivals.append(EnemySnake(x, y))
    else:
        g.powerups.append(PowerUp(x, y, what, ttl=60.0))
    c.ok(f"spawned {what} at ({x}, {y})")


@cmd("lucky", "[effect|list]", "Trigger a Lucky Block effect on yourself (random if none given).", run=True,
     args=lambda c: [e for e, _ in LUCKY_EFFECTS] + ["list"])
def _lucky(c: DevConsole, a: List[str]) -> None:
    names = [e for e, _ in LUCKY_EFFECTS]
    if a and a[0] == "list":
        c.out("effects: " + ", ".join(names))
        return
    c.g._open_lucky_block(_pick(a[0], names, "effect") if a else None)


@cmd("portal", "", "Spawn a portal pair somewhere free.", run=True)
def _portal(c: DevConsole, a: List[str]) -> None:
    g = c.g
    first = random_free_cell(g.occupied_cells())
    second = random_free_cell(g.occupied_cells() | {first})
    g.portal_pair = (first, second)
    c.ok(f"portals at {first} and {second}")


@cmd("obstacle", "<x> <y> | clear", "Toggle a wall block at x y, or remove them all.", run=True)
def _obstacle(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if a and a[0] == "clear":
        g.obstacles.clear()
        g.temp_obstacles = set()
        c.ok("obstacles cleared")
        return
    if len(a) < 2:
        raise CmdError("need x and y")
    cell = _free_cell(c, a)
    if cell in g.obstacles:
        g.obstacles.discard(cell)
    elif cell not in g.player.body:
        g.obstacles.add(cell)
    c.ok(f"obstacle {'on' if cell in g.obstacles else 'off'} at {cell}")


# ---------- chaos ----------

@cmd("event", "<id|list|stop>", "Start a chaos event now (frenzy, gold_rush, blackout, mirror, hunter, quake).", run=True,
     args=lambda c: list(EVENTS) + ["list", "stop"])
def _event(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if not a or a[0] == "list":
        c.out("events: " + ", ".join(f"{k} ({v.duration:.0f}s)" for k, v in EVENTS.items()))
        return
    d = g.event_director
    if d is None:
        d = g.event_director = EventDirector(random.Random())
        d.countdown = 1e9  # only what you start from the console, no random ones on top
    if a[0] == "stop":
        if d.active:
            g._on_event("end", d.active)
            d.active = None
            d.countdown = 1e9
        c.ok("event stopped")
        return
    eid = _pick(a[0], list(EVENTS), "event")
    if d.active:
        g._on_event("end", d.active)
    d.active, d.remaining, d.incoming = eid, EVENTS[eid].duration, None
    g._on_event("start", eid)
    c.ok(f"event {eid}")


@cmd("hazard", "<id|list|stop>", "Fire a Hardcore hazard (meteor, shower, tremor, surge, rockfall).", run=True,
     args=lambda c: list(HAZARDS) + ["list", "stop"])
def _hazard(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if not a or a[0] == "list":
        c.out("hazards: " + ", ".join(f"{k} ({v.duration:.0f}s)" for k, v in HAZARDS.items()))
        return
    if a[0] == "stop":
        for hid in HAZARDS:
            g._on_hazard("end", hid)
        g.meteors.clear()
        g.pending_meteors.clear()
        c.timers.clear()
        c.ok("hazards stopped")
        return
    hid = _pick(a[0], list(HAZARDS), "hazard")
    g._on_hazard("start", hid)
    c.later(HAZARDS[hid].duration, lambda: g._on_hazard("end", hid))
    c.ok(f"hazard {hid}")


@cmd("meteor", "[x y]", "Drop a meteor (with its warning) at x y, or on you.", run=True)
def _meteor(c: DevConsole, a: List[str]) -> None:
    g = c.g
    x, y = _free_cell(c, a) if len(a) >= 2 else g.player.head
    g.meteors.append([x, y, c.M.METEOR_WARN_SECONDS])


@cmd("perk", "<id|list|all|clear>", "Take a Roguelite perk (stackable) right now.", run=True,
     args=lambda c: list(PERKS) + ["list", "all", "clear"])
def _perk(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if not a or a[0] == "list":
        for p in PERKS.values():
            c.out(f"  {p.id}: {p.name}  (have {g.perks.get(p.id, 0)})")
        return
    if a[0] == "clear":
        g.perks.clear()
        g.perk_lives = 0
        c.ok("perks cleared")
        return
    ids = list(PERKS) if a[0] == "all" else [_pick(a[0], list(PERKS), "perk")]
    for pid in ids:
        g.perk_choices = [pid]
        g._choose_perk(0)
    g.resume_countdown = 0.0
    g.state = c.M.STATE_PLAYING if g.state == c.M.STATE_PERK_PICK else g.state
    c.ok("took " + ", ".join(ids))


# ---------- progress ----------

@cmd("ach", "<list [filter]|unlock <id|all>|lock <id|all>>", "List, unlock or re-lock achievements.",
     args=lambda c: ["list", "unlock", "lock"])
def _ach(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if not a or a[0] == "list":
        flt = a[1].lower() if len(a) > 1 else ""
        for ach in ACHIEVEMENTS:
            if flt in ach.id or flt in ach.name.lower():
                mark = "x" if ach.id in g.tracker.unlocked else " "
                c.out(f"  [{mark}] {ach.id}: {ach.name} - {ach.description}", OK if mark == "x" else TEXT)
        c.out(f"{len(g.tracker.unlocked)}/{len(ACHIEVEMENTS)} unlocked", DIM)
        return
    verb = _pick(a[0], ["unlock", "lock", "list"], "action")
    if len(a) < 2:
        raise CmdError("which id (or all)?")
    ids = [x.id for x in ACHIEVEMENTS] if a[1] == "all" else [_pick(a[1], list(ACHIEVEMENTS_BY_ID), "achievement")]
    if verb == "unlock":
        if len(ids) == 1:
            g._unlock(ids[0])
        else:
            g.tracker.unlocked.update(ids)
    else:
        g.tracker.unlocked.difference_update(ids)
    g.data["achievements"] = sorted(g.tracker.unlocked)
    persistence.save(g.data)
    c.ok(f"{verb}ed {len(ids)}")


@cmd("arcade", "<unlock|lock|best <mode> <value>|clearbest>", "Arcade shop unlock and best scores.",
     args=lambda c: ["unlock", "lock", "best", "clearbest"])
def _arcade(c: DevConsole, a: List[str]) -> None:
    g = c.g
    verb = _pick(a[0], ["unlock", "lock", "best", "clearbest"], "action") if a else "unlock"
    if verb == "best":
        if len(a) < 3:
            raise CmdError("arcade best <mode> <value>")
        g.arcade_best[_pick(a[1], list(ARCADE_MODES), "arcade mode")] = float(a[2])
    elif verb == "clearbest":
        g.arcade_best.clear()
    else:
        g.arcade_unlocked = verb == "unlock"
    g.save_wallet()
    c.ok(f"arcade {verb}: unlocked={g.arcade_unlocked} best={g.arcade_best}")


@cmd("skin", "<name|list|all>", "Own and equip a snake skin.", args=lambda c: list(SNAKE_SKINS) + ["all", "list"])
def _skin(c: DevConsole, a: List[str]) -> None:
    g = c.g
    names = list(SNAKE_SKINS)
    if not a or a[0] == "list":
        c.out("skins: " + ", ".join(f"{n}{'*' if n in g.owned_skins else ''}" for n in names))
        return
    if a[0] == "all":
        g.owned_skins.update(names)
        c.ok("all skins owned")
    else:
        name = _pick(a[0], names, "skin")
        g.owned_skins.add(name)
        g.skin_idx = names.index(name)
        c.ok(f"wearing {name}")
    g.save_wallet()


@cmd("trail", "<name|list|all>", "Own and equip a trail effect.", args=lambda c: list(TRAIL_EFFECTS) + ["all", "list"])
def _trail(c: DevConsole, a: List[str]) -> None:
    g = c.g
    names = list(TRAIL_EFFECTS)
    if not a or a[0] == "list":
        c.out("trails: " + ", ".join(f"{n}{'*' if n in g.owned_trails else ''}" for n in names))
        return
    if a[0] == "all":
        g.owned_trails.update(names)
        c.ok("all trails owned")
    else:
        name = _pick(a[0], names, "trail")
        g.owned_trails.add(name)
        g.equipped_trail = name
        c.ok(f"equipped {name}")
    g.save_wallet()


@cmd("streak", "<days>", "Set your daily-play streak.")
def _streak(c: DevConsole, a: List[str]) -> None:
    import datetime
    g = c.g
    n = max(0, int(_num(a[0])))
    g.data["streak"] = {"count": n, "last_played": datetime.date.today().isoformat()}
    g.streak_count = n
    persistence.save(g.data)
    c.ok(f"streak = {n}")


@cmd("quest", "complete", "Mark all of today's daily quests done (no reward paid).")
def _quest(c: DevConsole, a: List[str]) -> None:
    import datetime
    from quests import quests_for_date
    g = c.g
    today = datetime.date.today().isoformat()
    state = persistence.quest_state_for_today(g.data, today)
    for q in quests_for_date(today):
        if q.id not in state["completed"]:
            state["completed"].append(q.id)
    persistence.save(g.data)
    c.ok("today's quests marked complete")


@cmd("resetsave", "confirm", "Delete the DEV save file and ghosts (this build's folder only), then quit.")
def _resetsave(c: DevConsole, a: List[str]) -> None:
    if a != ["confirm"]:
        raise CmdError(f"this deletes {persistence.SAVE_DIR}; type `resetsave confirm`")
    for f in (persistence.SAVE_FILE, persistence.GHOST_FILE):
        try:
            f.unlink()
        except FileNotFoundError:
            pass
    c.ok("deleted. Quitting so nothing re-saves it...")
    pygame.quit()
    sys.exit(0)


# ---------- settings & fx ----------

@cmd("set", "<setting> <value>", "Change a setting (no args: list them). Same values as the Settings screen.",
     args=lambda c: [d.key for d in SETTING_DEFS])
def _set(c: DevConsole, a: List[str]) -> None:
    g = c.g
    if not a:
        for d in SETTING_DEFS:
            c.out(f"  {d.key} = {g.setting_get(d.key)}   ({d.kind}{', ' + '/'.join(d.options) if d.options else ''})")
        return
    d = next(x for x in SETTING_DEFS if x.key == _pick(a[0], [x.key for x in SETTING_DEFS], "setting"))
    cur = g.setting_get(d.key)
    val = a[1] if len(a) > 1 else None
    if d.kind == "toggle":
        new = _bool(val, bool(cur))
    elif d.kind == "slider":
        if val is None:
            raise CmdError(f"{d.key} is {cur} ({d.lo}-{d.hi})")
        new = max(d.lo, min(d.hi, int(_num(val, cur))))
    else:
        if val is None:
            raise CmdError(f"{d.key} is {cur} ({'/'.join(d.options)})")
        new = _pick(val, list(d.options), "option")
    g.setting_set(d.key, new)
    c.ok(f"{d.key} = {new}")


@cmd("get", "<setting>", "Show a setting's value.", args=lambda c: [d.key for d in SETTING_DEFS])
def _get(c: DevConsole, a: List[str]) -> None:
    key = _pick(a[0], [d.key for d in SETTING_DEFS], "setting")
    c.out(f"{key} = {c.g.setting_get(key)}")


def _sound_names(c: DevConsole) -> List[str]:
    return sorted(n for n, v in vars(c.g.sounds).items() if isinstance(v, pygame.mixer.Sound))


@cmd("sound", "<name|list>", "Play any game sound effect.", args=lambda c: _sound_names(c) + ["list"])
def _sound(c: DevConsole, a: List[str]) -> None:
    names = _sound_names(c)
    if not a or a[0] == "list":
        c.out("sounds: " + ", ".join(names))
        return
    c.g.sounds.play(getattr(c.g.sounds, _pick(a[0], names, "sound")))


@cmd("shake", "[strength]", "Screen shake.")
def _shake(c: DevConsole, a: List[str]) -> None:
    c.g.shake(0.5, _num(a[0]) if a else 8)


@cmd("announce", "<text>", "Show a big on-screen callout.")
def _announce(c: DevConsole, a: List[str]) -> None:
    c.g._announce(" ".join(a) or "TEST", WARN, life=1.5)


@cmd("toast", "<text>", "Show an achievement-style toast.")
def _toast(c: DevConsole, a: List[str]) -> None:
    g = c.g
    entry = ("Dev toast", " ".join(a) or "hello", 3.0)
    if g.state in (c.M.STATE_PLAYING, c.M.STATE_PAUSED):
        g.toast_queue.append(entry)
    else:
        g.ui_toasts.append(list(entry))


@cmd("seed", "<n>", "Seed Python's random generator (repeatable spawns).")
def _seed(c: DevConsole, a: List[str]) -> None:
    random.seed(int(_num(a[0])) if a else None)
    c.ok("seeded")
