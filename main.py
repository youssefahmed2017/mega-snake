"""MEGA SNAKE: classic Snake with an absurd number of extra features.

Modes: Classic (wrap), Walls (deadly edges), Maze (obstacles), Battle (2 AI rivals),
Timed (60s attack), Hardcore (no power-ups, faster ramp), Coop (local 2-player),
Daily (seeded layout, separate leaderboard).

Features: power-ups (ghost/magnet/shield/slowmo/2x/freeze/teleport), portals, curse
food, combo scoring, particles, screen shake, procedurally synthesized sound, skins
unlockable via achievements, settings/stats/changelog screens, itemized score
breakdown, persistent per-mode leaderboard.
"""
from __future__ import annotations

import datetime
import math
import os
import textwrap
import random
import sys
import tempfile
from pathlib import Path
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np
import pygame

import colorsys

from constants import (
    CELL_SIZE, GRID_W, GRID_H, SIDEBAR_W, SCREEN_W, SCREEN_H, BOARD_Y, FPS, BASE_MOVE_INTERVAL,
    BG, GRID_LINE, SIDEBAR_BG, TEXT, TEXT_DIM, ACCENT, DANGER, GOLD, GREEN, PURPLE,
    SNAKE_SKINS, SKIN_UNLOCK_REQUIREMENT, P2_COLOR, PLAYER_COLORS, PLAYER_LABELS, MAX_PLAYERS,
    TRAIL_EFFECTS, TRAIL_NAMES,
    FOOD_NORMAL, FOOD_GOLDEN, FOOD_SPEED, FOOD_SHRINK, FOOD_COLORS,
    DOWNERUP_BOMB, DOWNERUP_CURSE, DOWNERUP_COLORS, COLORBLIND_DOWNERUP_COLORS,
    POWERUP_GHOST, POWERUP_MAGNET, POWERUP_SHIELD, POWERUP_SLOWMO, POWERUP_MULT,
    POWERUP_FREEZE, POWERUP_TELEPORT, POWERUP_REVIVE, POWERUP_COLORS, POWERUP_DURATIONS, CURSE_DURATION,
    PORTAL_A, PORTAL_B, MODES, MODE_CONFIG, MODE_DESC, DIFFICULTIES, DIFFICULTY_SPEED_MULT,
    GAME_VERSION, CHANGELOG, COLORBLIND_FOOD_COLORS, COLORBLIND_POWERUP_COLORS, GHOST_MAX_TICKS,
    LAN_RULESETS, LAN_RULESET_NAMES, MAPS, MAP_NAMES, MAP_THEMES, DEFAULT_THEME,
    EASTER_EXTRA_PRESSES, EASTER_WARNINGS, SECRET_SHOP_ITEMS, ONLINE_SERVER_URL,
)
from snake import PlayerSnake
from enemy import EnemySnake
from food import (
    Food, PowerUp, Downerup, spawn_food, maybe_spawn_powerup, maybe_spawn_downerup,
    maybe_spawn_portal_pair, random_free_cell,
)
from particles import ParticleSystem
from achievements import ACHIEVEMENTS, ACHIEVEMENTS_BY_ID, AchievementTracker
from audio import SoundBank
import persistence
import network
import updater
from quests import quests_for_date
import gfx
import ui
from art import Art
from ui import Hot
from settings_defs import (SETTING_DEFS, SETTING_BY_KEY, SETTING_TABS, SETTING_DEFAULTS, PARTICLE_DENSITY,
                           STICK_ENGAGE, SettingDef)

os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")  # smooth, not blocky, when the OS upscales
pygame.init()
from pygame._sdl2 import controller as sdl_controller
sdl_controller.init()
pygame.display.set_caption("MEGA SNAKE")
clock = pygame.time.Clock()

# Render resolution presets (window size). The 1028x528 logical canvas is fitted
# inside, keeping its aspect ratio, and every drawing call is scaled to match - see gfx.py.
RESOLUTIONS = {"144p": (256, 144), "360p": (640, 360), "480p": (854, 480),
               "720p": (1280, 720), "1080p": (1920, 1080), "4K": (3840, 2160)}
display: pygame.Surface  # the real window
screen: gfx.HSurface     # the logical canvas everything draws onto
canvas_offset = (0, 0)


def apply_display(resolution: str, fullscreen: bool) -> None:
    """(Re)create the window at a preset and rebuild the canvas and fonts for it."""
    global display, screen, canvas_offset
    w, h = RESOLUTIONS.get(resolution, RESOLUTIONS["1080p"])
    gfx.set_scale(min(w / SCREEN_W, h / SCREEN_H))  # also rebuilds every gfx.Font
    flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
    try:
        display = pygame.display.set_mode((w, h), flags)
    except pygame.error:
        display = pygame.display.set_mode((w, h))
    screen = gfx.surface((SCREEN_W, SCREEN_H))
    cw, ch = pygame.Surface.get_size(screen)
    canvas_offset = ((w - cw) // 2, (h - ch) // 2)
    gfx.set_offset(canvas_offset)


def _font_file(name: str) -> Optional[str]:
    path = gfx.asset_path(f"assets/fonts/{name}")
    return path if os.path.exists(path) else None  # None = pygame's built-in font


_HEAD_FONT = _font_file("LilitaOne-Regular.ttf")    # chunky cartoon display face
_BODY_FONT = _font_file("VarelaRound-Regular.ttf")  # soft, readable small text
font_big = gfx.Font(_HEAD_FONT, 42)
font_mid = gfx.Font(_HEAD_FONT, 25)
font_small = gfx.Font(_BODY_FONT, 17)
font_tiny = gfx.Font(_BODY_FONT, 14)
font_chat = gfx.Font(_BODY_FONT, 17)
font_title = gfx.Font(_BODY_FONT, 50)

_boot_settings = persistence.load()["settings"]
apply_display(_boot_settings.get("resolution", "1080p"), bool(_boot_settings.get("fullscreen", True)))

art = Art(gfx.asset_path("assets/art"))  # needs the display, so after apply_display

_icon_font_cache: Dict[int, gfx.Font] = {}


def _icon_font(size: int) -> gfx.Font:
    """A tiny bold font for glyphs drawn *inside* an icon (just the Mult
    power-up's "x2"), sized to whatever radius that icon happens to be
    drawn at (board cell vs. a small HUD/legend dot) - cached since icons
    redraw every frame."""
    f = _icon_font_cache.get(size)
    if f is None:
        f = gfx.Font(_HEAD_FONT, size)
        _icon_font_cache[size] = f
    return f


SKIN_NAMES = list(SNAKE_SKINS.keys())

PTAGS = ["p1", "p2", "p3", "p4"]  # self.players index <-> network/UI tag
SLOT_LABEL = {"host": "P1", "p2": "P2", "p3": "P3", "p4": "P4"}  # network slot <-> chat/roster label

STATE_MENU = "menu"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"
STATE_GAME_OVER = "game_over"
STATE_LEADERBOARD = "leaderboard"
STATE_ACHIEVEMENTS = "achievements"
STATE_SETTINGS = "settings"
STATE_STATS = "stats"
STATE_CHANGELOG = "changelog"
STATE_SHOP = "shop"
STATE_ENTER_INITIALS = "enter_initials"
STATE_LAN_MENU = "lan_menu"
STATE_LAN_SETUP = "lan_setup"
STATE_MAP_SELECT = "map_select"
STATE_LAN_HOST_WAIT = "lan_host_wait"
STATE_LAN_JOIN_IP = "lan_join_ip"
STATE_LAN_CONNECTING = "lan_connecting"
STATE_LAN_ERROR = "lan_error"
STATE_ONLINE_JOIN_CODE = "online_join_code"
STATE_HOWTO = "howto"
STATE_QUESTS = "quests"
STATE_UPDATE_CHECK = "update_check"
STATE_UPDATE_PROMPT = "update_prompt"
STATE_UPDATE_NONE = "update_none"
STATE_UPDATE_DOWNLOAD = "update_download"
STATE_UPDATE_ERROR = "update_error"
STATE_EASTER_WARNING = "easter_warning"
STATE_SECRET_SHOP = "secret_shop"

# After the run-ending death, the board stays up this long (frozen, with the
# screen shake and death particles playing) before the Game Over screen.
DEATH_PAUSE_SECONDS = 0.9

# Floating "+10"/"-5" popups at the pickup tile, and the tail's grow-in pop.
SCORE_POPUP_DURATION = 0.8
SCORE_POPUP_RISE = 26  # pixels drifted upward over the popup's lifetime
TAIL_GROW_POP_DURATION = 0.16
TURN_SQUASH_DURATION = 0.14
BLINK_PERIOD = 3.2       # how often the head eye blinks
BLINK_HOLD = 0.12        # how long the blink stays closed
TONGUE_PERIOD = 4.0      # how often the tongue flicks out
TONGUE_HOLD = 0.18

# Near misses: head ends up next to something lethal but survives. Rewards
# skillful close play instead of only ever reacting to actual death.
NEAR_MISS_COOLDOWN = 1.2      # don't re-trigger while hugging the same wall/tail
NEAR_MISS_FLASH_DURATION = 0.3
NEAR_MISS_HITSTOP = 0.1       # real seconds the brief slowdown lasts
NEAR_MISS_HITSTOP_FACTOR = 0.25  # how slow the game runs during it

# The death pause (board frozen before Game Over) ramps down to near-stopped
# instead of just holding the last frame - the fatal moment stretches out
# instead of simply cutting off.
DEATH_SLOWMO_RAMP = 0.3
DEATH_SLOWMO_FLOOR = 0.15

# In-match chat (LAN/online only, available from the Paused screen so
# nobody's snake is ever moving while someone types - see handle_pause_key).
CHAT_MAX_LEN = 200
CHAT_MAX_LOG = 50
CHAT_VISIBLE = 6
CHAT_COOLDOWN = 0.35

# While paused, neither side sent any traffic at all before chat existed -
# nothing needed to. Some Wi-Fi drivers power-save a radio that's gone quiet,
# and some routers drop an idle NAT mapping, either of which silently kills
# the TCP connection; the game then only notices (and shows "disconnected")
# once something finally touches the dead socket. A small periodic heartbeat
# keeps real traffic flowing so that never has the chance to happen.
LAN_HEARTBEAT_SECONDS = 4.0

# Full game state is replaceable, so cap uploads instead of sending on every
# render frame or every simulation tick. Inputs and control messages stay immediate.
NETWORK_SNAPSHOT_INTERVAL = 0.1

# How long each side waits for the other to confirm its version before just
# proceeding anyway (see _lan_host_poll / _lan_connecting_poll). Failing open
# rather than hanging forever matters for an old peer that predates this
# handshake entirely and will never send its half of it.
LAN_HANDSHAKE_TIMEOUT = 3.0


def _clean_chat_text(text: str) -> str:
    """Printable ASCII only, deliberately - see font_chat's comment for why.
    This is temporary: dropping emoji/Unicode support rules out font/glyph
    coverage as the cause of chat being invisible on macOS. A lone UTF-16
    surrogate (a known SDL/Windows emoji-picker bug - see git history) would
    crash rendering with an uncaught UnicodeEncodeError if it ever got
    through, but printable-ASCII-only already can't admit one regardless."""
    return "".join(ch for ch in text if 32 <= ord(ch) < 127)


# How long each cell of a shop trail lingers behind the tail before fading out.
TRAIL_LIFE = 0.7

POWERUP_SPRITES = {
    POWERUP_GHOST: "pu_ghost", POWERUP_MAGNET: "pu_magnet", POWERUP_SHIELD: "pu_shield",
    POWERUP_SLOWMO: "pu_slowmo", POWERUP_MULT: "pu_mult", POWERUP_FREEZE: "pu_freeze",
    POWERUP_TELEPORT: "pu_teleport", POWERUP_REVIVE: "pu_revive",
}

MENU_ITEMS = [
    "Start Game", "Mode", "Skin", "Multiplayer", "Daily Quests", "Shop", "Settings",
    "How to Play", "Stats", "Leaderboard", "Achievements", "Changelog", "Check for Updates", "Quit",
]
PAUSE_ITEMS = ["Resume", "Restart", "Settings", "Main Menu"]
LAN_HOST_PAUSE_ITEMS = ["Resume", "Settings", "End Session"]
LAN_MENU_ITEMS = ["Host LAN Game", "Join LAN Game", "Host Online Game", "Join Online Game", "Back"]
LAN_SETUP_ITEMS = ["Ruleset", "Map", "Start Hosting"]
MAP_SETUP_ITEMS = ["Map", "Start Game"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def grid_to_px(x: float, y: float) -> Tuple[float, float]:
    return x * CELL_SIZE, y * CELL_SIZE


def clamp_color(c: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return tuple(max(0, min(255, int(v))) for v in c)


FADE_SECONDS = 0.32  # dip-to-dark length when the screen changes (fade out, then fade in)
FADE_OUT_SHARE = 0.42  # how much of it is the old screen going dark


class Game:
    _state = None
    _fade_from = None   # snapshot of the previous screen, fading out over the new one
    _fade_t = 0.0
    _fade_black = None

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, new: str) -> None:
        """Every screen change goes through here, so every change can crossfade. Pausing and
        resuming stay instant: they happen mid-run and a fade there would feel laggy."""
        old = self._state
        self._state = new
        if (old is not None and old != new and STATE_PAUSED not in (old, new)
                and getattr(self, "settings", {}).get("transitions", True)):
            self._fade_from = screen.copy()  # still the last frame that was drawn
            self._fade_t = FADE_SECONDS

    def __init__(self) -> None:
        self.data = persistence.load()
        self.tracker = AchievementTracker(self.data.get("achievements", []))
        self.sounds = SoundBank()
        self.particles = ParticleSystem()
        self.pad_active = False  # last real input came from a pad (drives footer hints)
        self._pads: dict = {}  # device index -> open sdl_controller.Controller (must stay open to get events)
        self._stick_dir = {pygame.CONTROLLER_AXIS_LEFTX: 0, pygame.CONTROLLER_AXIS_LEFTY: 0}
        for i in range(sdl_controller.get_count()):
            self._open_pad(i)

        settings = self.data["settings"]
        self.settings: Dict[str, object] = dict(SETTING_DEFAULTS)
        self.settings.update({k: v for k, v in settings.items() if k in SETTING_DEFAULTS})
        self.sounds.master_volume = settings.get("volume", 100) / 100
        self.sounds.muted = settings.get("muted", False)
        self.sounds.ui_sounds = bool(self.settings["ui_sounds"])
        self.difficulty = settings.get("difficulty", "Normal")
        self.screen_shake_enabled = settings.get("screen_shake", True)
        self.colorblind = settings.get("colorblind", False)
        self.particles.density = PARTICLE_DENSITY.get(self.settings["particles"], 1.0)

        # Mouse layer: hotspots are re-registered by every draw_* each frame.
        self.hotspots: List[Hot] = []
        self.drag_hot: Optional[Hot] = None
        self._cursor_hidden = False
        self.cursor = ui.SnakeCursor()
        self.settings_tab = 0
        self.ach_filter = 0
        self.ach_scroll = 0.0
        self.ui_toasts: List[list] = []
        self.run_new_achievements: List[str] = []

        self.ghosts = persistence.load_ghosts()
        self.announcer_queue: List[list] = []  # [text, color, life, max_life]
        self._vignette_cache: Dict[Tuple[int, bool], pygame.Surface] = {}
        self._bg_cache: dict = {}
        self._floor_cache: dict = {}
        self.run_quest_rewards: List[Tuple[str, int]] = []

        self.wallet = self.data.get("wallet", 0)
        self.owned_trails = set(self.data.get("owned_trails", ["None"]))
        self.equipped_trail = self.data.get("equipped_trail", "None")

        self.state = STATE_MENU
        self.prev_state = STATE_MENU  # where Settings/Pause should return to
        self.menu_index = 0
        self.pause_index = 0
        self.settings_index = 0
        self.shop_index = 0
        self.mode_idx = 0
        self.skin_idx = 0

        self.toast_queue: List[Tuple[str, str, float]] = []
        self.game_over_reason = ""
        self.final_stats: dict = {}
        self.run_coins_earned = 0
        self.run_streak_bonus = 0
        self.streak_count = self.data.get("streak", {}).get("count", 0)

        self.pending_initials = ["A", "A", "A"]
        self.initials_cursor = 0
        self.pending_score_entry: Optional[dict] = None

        # LAN multiplayer: no external/cloud server, one player's instance hosts
        # a plain TCP socket on the local network, the other connects by IP.
        self.lan_role: Optional[str] = None  # None | "host" | "client"
        self.lan_host: Optional[network.Host] = None
        self.lan_client: Optional[network.Client] = None
        self.lan_link: Optional[network.LineSocket] = None
        self.lan_menu_index = 0
        self.lan_setup_index = 0
        self.lan_ruleset_idx = LAN_RULESET_NAMES.index("Walls")
        self.map_idx = 0
        self.lan_ruleset_name = LAN_RULESET_NAMES[self.lan_ruleset_idx]
        self.map_name = MAP_NAMES[self.map_idx]
        self.lan_cfg_override: Optional[dict] = None
        self.lan_ip_input = ""
        self.lan_error_msg = ""
        # Online multiplayer reuses every lan_* field above: the only
        # difference is the transport (network.Online* via the relay).
        self.lan_online = False
        self.online_code_input = ""
        self.snapshot_accum = 0.0
        self.snapshot_seq = 0
        self.last_snapshot_seq = -1
        self.snapshot_age = NETWORK_SNAPSHOT_INTERVAL
        self.match_meta_sent = False

        self.chat_active = False
        self.chat_input = ""
        self.chat_log: List[Tuple[str, str]] = []  # [(who, text)], "You" or "Friend"
        self.chat_unread = 0
        # -inf, not 0.0: get_ticks() is process uptime, so a 0.0 baseline would
        # wrongly rate-limit a message sent within the first CHAT_COOLDOWN
        # seconds of the game launching.
        self.chat_last_sent = float("-inf")
        # Client only: T while Playing asks the host to pause (the client has
        # no pause authority of its own); this remembers to open chat once
        # that pause actually comes back, instead of needing a second T press.
        self.chat_pending_open = False
        self.lan_heartbeat_last = 0.0
        # Held between "TCP connected" and "confirmed a compatible version" -
        # see _lan_host_poll / _lan_connecting_poll. Mismatched LAN versions
        # used to connect anyway and then behave inexplicably differently on
        # each side (e.g. one side missing newer features entirely); now it's
        # caught with a clear message instead.
        self.lan_pending_link: Optional[network.LineSocket] = None
        self.lan_handshake_deadline = 0.0
        self.lan_connect_label = ""
        # Host-side lobby bookkeeping: slot -> deadline for its version check
        # (LAN only), and which slots were in the match when it started (to
        # notice one vanishing later without an explicit "they left" message
        # - see _lan_sync_roster).
        self.lan_unverified: Dict[str, float] = {}
        self.lan_known_slots: set = set()
        self.lan_toast = ""
        self.lan_toast_until = 0.0
        self.map_setup_index = 0
        self.theme = dict(DEFAULT_THEME)
        self.ambient_particles: List[list] = []  # [x, y, vx, vy, life, max_life, radius]
        self._ambient_spawn_accum = 0.0
        self.local_ip: Optional[str] = None

        self.easter_down_count = 0
        self.easter_streak_start = 0
        self.easter_stage = 0
        self.secret_shop_toast_until = 0

        # Auto-updater: checks GitHub Releases on a background thread so the
        # UI never blocks. The startup check is silent on "no update" or a
        # network error (most launches, most of the time) - only a manual
        # "Check for Updates" from the menu reports those explicitly.
        self.update_checker: Optional[updater.UpdateChecker] = None
        self.update_downloader: Optional[updater.Downloader] = None
        self.update_releases: List[updater.Release] = []
        self.update_choice_index = 0  # 0 = Yes, 1 = No
        self.update_error_msg = ""
        self.update_check_silent = True
        self.update_check_anim = 0.0
        self.prev_state_before_update = STATE_MENU

        self.reset_run()
        failed_update = self._consume_pending_update()
        if failed_update:
            # The last update relaunched this same old version. Offering it
            # again would just loop forever, so explain instead.
            self.update_error_msg = failed_update
            self.state = STATE_UPDATE_ERROR
        else:
            self.update_checker = updater.UpdateChecker(GAME_VERSION)
            self.state = STATE_UPDATE_CHECK

    # ---------- helpers ----------

    def mode_name(self) -> str:
        return MODES[self.mode_idx]

    def mode_cfg(self) -> dict:
        base = MODE_CONFIG[self.mode_name()]
        if self.lan_cfg_override:
            merged = dict(base)
            merged.update(self.lan_cfg_override)
            return merged
        return base

    def _center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        return cell[0] + 0.5, cell[1] + 0.5

    def _rumble(self, low: float, high: float, ms: int) -> None:
        """Vibrate connected pads (low = heavy motor, high = light). Only while a pad is the active input."""
        if not (self.pad_active and self.settings["rumble"]):
            return
        k = int(self.settings["rumble_strength"]) / 100
        for c in self._pads.values():
            try:
                c.rumble(low * k, high * k, ms)
            except pygame.error:
                pass

    def shake(self, duration: float, magnitude: float) -> None:
        if self.screen_shake_enabled:
            self.particles.shake(duration, magnitude * int(self.settings["shake_strength"]) / 100)

    def cycle_skin(self, direction: int) -> None:
        n = len(SKIN_NAMES)
        idx = self.skin_idx
        for _ in range(n):
            idx = (idx + direction) % n
            name = SKIN_NAMES[idx]
            req = SKIN_UNLOCK_REQUIREMENT[name]
            if req is None or req in self.tracker.unlocked:
                self.skin_idx = idx
                return

    # Five settings predate the settings table and live as plain attributes that
    # the rest of the game (and the M key) reads and writes directly; everything
    # else lives in self.settings. These two methods hide that split.
    def setting_get(self, key: str):
        if key == "volume":
            return round(self.sounds.master_volume * 100)
        if key == "muted":
            return self.sounds.muted
        if key == "difficulty":
            return self.difficulty
        if key == "screen_shake":
            return self.screen_shake_enabled
        if key == "colorblind":
            return self.colorblind
        return self.settings[key]

    def setting_set(self, key: str, value, save: bool = True) -> None:
        if key == "volume":
            self.sounds.master_volume = value / 100
        elif key == "muted":
            self.sounds.muted = value
        elif key == "difficulty":
            self.difficulty = value
        elif key == "screen_shake":
            self.screen_shake_enabled = value
        elif key == "colorblind":
            self.colorblind = value
        else:
            self.settings[key] = value
            if key == "ui_sounds":
                self.sounds.ui_sounds = value
            elif key == "particles":
                self.particles.density = PARTICLE_DENSITY.get(value, 1.0)
            elif key in ("fullscreen", "resolution"):
                self._apply_display()
        self._unlock("tinkerer")
        if save:
            self.save_settings()

    def setting_step(self, d: SettingDef, direction: int) -> None:
        cur = self.setting_get(d.key)
        if d.kind == "toggle":
            new = not cur
        elif d.kind == "choice":
            new = d.options[(d.options.index(cur) + direction) % len(d.options)]
        else:
            new = max(d.lo, min(d.hi, cur + direction * d.step))
        if new != cur:
            self.setting_set(d.key, new)

    def _apply_display(self) -> None:
        apply_display(str(self.settings["resolution"]), bool(self.settings["fullscreen"]))
        # Anything cached at the old pixel density would be resampled every frame.
        self._fade_from = None
        self._vignette_cache.clear()
        self._bg_cache.clear()
        self._floor_cache.clear()
        _icon_font_cache.clear()
        art.clear()

    def save_settings(self) -> None:
        saved = dict(self.settings)
        for key in ("volume", "muted", "difficulty", "screen_shake", "colorblind"):
            saved[key] = self.setting_get(key)
        self.data["settings"] = saved
        persistence.save(self.data)

    def _unlock(self, ach_id: str) -> None:
        """Unlock an achievement that's triggered by an event rather than by run
        stats (shop purchases, settings changes, ...). No-op if already earned."""
        if ach_id in self.tracker.unlocked:
            return
        ach = ACHIEVEMENTS_BY_ID[ach_id]
        self.tracker.unlocked.add(ach_id)
        self.data["achievements"] = sorted(self.tracker.unlocked)
        persistence.save(self.data)
        self.sounds.play(self.sounds.achievement)
        toast = ["Achievement Unlocked!", ach.name, 3.0]
        if self.state in (STATE_PLAYING, STATE_PAUSED):
            self.toast_queue.append(tuple(toast))
        else:
            self.ui_toasts.append(toast)

    def food_color(self, kind: str) -> Tuple[int, int, int]:
        return (COLORBLIND_FOOD_COLORS if self.colorblind else FOOD_COLORS)[kind]

    def powerup_color(self, kind: str) -> Tuple[int, int, int]:
        return (COLORBLIND_POWERUP_COLORS if self.colorblind else POWERUP_COLORS)[kind]

    def downerup_color(self, kind: str) -> Tuple[int, int, int]:
        return (COLORBLIND_DOWNERUP_COLORS if self.colorblind else DOWNERUP_COLORS)[kind]

    def _quest_progress(self) -> Tuple[int, int]:
        today_iso = datetime.date.today().isoformat()
        todays = quests_for_date(today_iso)
        q = self.data.get("quests", {})
        completed = q.get("completed", []) if q.get("date") == today_iso else []
        return sum(1 for quest in todays if quest.id in completed), len(todays)

    def _announce(self, text: str, color: Tuple[int, int, int] = GOLD, life: float = 1.3) -> None:
        # Keep at most two callouts stacked so a burst of events stays readable.
        if not self.settings["callouts"]:
            return
        self.announcer_queue.append([text, color, life, life])
        del self.announcer_queue[:-2]

    def _spawn_score_popup(self, px: float, py: float, text: str, color: Tuple[int, int, int],
                            big: bool = False) -> None:
        """A '+10'/'-5' that drifts up from the pickup and fades, so a score
        change lands as something you *saw happen* at that exact tile, not
        just a number that changed in the sidebar a moment later."""
        self.score_popups.append([px, py, text, color, 0.0, big])

    def save_wallet(self) -> None:
        self.data["wallet"] = self.wallet
        self.data["owned_trails"] = sorted(self.owned_trails)
        self.data["equipped_trail"] = self.equipped_trail
        persistence.save(self.data)

    def trail_color(self, t: float, offset: float = 0.0) -> Optional[Tuple[int, int, int]]:
        spec = TRAIL_EFFECTS[self.equipped_trail]["color"]
        if spec is None:
            return None
        if spec == "rainbow":
            hue = (t * 0.3 + offset) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
            return int(r * 255), int(g * 255), int(b * 255)
        return spec

    # ---------- auto-updater ----------

    def _start_update_check(self, silent: bool) -> None:
        self.update_check_silent = silent
        self.update_check_anim = 0.0
        self.update_error_msg = ""
        self.update_checker = updater.UpdateChecker(GAME_VERSION)
        self.state = STATE_UPDATE_CHECK

    def _consume_pending_update(self) -> Optional[str]:
        """Checks how the previous launch's update attempt went (and forgets it).
        Returns an error message if this is still the version it updated from."""
        pending = self.data.get("pending_update")
        if not pending:
            return None
        self.data["pending_update"] = None
        persistence.save(self.data)
        target = pending.get("to", "")
        if updater.parse_version(GAME_VERSION) >= updater.parse_version(target):
            return None
        return updater.update_failed_message(target)

    def _poll_update_check(self, dt: float) -> None:
        self.update_check_anim = min(1.0, self.update_check_anim + dt * 1.6)
        checker = self.update_checker
        if checker is None or not checker.done:
            return
        silent = self.update_check_silent
        if checker.error:
            if silent:
                self.state = STATE_MENU
            else:
                self.update_error_msg = checker.error
                self.state = STATE_UPDATE_ERROR
        elif checker.updates:
            self.update_releases = checker.updates
            self.update_choice_index = 0
            self.state = STATE_UPDATE_PROMPT
        else:
            self.state = STATE_MENU if silent else STATE_UPDATE_NONE

    def _begin_update_download(self) -> None:
        blocker = updater.preflight_error()
        if blocker:
            self.update_error_msg = blocker
            self.state = STATE_UPDATE_ERROR
            return
        latest = self.update_releases[-1]
        asset = latest.asset_for_this_platform()
        if asset is None:
            self.update_error_msg = f"No {updater.current_platform()} build in release {latest.tag}."
            self.state = STATE_UPDATE_ERROR
            return
        asset_name = updater.ASSET_BY_PLATFORM[updater.current_platform()]
        dest = Path(tempfile.gettempdir()) / asset_name
        self.update_downloader = updater.Downloader(asset["url"], dest)
        self.state = STATE_UPDATE_DOWNLOAD

    def _poll_update_download(self) -> None:
        dl = self.update_downloader
        if dl is None or not dl.done:
            return
        if dl.error:
            self.update_error_msg = dl.error
            self.state = STATE_UPDATE_ERROR
            return
        # Remember what we're updating to, so the relaunched game can tell
        # whether the swap really happened (see _consume_pending_update).
        self.data["pending_update"] = {"from": GAME_VERSION, "to": self.update_releases[-1].tag}
        persistence.save(self.data)
        err = updater.apply_update_and_relaunch(dl.dest_path)
        # Only reached if the update could NOT be applied (e.g. a dev build) -
        # on success the process has already exited.
        self.data["pending_update"] = None
        persistence.save(self.data)
        self.update_error_msg = err or "Could not apply the update."
        self.state = STATE_UPDATE_ERROR

    # ---------- LAN multiplayer ----------

    def _pause_items(self) -> List[str]:
        if self.lan_role == "host":
            return LAN_HOST_PAUSE_ITEMS
        return PAUSE_ITEMS

    def _host_end_session(self) -> None:
        if self.lan_link and self.lan_link.connected:
            self.lan_link.send({"type": "host_left"})
        self._lan_teardown()
        self.state = STATE_MENU

    def _lan_teardown(self) -> None:
        if self.lan_link:
            self.lan_link.close()
        if self.lan_host:
            self.lan_host.close()
        if self.lan_client:
            self.lan_client.close()
        if self.lan_pending_link:
            self.lan_pending_link.close()
        self.lan_link = None
        self.lan_host = None
        self.lan_client = None
        self.lan_pending_link = None
        self.lan_role = None
        self.lan_cfg_override = None
        self.lan_unverified = {}
        self.lan_known_slots = set()
        self.lan_toast = ""
        if self.chat_active:
            pygame.key.stop_text_input()
        self.chat_active = False
        self.chat_input = ""
        self.chat_log = []
        self.chat_unread = 0
        self.chat_pending_open = False

    def _online_server_url(self) -> str:
        # MEGASNAKE_SERVER points a dev build at `wrangler dev` (ws://127.0.0.1:8787).
        return os.environ.get("MEGASNAKE_SERVER") or ONLINE_SERVER_URL

    def _net_issue(self) -> Optional[str]:
        """What to tell the player while an online link is degraded, or None."""
        link = self.lan_link
        if not link or not self.lan_role:
            return None
        if link.reconnecting:
            return "Connection lost - reconnecting..."
        if not link.peer_present:
            if self.lan_role == "host":
                down = [SLOT_LABEL[s] for s, up in link.roster.items() if not up]
                who = "/".join(down) if down else "your friend"
            else:
                who = "the host"
            return f"Waiting for {who} to reconnect..."
        return None

    def _build_snapshot(self, game_over: bool = False) -> dict:
        self.snapshot_seq += 1
        snap = {
            "type": "state",
            "seq": self.snapshot_seq,
            "match_size": self.match_size,
            "players": [
                {"body": [list(c) for c in p.body], "dir": list(p.direction), "alive": self.players_alive[i]}
                if p is not None else None
                for i, p in enumerate(self.players)
            ],
            "foods": [{"x": f.x, "y": f.y, "kind": f.kind} for f in self.foods],
            "powerups": [{"x": p.x, "y": p.y, "kind": p.kind} for p in self.powerups],
            "downerups": [{"x": d.x, "y": d.y, "kind": d.kind} for d in self.downerups],
            "obstacles": [list(o) for o in self.obstacles],
            "portal_pair": [list(self.portal_pair[0]), list(self.portal_pair[1])] if self.portal_pair else None,
            "active_powerups": dict(self.active_powerups),
            "score": self.score,
            "combo": self.combo,
            "curse_timer": self.curse_timer,
            "time_remaining": self.time_remaining,
            "game_over": game_over,
            "game_over_reason": self.game_over_reason if game_over else "",
        }
        # mode/ruleset/map/skin never change once a match is running, so only
        # put them on the wire once per session instead of on every one of
        # the ~10 snapshots/sec this gets called for over a match's lifetime.
        # apply_snapshot() already treats all four as optional (see its
        # `snap.get(...) in <enum>` guards), so omitting them is safe.
        if not self.match_meta_sent or game_over:
            snap["mode"] = self.mode_name()
            snap["ruleset"] = self.lan_ruleset_name
            snap["map"] = self.map_name
            snap["skin_p1"] = SKIN_NAMES[self.skin_idx]
            self.match_meta_sent = True
        return snap

    def apply_snapshot(self, snap: dict) -> None:
        seq = snap.get("seq")
        if isinstance(seq, int) and not isinstance(seq, bool):
            if seq <= self.last_snapshot_seq:
                return
            self.last_snapshot_seq = seq
        self.snapshot_age = 0.0
        self.match_size = snap.get("match_size", 2)
        for i, pdata in enumerate(snap.get("players", [])):
            if pdata is None:
                self.players[i] = None
                self.players_alive[i] = False
                continue
            snake = self.players[i]
            previous_body = list(snake.body) if snake is not None else []
            if snake is None:
                snake = self.players[i] = PlayerSnake(0, 0)
            snake.body = deque(tuple(c) for c in pdata["body"]) if pdata["body"] else deque([(0, 0)])
            snake.prev_body = previous_body or list(snake.body)
            snake.direction = tuple(pdata["dir"])
            self.players_alive[i] = pdata["alive"]

        self.foods = [Food(f["x"], f["y"], f["kind"]) for f in snap["foods"]]
        self.powerups = [PowerUp(p["x"], p["y"], p["kind"]) for p in snap["powerups"]]
        self.downerups = [Downerup(d["x"], d["y"], d["kind"]) for d in snap.get("downerups", [])]
        self.obstacles = set(tuple(o) for o in snap["obstacles"])
        self.portal_pair = (tuple(snap["portal_pair"][0]), tuple(snap["portal_pair"][1])) if snap["portal_pair"] else None
        self.active_powerups = dict(snap["active_powerups"])
        self.score = snap["score"]
        self.combo = snap["combo"]
        self.curse_timer = snap["curse_timer"]
        self.time_remaining = snap["time_remaining"]
        self.rivals = []

        if snap.get("mode") in MODES:
            self.mode_idx = MODES.index(snap["mode"])
        if snap.get("skin_p1") in SKIN_NAMES:
            self.skin_idx = SKIN_NAMES.index(snap["skin_p1"])
        if snap.get("ruleset") in LAN_RULESETS:
            self.lan_ruleset_name = snap["ruleset"]
            self.lan_cfg_override = dict(LAN_RULESETS[self.lan_ruleset_name])
        if snap.get("map") in MAPS:
            self.map_name = snap["map"]
            self.theme = dict(MAP_THEMES.get(self.map_name, DEFAULT_THEME))

        if snap.get("game_over"):
            self.game_over_reason = snap.get("game_over_reason") or "Game over."
            self.final_stats = {
                "score": self.score, "food_eaten": 0, "golden_eaten": 0,
                "length": sum(len(p.body) for p in self.players if p is not None), "time_alive": 0,
            }
            self.score_breakdown = {"normal": 0, "golden": 0, "mult_bonus": 0, "penalty": 0}
            self.run_coins_earned = 0
            self.run_streak_bonus = 0
            self.state = STATE_GAME_OVER

    def _open_chat(self) -> None:
        if not self.lan_role or self.chat_active:
            return
        self.chat_active = True
        self.chat_input = ""
        self.chat_unread = 0
        pygame.key.start_text_input()

    def _close_chat(self) -> None:
        if not self.chat_active:
            return
        self.chat_active = False
        self.chat_input = ""
        pygame.key.stop_text_input()

    def _send_heartbeat_if_due(self) -> None:
        """See LAN_HEARTBEAT_SECONDS. "ping" needs no receiver-side handling -
        any message type nothing recognizes is already silently dropped."""
        if not self.lan_link or not self.lan_link.connected:
            return
        now = pygame.time.get_ticks() / 1000.0
        if now - self.lan_heartbeat_last >= LAN_HEARTBEAT_SECONDS:
            self.lan_heartbeat_last = now
            self.lan_link.send({"type": "ping"})

    def handle_chat_text(self, text: str) -> None:
        """pygame.TEXTINPUT gives fully composed Unicode text (proper IME/dead-key
        support), unlike KEYDOWN which only covers keys pygame has a K_* for."""
        text = _clean_chat_text(text)
        if not text:
            return
        room = CHAT_MAX_LEN - len(self.chat_input)
        if room > 0:
            self.chat_input += text[:room]

    def handle_chat_key(self, key) -> None:
        if key == pygame.K_RETURN:
            self._send_chat_message()
        elif key == pygame.K_ESCAPE:
            self._close_chat()
        elif key == pygame.K_BACKSPACE:
            self.chat_input = self.chat_input[:-1]

    def _send_chat_message(self) -> None:
        text = self.chat_input.strip()
        self.chat_input = ""
        if not text or not self.lan_link:
            return
        now = pygame.time.get_ticks() / 1000.0
        if now - self.chat_last_sent < CHAT_COOLDOWN:
            return  # a paste or key-repeat flood; drop rather than spam the link
        self.chat_last_sent = now
        self.lan_link.send({"type": "chat", "text": text})
        self._append_chat("You", text)
        self.sounds.play(self.sounds.chat)

    def _append_chat(self, who: str, text: str) -> None:
        self.chat_log.append((who, text))
        if len(self.chat_log) > CHAT_MAX_LOG:
            self.chat_log = self.chat_log[-CHAT_MAX_LOG:]
        if who != "You" and not self.chat_active:
            self.chat_unread += 1

    def _on_chat_message(self, msg: dict) -> None:
        text = _clean_chat_text(str(msg.get("text", "")))[:CHAT_MAX_LEN]
        if not text:
            return
        who = SLOT_LABEL.get(msg.get("from"), "Friend")
        self._append_chat(who, text)
        self.sounds.play(self.sounds.chat)

    def _lan_begin_session(self, role: str, match_size: int = 2) -> None:
        self.lan_role = role
        self.snapshot_accum = 0.0
        self.snapshot_seq = 0
        self.last_snapshot_seq = -1
        self.snapshot_age = NETWORK_SNAPSHOT_INTERVAL
        self.match_meta_sent = False
        if role == "host":
            self.lan_link = self.lan_host.link if self.lan_online else self.lan_host
        # else: the guest's self.lan_link was already set in _lan_connecting_poll
        self.lan_known_slots = set(self.lan_link.roster.keys()) if role == "host" else set()
        self.mode_idx = MODES.index("Coop")
        self.reset_run(match_size=match_size)
        self.state = STATE_PLAYING

    def _lan_channel(self):
        """The one object main.py polls/sends through, regardless of role or
        transport: for Online it's always the single OnlineLink (host or
        guest); for LAN it's the Host itself while hosting (it already
        merges every guest), or the lone GuestLink while joining."""
        if self.lan_role == "host":
            return self.lan_host.link if self.lan_online else self.lan_host
        return self.lan_link

    def _lan_host_poll(self) -> None:
        """Runs for the whole lobby: host just started hosting and is
        waiting for 1-3 guests to join, showing a live roster, until they
        press Enter to start (see handle_lan_host_wait_key). A guest's
        version is checked here (LAN only - Online's relay already gated it
        before the connection even completed) by watching for each new
        slot's first message; a mismatch gets that one slot disconnected
        without affecting anyone else already waiting."""
        if not self.lan_host:
            return
        failure = self.lan_host.failure()
        if failure:
            self.lan_error_msg = failure
            self._lan_teardown()
            self.state = STATE_LAN_ERROR
            return
        self.lan_role = "host"
        channel = self.lan_host.link if self.lan_online else self.lan_host
        if self.lan_online and not channel.connected and channel.done:
            self.lan_error_msg = channel.error or "Could not create a room."
            self._lan_teardown()
            self.state = STATE_LAN_ERROR
            return

        now = pygame.time.get_ticks() / 1000.0
        for slot in list(channel.roster.keys()):
            if slot != "host" and slot not in self.lan_unverified:
                self.lan_unverified[slot] = now + LAN_HANDSHAKE_TIMEOUT
        for slot in list(self.lan_unverified.keys()):
            if slot not in channel.roster:
                del self.lan_unverified[slot]  # left before we even checked them

        for msg in channel.poll():
            sender = msg.get("from")
            if self.lan_online:
                continue  # no in-band version check needed; the relay already gated it
            if msg.get("type") == "hello" and sender in self.lan_unverified:
                their_version = str(msg.get("version") or "")
                if their_version and their_version != GAME_VERSION:
                    self.lan_host.close_slot(sender)
                    self.lan_toast = (
                        f"A player on v{their_version} tried to join (need v{GAME_VERSION}) - disconnected."
                    )
                    self.lan_toast_until = now + 4.0
                del self.lan_unverified[sender]

        for slot, deadline in list(self.lan_unverified.items()):
            if now >= deadline:
                del self.lan_unverified[slot]  # no "hello" in time; let an old build through

    def _lan_connecting_poll(self) -> None:
        """Online: OnlineClient already fully resolves connect-or-reject
        (including a version mismatch, rejected server-side by the relay
        before the connection even completes) via poll_connect_result().
        LAN: TCP has no such gate, so the guest sends its version as its
        first message for the host to check (see _lan_host_poll); if
        mismatched the host just closes this connection, which shows up
        here as a plain disconnect."""
        if not self.lan_client:
            return
        result = self.lan_client.poll_connect_result()
        if result is None:
            return
        if result is False:
            self.lan_error_msg = self.lan_client.error or "Could not connect."
            self.lan_client = None
            self.state = STATE_LAN_ERROR
            return
        self.lan_connect_label = self.lan_client.label
        self.lan_link = self.lan_client.link
        self.lan_client = None
        self.lan_role = "client"
        if not self.lan_online:
            self.lan_link.send({"type": "hello", "version": GAME_VERSION})
        self.state = STATE_LAN_HOST_WAIT  # the lobby screen, shared with the host (see draw_lan_host_wait)

    def _lan_client_poll(self, dt: float) -> None:
        if not self.lan_link:
            return
        self.snapshot_age = min(
            NETWORK_SNAPSHOT_INTERVAL, self.snapshot_age + dt,
        )
        # Drain whatever already arrived before checking the connection flag -
        # a graceful "host_left" is usually sitting in the queue right before
        # the socket reports closed, and it explains *why* far better than a
        # generic disconnect message would.
        for msg in self.lan_link.poll():
            mtype = msg.get("type")
            if mtype == "start":
                self._lan_begin_session("client")
            elif mtype == "state":
                self.apply_snapshot(msg)
            elif mtype == "chat":
                self._on_chat_message(msg)
            elif mtype == "_slot_gone":
                label = SLOT_LABEL.get(msg.get("slot"), "A player")
                self.toast_queue.append(("Player Left", f"{label} left the match", 3.0))
            elif mtype == "host_left":
                self.lan_error_msg = "Host ended the session."
                self._lan_teardown()
                self.state = STATE_LAN_ERROR
                return
            elif mtype == "paused":
                self.state = STATE_PAUSED
                if self.chat_pending_open:
                    self.chat_pending_open = False
                    self._open_chat()
            elif mtype == "resumed":
                self.state = STATE_PLAYING
        if not self.lan_link.connected:
            self.lan_error_msg = "Host disconnected."
            self._lan_teardown()
            self.state = STATE_LAN_ERROR
            return
        self._send_heartbeat_if_due()
        if self.state in (STATE_PLAYING, STATE_PAUSED):
            self._update_trail(dt)
            self.particles.update(dt)
            self._update_ambient(dt)

    def _lan_player_left(self, sender: Optional[str]) -> None:
        """A guest explicitly left (Esc, not a raw drop - see _lan_sync_roster
        for that case). Kills their snake and tells whoever's left, same as
        any other death, so the match just continues without them."""
        if sender not in PTAGS or not self._snake_alive(sender):
            return
        self._kill_snake(sender, "Left the game.")
        if not self.lan_online:  # Online's relay already told everyone else
            self.lan_link.send({"type": "_slot_gone", "slot": sender})

    def _lan_sync_roster(self) -> None:
        """Notices a guest's slot vanishing from the channel's roster without
        an explicit 'they left' message (a raw drop, not a graceful Esc) and
        treats it exactly like that player's snake dying - the match
        continues for whoever's left, same as any other death."""
        current = set(self.lan_link.roster.keys())
        for slot in self.lan_known_slots - current:
            if slot != "host":
                self._lan_player_left(slot)
        self.lan_known_slots = current

    def _lan_host_pause_poll(self) -> None:
        """While the host has the game paused, update_playing() (and its usual
        network polling) never runs. Still drain the socket so a client
        disconnect is noticed immediately instead of only on resume."""
        if not self.lan_link:
            return
        for msg in self.lan_link.poll():
            mtype = msg.get("type")
            if mtype == "chat":
                self._on_chat_message(msg)
            elif mtype == "client_left":
                self._lan_player_left(msg.get("from"))
            # "input" messages that arrive while paused are intentionally
            # dropped - the client is a pure renderer, queued moves from
            # before the pause shouldn't suddenly fire on resume.
        self._lan_sync_roster()
        if not self.lan_link.connected:
            self.lan_error_msg = "Lost your own connection to the game server."
            self._lan_teardown()
            self.state = STATE_LAN_ERROR
            return
        self._send_heartbeat_if_due()

    # ---------- run lifecycle ----------

    @property
    def player(self) -> Optional[PlayerSnake]:
        return self.players[0]

    @player.setter
    def player(self, v: Optional[PlayerSnake]) -> None:
        self.players[0] = v

    @property
    def player2(self) -> Optional[PlayerSnake]:
        return self.players[1]

    @player2.setter
    def player2(self, v: Optional[PlayerSnake]) -> None:
        self.players[1] = v

    @property
    def player_alive(self) -> bool:
        return self.players_alive[0]

    @player_alive.setter
    def player_alive(self, v: bool) -> None:
        self.players_alive[0] = v

    @property
    def player2_alive(self) -> bool:
        return self.players_alive[1]

    @player2_alive.setter
    def player2_alive(self, v: bool) -> None:
        self.players_alive[1] = v

    def reset_run(self, match_size: Optional[int] = None) -> None:
        cfg = self.mode_cfg()
        cx, cy = GRID_W // 2, GRID_H // 2

        # match_size: how many snakes THIS run has (1=solo, 2=local Coop, or
        # 2-4 for LAN/online - the host decides based on who joined before
        # starting; see _lan_begin_session). Solo/local-coop keep today's
        # exact behavior; it's only ever 3 or 4 for a network match.
        if match_size is None:
            match_size = 2 if cfg["coop"] else 1
        self.match_size = max(1, min(match_size, MAX_PLAYERS))
        SPAWN_OFFSETS = [(0, 0), (-6, 0), (6, 0), (0, -6)]
        self.players = [None, None, None, None]
        self.players_alive = [False, False, False, False]
        for i in range(self.match_size):
            ox, oy = SPAWN_OFFSETS[i]
            self.players[i] = PlayerSnake(cx + ox, cy + oy)
            self.players_alive[i] = True

        self.rivals: List[EnemySnake] = []
        corners = [(GRID_W - 5, GRID_H - 5), (4, 4), (GRID_W - 5, 4), (4, GRID_H - 5)]
        for i in range(cfg["rivals"]):
            rx, ry = corners[i % len(corners)]
            self.rivals.append(EnemySnake(rx, ry))

        self.obstacles: set = set()
        # Maps apply to every mode except Daily - Daily's whole point is an
        # identical, date-seeded layout for everyone, so letting the player
        # swap in an arbitrary map would break the fairness of its
        # leaderboard. Everything else (solo or multiplayer, LAN or local)
        # gets the chosen map's obstacles, theme, and ambient effect.
        if self.mode_name() != "Daily":
            self.theme = dict(MAP_THEMES.get(self.map_name, DEFAULT_THEME))
            heads = [p.head for p in self.players if p is not None]
            heads.extend(self.rivals[i].head for i in range(len(self.rivals)))
            self.obstacles |= {
                cell for cell in MAPS.get(self.map_name, set())
                if all(abs(cell[0] - hx) + abs(cell[1] - hy) >= 4 for hx, hy in heads)
            }
        else:
            self.theme = dict(DEFAULT_THEME)
        self.ambient_particles = []
        self._ambient_spawn_accum = 0.0
        self.foods: List[Food] = []
        self.powerups: List[PowerUp] = []
        self.downerups: List[Downerup] = []
        self.active_powerups: Dict[str, float] = {}
        self.portal_pair: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None
        self.p1_portal_lock = 0
        self.p2_portal_lock = 0
        self.curse_timer = 0.0

        self.score = 0
        self.combo = 1
        self.combo_timer = 0.0
        self.combo_window = 2.6
        self.move_accum = 0.0
        self.speed_boost_timer = 0.0
        self.time_alive = 0.0
        self.next_obstacle_score = 40 if self.mode_name() == "Hardcore" else 60
        self.obstacle_interval = 40 if self.mode_name() == "Hardcore" else 60

        self.time_remaining = cfg["timer"]
        self.last_death_reason: Dict[str, str] = {}

        self.pending_death_bursts: List[list] = []  # [delay, x, y, color]
        self.death_pause_timer = 0.0
        self.trail_marks: List[list] = []  # [x, y, life, seq] cells your tail just left
        self.trail_last_tail: Optional[Tuple[int, int]] = None
        self.trail_seq = 0
        self.score_popups: List[list] = []  # [px, py, text, color, age, big]
        self.near_miss_cooldown = 0.0
        self.near_miss_flash = 0.0
        self.hitstop_timer = 0.0
        self.hitstop_factor = 1.0
        self.zoom_timer = 0.0
        self.zoom_duration = 0.18
        self.zoom_mag = 0.07

        self.score_breakdown = {"normal": 0, "golden": 0, "mult_bonus": 0, "penalty": 0}

        self.mode_best_at_start = max(
            (s["score"] for s in self.data.get("high_scores", []) if s["mode"] == self.mode_name()),
            default=0,
        )
        self.pb_broken = False
        self.run_coins_earned = 0
        self.run_streak_bonus = 0
        self.run_quest_rewards = []
        self.run_new_ghost = False
        self.announcer_queue = []
        self.last_combo_milestone = 0

        self.stats = dict(
            food_eaten=0, golden_eaten=0, combo=1, bombs_survived=0,
            length=len(self.player.body), score=0, speed_tier=0,
            wall_phases=0, time_alive=0.0,
            combo_peak=1, length_peak=len(self.player.body),
            powerups_collected=0, portals_used=0, near_misses=0,
        )

        # Ghost replay: single-snake local modes only. Coop has two snakes and a
        # LAN client doesn't simulate, so neither has one clean trail to record.
        self.ghost_enabled = not cfg["coop"] and self.lan_role is None
        self.recording_trail: List[List[int]] = []
        ghost = self.ghosts.get(self.mode_name()) if self.ghost_enabled else None
        self.ghost_trail: Optional[List[List[int]]] = ghost["trail"] if ghost else None
        self.ghost_best_score = ghost["score"] if ghost else 0
        self.ghost_index = 0

        if cfg["seeded"]:
            seed_str = datetime.date.today().isoformat() + self.mode_name()
            random.seed(seed_str)
            # The very first food is always safe (normal) so a deterministic seed
            # can never hand every player of the day an unavoidable bomb/curse.
            fx, fy = random_free_cell(self.occupied_cells())
            self.foods.append(Food(fx, fy, FOOD_NORMAL))
            random.seed()
        else:
            self._spawn_food()

        self.game_over_reason = ""

    def occupied_cells(self) -> set:
        occ = set(self.player.body) | self.obstacles
        if self.player2 and self.player2_alive:
            occ |= set(self.player2.body)
        for r in self.rivals:
            if r.alive:
                occ |= r.occupies()
        for f in self.foods:
            occ.add((f.x, f.y))
        for p in self.powerups:
            occ.add((p.x, p.y))
        for d in self.downerups:
            occ.add((d.x, d.y))
        if self.portal_pair:
            occ.add(self.portal_pair[0])
            occ.add(self.portal_pair[1])
        return occ

    def _spawn_food(self) -> None:
        self.foods.append(spawn_food(self.occupied_cells()))

    # ---------- update ----------

    def move_interval(self) -> float:
        cfg = self.mode_cfg()
        tier = min(5, self.score // 60)
        speed_mult = cfg["speed_mult"] * DIFFICULTY_SPEED_MULT[self.difficulty]
        interval = (BASE_MOVE_INTERVAL / (1 + tier * 0.15)) / speed_mult
        if self.speed_boost_timer > 0:
            interval *= 0.55
        if POWERUP_SLOWMO in self.active_powerups:
            interval *= 1.7
        return max(0.03, interval)

    def update_playing(self, dt: float) -> None:
        if self.lan_role == "host" and self.lan_link:
            for msg in self.lan_link.poll():
                mtype = msg.get("type")
                if mtype == "input":
                    sender = msg.get("from")
                    d = msg.get("dir")
                    if sender in PTAGS[1:] and isinstance(d, list) and len(d) == 2:
                        idx = PTAGS.index(sender)
                        if self.players[idx] is not None:
                            self.players[idx].set_direction((int(d[0]), int(d[1])))
                elif mtype == "client_left":
                    self._lan_player_left(msg.get("from"))
                elif mtype == "chat":
                    self._on_chat_message(msg)
                elif mtype == "chat_pause_request":
                    self.pause_index = 0
                    self.state = STATE_PAUSED
                    self.lan_link.send({"type": "paused"})
                    return
            self._lan_sync_roster()
            if not self.lan_link.connected:
                self.lan_error_msg = "Lost your own connection to the game server."
                self._lan_teardown()
                self.state = STATE_LAN_ERROR
                return
            if self._net_issue():
                # Online only: freeze the match while either side's connection
                # is being re-established, instead of letting the snakes crash.
                self.particles.update(dt)
                return

        if self.death_pause_timer > 0:
            self.death_pause_timer -= dt
            remaining = max(0.0, self.death_pause_timer)
            frac = min(1.0, (DEATH_PAUSE_SECONDS - remaining) / DEATH_SLOWMO_RAMP)
            slowmo = 1.0 - (1.0 - DEATH_SLOWMO_FLOOR) * frac
            self._update_death_effects(dt * slowmo)
            if self.death_pause_timer <= 0:
                self.death_pause_timer = 0.0
                self._finalize_game_over()
            return

        if self.hitstop_timer > 0:
            self.hitstop_timer = max(0.0, self.hitstop_timer - dt)
            dt *= self.hitstop_factor
        if self.near_miss_flash > 0:
            self.near_miss_flash = max(0.0, self.near_miss_flash - dt)
        if self.near_miss_cooldown > 0:
            self.near_miss_cooldown = max(0.0, self.near_miss_cooldown - dt)

        self.time_alive += dt
        self.stats["time_alive"] = self.time_alive

        if self.time_remaining is not None:
            self.time_remaining -= dt
            if self.time_remaining <= 0:
                self.time_remaining = 0
                self._time_up()
                return

        if self.speed_boost_timer > 0:
            self.speed_boost_timer = max(0.0, self.speed_boost_timer - dt)
        if self.curse_timer > 0:
            self.curse_timer = max(0.0, self.curse_timer - dt)
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 1

        for p in self.score_popups:
            p[4] += dt
        self.score_popups = [p for p in self.score_popups if p[4] < SCORE_POPUP_DURATION]

        for snake in self.players:
            if snake is not None:
                snake.tail_pop_anim += dt
                snake.turn_anim += dt

        expired = []
        for kind in list(self.active_powerups.keys()):
            self.active_powerups[kind] -= dt
            if self.active_powerups[kind] <= 0:
                expired.append(kind)
        for kind in expired:
            del self.active_powerups[kind]

        if POWERUP_MAGNET in self.active_powerups:
            for f in list(self.foods):
                heads = []
                if self.player_alive:
                    heads.append(self.player.head)
                if self.player2 and self.player2_alive:
                    heads.append(self.player2.head)
                for hx, hy in heads:
                    if abs(f.x - hx) + abs(f.y - hy) <= 3:
                        self._consume_food(f, self.player, auto=True)
                        break

        heads_now = []
        if self.player_alive:
            heads_now.append(self.player.head)
        if self.player2 and self.player2_alive:
            heads_now.append(self.player2.head)

        for p in list(self.powerups):
            p.ttl -= dt
            if p.ttl <= 0:
                self.powerups.remove(p)
                continue
            if (p.x, p.y) in heads_now:
                self._activate_powerup(p.kind)
                self.powerups.remove(p)

        cfg = self.mode_cfg()
        new_p = maybe_spawn_powerup(self.occupied_cells(), self.powerups, cfg["powerups"])
        if new_p:
            self.powerups.append(new_p)

        # Downerups despawn on a timer like power-ups; actually picking one up
        # happens in _tick() instead (grid-step granularity), so it works the
        # same way food does for every connected player, not just p1/p2.
        for d in list(self.downerups):
            d.ttl -= dt
            if d.ttl <= 0:
                self.downerups.remove(d)
        new_d = maybe_spawn_downerup(self.occupied_cells(), self.downerups, cfg["powerups"])
        if new_d:
            self.downerups.append(new_d)

        active = self.players_alive[:self.match_size]
        if cfg["coop"] and any(active) and not all(active):
            if not any(p.kind == POWERUP_REVIVE for p in self.powerups) and random.random() < 0.015:
                rx, ry = random_free_cell(self.occupied_cells())
                self.powerups.append(PowerUp(rx, ry, POWERUP_REVIVE))

        if not self.portal_pair:
            pair = maybe_spawn_portal_pair(self.occupied_cells())
            if pair:
                self.portal_pair = pair

        if cfg["obstacles"] and self.score >= self.next_obstacle_score:
            self._grow_maze()
            self.next_obstacle_score += self.obstacle_interval

        if self.p1_portal_lock > 0:
            self.p1_portal_lock -= 1
        if self.p2_portal_lock > 0:
            self.p2_portal_lock -= 1

        self.move_accum += dt
        interval = self.move_interval()
        if self.move_accum >= interval:
            self.move_accum -= interval
            self._tick()

        if self.zoom_timer > 0:
            self.zoom_timer = max(0.0, self.zoom_timer - dt)

        self._update_death_bursts(dt)
        self._update_trail(dt)

        self.stats.update(
            combo=self.combo, length=len(self.player.body), score=self.score,
            speed_tier=min(5, self.score // 60),
        )
        self.stats["combo_peak"] = max(self.stats["combo_peak"], self.combo)
        self.stats["length_peak"] = max(self.stats["length_peak"], len(self.player.body))

        milestone = (self.combo // 5) * 5
        if milestone >= 5 and milestone > self.last_combo_milestone:
            self.last_combo_milestone = milestone
            self._announce(f"COMBO x{milestone}!", GOLD)
        elif self.combo == 1 and self.last_combo_milestone >= 5:
            self._announce("COMBO BREAKER", DANGER, life=1.0)
            self.last_combo_milestone = 0

        newly = self.tracker.check(self._achievement_stats())
        for ach in newly:
            self.toast_queue.append(("Achievement Unlocked!", ach.name, 3.0))
            self.sounds.play(self.sounds.achievement)
            for skin_name, req in SKIN_UNLOCK_REQUIREMENT.items():
                if req == ach.id:
                    self.toast_queue.append(("New Skin Unlocked!", skin_name, 3.0))
                    self.sounds.play(self.sounds.unlock)

        if not self.pb_broken and self.mode_best_at_start > 0 and self.score > self.mode_best_at_start:
            self.pb_broken = True
            self.toast_queue.append(("New Personal Best!", f"{self.mode_name()}: {self.score}", 3.0))
            self._unlock("record_breaker")
            self._announce("NEW PERSONAL BEST!", GREEN, life=1.8)
            self.sounds.play(self.sounds.achievement)
            self.zoom_timer = self.zoom_duration

        self.toast_queue = [(t, s, tl - dt) for (t, s, tl) in self.toast_queue if tl - dt > 0]
        for a in self.announcer_queue:
            a[2] -= dt
        self.announcer_queue = [a for a in self.announcer_queue if a[2] > 0]
        self.particles.update(dt)
        self._update_ambient(dt)

        if self.lan_role == "host" and self.lan_link and self.lan_link.connected:
            self.snapshot_accum += dt
            if self.snapshot_accum >= NETWORK_SNAPSHOT_INTERVAL - 1e-9:
                self.snapshot_accum = 0.0
                self.lan_link.send(self._build_snapshot())

    def _update_death_bursts(self, dt: float) -> None:
        for burst in list(self.pending_death_bursts):
            burst[0] -= dt
            if burst[0] <= 0:
                self.particles.burst(burst[1], burst[2], burst[3], count=8, speed=180, life=0.6)
                self.pending_death_bursts.remove(burst)

    def _my_snake(self) -> Tuple[Optional[PlayerSnake], bool]:
        """The snake this player controls (a LAN/online client steers player 2)."""
        if self.lan_role == "client":
            return self.player2, self.player2_alive
        return self.player, self.player_alive

    def _update_trail(self, dt: float) -> None:
        for mark in self.trail_marks:
            mark[2] -= dt
        self.trail_marks = [m for m in self.trail_marks if m[2] > 0]
        snake, alive = self._my_snake()
        if TRAIL_EFFECTS[self.equipped_trail]["color"] is None or not alive or not snake or not snake.body:
            self.trail_last_tail = None
            return
        tail = tuple(snake.body[-1])
        if self.trail_last_tail is not None and tail != self.trail_last_tail:
            lx, ly = self.trail_last_tail
            self.trail_marks.append([lx, ly, TRAIL_LIFE, self.trail_seq])
            color = self.trail_color(pygame.time.get_ticks() / 1000.0, self.trail_seq * 0.07)
            px, py = grid_to_px(*self._center((lx, ly)))
            self.particles.burst(px, py, color, count=2, speed=35, life=0.45)
            self.trail_seq += 1
        self.trail_last_tail = tail

    def _draw_trail(self, board: pygame.Surface) -> None:
        if not self.trail_marks:
            return
        t = pygame.time.get_ticks() / 1000.0
        for x, y, life, seq in self.trail_marks:
            frac = max(0.0, life / TRAIL_LIFE)
            color = self.trail_color(t, seq * 0.07)
            if color is None:
                return
            cx, cy = x * CELL_SIZE + CELL_SIZE // 2, y * CELL_SIZE + CELL_SIZE // 2
            # Soft additive glow, then a shrinking solid core on top.
            glow_r = int(CELL_SIZE * (0.32 + 0.22 * frac))
            glow = gfx.surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            gfx.draw.circle(glow, (*color, int(60 * frac)), (glow_r, glow_r), glow_r)
            board.blit(glow, (cx - glow_r, cy - glow_r), special_flags=pygame.BLEND_RGBA_ADD)
            core = max(2, int(CELL_SIZE * 0.5 * frac))
            sq = gfx.surface((core, core), pygame.SRCALPHA)
            gfx.draw.rect(sq, (*color, int(220 * frac)), (0, 0, core, core), border_radius=max(1, core // 3))
            board.blit(sq, (cx - core // 2, cy - core // 2))

    def _draw_score_popups(self, board: pygame.Surface) -> None:
        for px, py, text, color, age, big in self.score_popups:
            frac = min(1.0, age / SCORE_POPUP_DURATION)
            font = font_small if big else font_tiny
            label = font.render(text, True, color)
            label = label.copy()  # rendered text is cached; don't fade the shared copy
            label.set_alpha(int(255 * (1.0 - frac)))
            y = py - SCORE_POPUP_RISE * frac
            board.blit(label, (px - label.get_width() // 2, y - label.get_height() // 2))

    def _draw_near_miss_flash(self, board: pygame.Surface) -> None:
        if self.near_miss_flash <= 0:
            return
        frac = self.near_miss_flash / NEAR_MISS_FLASH_DURATION
        w, h = board.get_size()
        s = gfx.surface((w, h), pygame.SRCALPHA)
        thickness = 14
        color = (255, 255, 210, int(180 * frac))
        gfx.draw.rect(s, color, (0, 0, w, thickness))
        gfx.draw.rect(s, color, (0, h - thickness, w, thickness))
        gfx.draw.rect(s, color, (0, 0, thickness, h))
        gfx.draw.rect(s, color, (w - thickness, 0, thickness, h))
        board.blit(s, (0, 0))

    def _update_death_effects(self, dt: float) -> None:
        self._update_trail(dt)
        self._update_death_bursts(dt)
        self.particles.update(dt)
        self._update_ambient(dt)

    def _grow_maze(self) -> None:
        occ = self.occupied_cells()
        placed = 0
        attempts = 0
        heads = [self.player.head]
        if self.player2:
            heads.append(self.player2.head)
        while placed < 4 and attempts < 60:
            attempts += 1
            x, y = random_free_cell(occ)
            if any(abs(x - hx) + abs(y - hy) < 5 for hx, hy in heads):
                continue
            self.obstacles.add((x, y))
            occ.add((x, y))
            placed += 1

    def _activate_powerup(self, kind: str) -> None:
        self.stats["powerups_collected"] += 1
        px, py = grid_to_px(*self._center(self.player.head))
        if kind == POWERUP_TELEPORT:
            self.sounds.play(self.sounds.teleport)
            self.particles.burst(px, py, self.powerup_color(kind), count=20, speed=200)
            if self.foods:
                nearest = min(self.foods, key=lambda f: abs(f.x - self.player.head[0]) + abs(f.y - self.player.head[1]))
                self._consume_food(nearest, self.player, auto=True)
            return
        if kind == POWERUP_REVIVE:
            self._revive_teammate()
            return

        self.active_powerups[kind] = POWERUP_DURATIONS[kind]
        self.sounds.play(self.sounds.freeze if kind == POWERUP_FREEZE else self.sounds.powerup)
        self.particles.burst(px, py, self.powerup_color(kind), count=18)

    def _revive_teammate(self) -> None:
        active = self.players_alive[:self.match_size]
        if not any(active) or all(active):
            return  # nothing to revive, or everyone already down/up
        dead_idx = next(i for i in range(self.match_size) if not self.players_alive[i])
        reviver_idx = next(i for i in range(self.match_size) if self.players_alive[i])
        dead_tag = PTAGS[dead_idx]
        reviver = self.players[reviver_idx]
        dead_snake = self.players[dead_idx]

        occ = self.occupied_cells()
        rx, ry = reviver.head
        spot = None
        for ddx, ddy in [(2, 0), (-2, 0), (0, 2), (0, -2), (3, 0), (-3, 0), (0, 3), (0, -3)]:
            cand = (rx + ddx, ry + ddy)
            if 0 <= cand[0] < GRID_W and 0 <= cand[1] < GRID_H and cand not in occ:
                spot = cand
                break
        if spot is None:
            spot = random_free_cell(occ)

        dead_snake.body = deque([spot, (spot[0] - 1, spot[1]), (spot[0] - 2, spot[1])])
        dead_snake.prev_body = list(dead_snake.body)
        dead_snake.direction = (1, 0)
        dead_snake.pending_direction = (1, 0)

        self.players_alive[dead_idx] = True

        # A brief shared Ghost window so the revived teammate (and their
        # rescuer) can't be insta-killed by whatever was nearby.
        self.active_powerups[POWERUP_GHOST] = max(self.active_powerups.get(POWERUP_GHOST, 0.0), 2.5)

        px, py = grid_to_px(*self._center(spot))
        self.particles.burst(px, py, self.powerup_color(POWERUP_REVIVE), count=26, speed=220)
        self.shake(0.25, 5)
        self.sounds.play(self.sounds.unlock)
        self._announce("REVIVED!", self.powerup_color(POWERUP_REVIVE), life=1.5)

    def _p1_set_direction(self, d: Tuple[int, int]) -> None:
        """Route a direction key through this instead of calling
        self.player.set_direction directly, so Curse (controls reversed) can
        flip the *key press* itself rather than whatever happens to be queued
        for the next step. Flipping the queued direction instead would also
        flip "no new key pressed, keep going straight" into a 180 - which is
        a self-collision for any snake longer than one cell, i.e. an
        unavoidable, instant death every single tick you didn't react fast
        enough. PlayerSnake.set_direction still blocks reversing into your own
        neck relative to your *true* current heading, so a cursed player
        turning squarely into themselves is still refused, same as normal."""
        if self.curse_timer > 0:
            d = (-d[0], -d[1])
        self.player.set_direction(d)

    def _blocking_set(self, exclude_tag: str) -> set:
        s = set(self.obstacles)
        for i, snake in enumerate(self.players):
            if snake is not None and self.players_alive[i] and PTAGS[i] != exclude_tag:
                s |= set(snake.body)
        for r in self.rivals:
            if r.alive:
                s |= r.occupies()
        return s

    def _achievement_stats(self) -> dict:
        """Run stats plus the context some achievements need (current mode and
        lifetime totals). Kept out of self.stats so none of it is treated as a
        per-run personal best."""
        return dict(
            self.stats, mode=self.mode_name(),
            lifetime_games=self.data.get("games_played", 0),
            lifetime_food=self.data.get("total_food_eaten", 0) + self.stats["food_eaten"],
            streak=self.data.get("streak", {}).get("count", 0),
            quests_today=len(self.data.get("quests", {}).get("completed", [])),
        )

    def _check_near_miss(self, cfg: dict) -> None:
        """A whoosh + screen flash when the head survives next to something
        that would have killed it - skill gets its own feedback, not just
        "you didn't die." Scoped to p1 only; see the hitstop/flash fields."""
        hx, hy = self.player.head
        blocked = self._blocking_set("p1")
        own_tail = set(list(self.player.body)[3:])  # skip head+neck: always adjacent, not a "miss"
        for nx, ny in ((hx + 1, hy), (hx - 1, hy), (hx, hy + 1), (hx, hy - 1)):
            off_grid = not cfg["wrap"] and not (0 <= nx < GRID_W and 0 <= ny < GRID_H)
            if off_grid or (nx, ny) in blocked or (nx, ny) in own_tail:
                self.near_miss_cooldown = NEAR_MISS_COOLDOWN
                self.near_miss_flash = NEAR_MISS_FLASH_DURATION
                self.stats["near_misses"] += 1
                if self.settings["near_miss_slowmo"]:
                    self.hitstop_timer = NEAR_MISS_HITSTOP
                    self.hitstop_factor = NEAR_MISS_HITSTOP_FACTOR
                self.sounds.play(self.sounds.near_miss)
                return

    def _tick(self) -> None:
        cfg = self.mode_cfg()
        ghost = POWERUP_GHOST in self.active_powerups
        wrap = cfg["wrap"] or ghost

        movers: List[Tuple[str, PlayerSnake]] = []
        if self.player_alive:
            movers.append(("p1", self.player))
        if cfg["coop"]:
            for i in range(1, self.match_size):
                if self.players[i] is not None and self.players_alive[i]:
                    movers.append((PTAGS[i], self.players[i]))

        prev_heads = {}
        for tag, snake in movers:
            prev_heads[tag] = snake.head
            snake.step(wrap=wrap)

        for tag, snake in movers:
            nx, ny = snake.head
            died, reason = self._check_collision(tag, snake, nx, ny, ghost, cfg)
            if died:
                if POWERUP_SHIELD in self.active_powerups:
                    del self.active_powerups[POWERUP_SHIELD]
                    snake.body[0] = prev_heads[tag]
                    snake.prev_body = list(snake.body)
                    ppx, ppy = grid_to_px(*self._center(snake.head))
                    self.particles.burst(ppx, ppy, (120, 255, 190), count=20)
                    self.shake(0.2, 4)
                    self._rumble(0.5, 0.6, 200)
                    self._announce("CLUTCH SAVE!", GREEN)
                else:
                    self._kill_snake(tag, reason)

        for tag, snake in movers:
            if self._snake_alive(tag):
                self._check_portal(tag, snake)

        if self.player_alive and self.near_miss_cooldown <= 0:
            self._check_near_miss(cfg)

        for tag, snake in movers:
            if self._snake_alive(tag):
                hx, hy = snake.head
                for f in list(self.foods):
                    if (f.x, f.y) == (hx, hy):
                        self._consume_food(f, snake)
                for d in list(self.downerups):
                    if (d.x, d.y) == (hx, hy):
                        self.downerups.remove(d)
                        self._consume_downerup(tag, d)

        if self.ghost_enabled and self.player_alive:
            if len(self.recording_trail) < GHOST_MAX_TICKS:
                hx, hy = self.player.head
                self.recording_trail.append([hx, hy, self.score])
            self.ghost_index += 1

        if self.rivals and POWERUP_FREEZE not in self.active_powerups:
            for rival in self.rivals:
                if not rival.alive:
                    continue
                target = (self.foods[0].x, self.foods[0].y) if self.foods else rival.head
                blocked = set(self.obstacles)
                for other in self.rivals:
                    if other is not rival and other.alive:
                        blocked |= other.occupies()
                rival.choose_direction(target, blocked)
                grow = False
                for f in list(self.foods):
                    ehx = rival.head[0] + rival.direction[0]
                    ehy = rival.head[1] + rival.direction[1]
                    if (f.x, f.y) == (ehx, ehy):
                        self.foods.remove(f)
                        self._spawn_food()
                        grow = True
                rival.step(grow)

    def _snake_alive(self, tag: str) -> bool:
        return self.players_alive[PTAGS.index(tag)]

    def _check_collision(self, tag: str, snake: PlayerSnake, nx: int, ny: int, ghost: bool, cfg: dict) -> Tuple[bool, str]:
        if ghost:
            if not (0 <= nx < GRID_W and 0 <= ny < GRID_H):
                self.stats["wall_phases"] = self.stats.get("wall_phases", 0) + 1
            return False, ""

        if not (0 <= nx < GRID_W and 0 <= ny < GRID_H):
            return True, "You slammed into the wall."
        if snake.self_collision():
            return True, "You bit yourself."
        if (nx, ny) in self.obstacles:
            return True, "You crashed into an obstacle."

        if cfg["coop"]:
            my_idx = PTAGS.index(tag)
            for i, other in enumerate(self.players):
                if i == my_idx or other is None or not self.players_alive[i]:
                    continue
                if (nx, ny) in set(other.body):
                    return True, "You crashed into your teammate."
        for r in self.rivals:
            if r.alive and (nx, ny) in r.occupies():
                return True, "The rival snake got you."
        return False, ""

    def _check_portal(self, tag: str, snake: PlayerSnake) -> None:
        if not self.portal_pair:
            return
        lock = self.p1_portal_lock if tag == "p1" else self.p2_portal_lock
        if lock > 0:
            return
        a, b = self.portal_pair
        hx, hy = snake.head
        dest = None
        if (hx, hy) == a:
            dest = b
        elif (hx, hy) == b:
            dest = a
        if dest is None:
            return
        delta = (dest[0] - hx, dest[1] - hy)
        snake.body = deque((bx + delta[0], by + delta[1]) for (bx, by) in snake.body)
        snake.prev_body = list(snake.body)
        if tag == "p1":
            self.p1_portal_lock = 1
        else:
            self.p2_portal_lock = 1
        px, py = grid_to_px(*self._center(snake.head))
        self.particles.burst(px, py, PORTAL_A, count=16, speed=160)
        self.sounds.play(self.sounds.portal)
        self.stats["portals_used"] += 1

    def _consume_food(self, f: Food, snake: PlayerSnake, auto: bool = False) -> None:
        if f not in self.foods:
            return
        self.foods.remove(f)
        px, py = grid_to_px(*self._center((f.x, f.y)))
        mult = 2 if POWERUP_MULT in self.active_powerups else 1

        if f.kind == FOOD_NORMAL:
            snake.grow(1)
            self.combo = min(20, self.combo + 1)
            self.combo_timer = self.combo_window
            base = 10 * self.combo
            gained = base * mult
            self.score += gained
            self.score_breakdown["normal"] += base
            self.score_breakdown["mult_bonus"] += gained - base
            self.stats["food_eaten"] += 1
            self.sounds.play(self.sounds.eat_sound(self.combo))
            self._rumble(0.0, 0.3, 70)
            self.particles.burst(px, py, self.food_color(FOOD_NORMAL), count=10)
            self._spawn_score_popup(px, py, f"+{gained}", self.food_color(FOOD_NORMAL))

        elif f.kind == FOOD_GOLDEN:
            snake.grow(1)
            self.combo = min(20, self.combo + 1)
            self.combo_timer = self.combo_window
            gained = 50 * mult
            self.score += gained
            self.score_breakdown["golden"] += 50
            self.score_breakdown["mult_bonus"] += gained - 50
            self.stats["food_eaten"] += 1
            self.stats["golden_eaten"] += 1
            self.sounds.play(self.sounds.golden)
            self._rumble(0.25, 0.7, 160)
            self.particles.burst(px, py, self.food_color(FOOD_GOLDEN), count=24, speed=200)
            self._spawn_score_popup(px, py, f"+{gained}", self.food_color(FOOD_GOLDEN), big=True)
            if self.combo >= 3:
                self.zoom_timer = self.zoom_duration
                self._announce("GOLDEN RUSH!", GOLD, life=1.0)

        elif f.kind == FOOD_SPEED:
            snake.grow(1)
            self.speed_boost_timer = 4.0
            gained = 10 * mult
            self.score += gained
            self.score_breakdown["normal"] += 10
            self.score_breakdown["mult_bonus"] += gained - 10
            self.stats["food_eaten"] += 1
            self.sounds.play(self.sounds.eat)
            self._rumble(0.0, 0.3, 70)
            self.particles.burst(px, py, self.food_color(FOOD_SPEED), count=14)
            self._spawn_score_popup(px, py, f"+{gained}", self.food_color(FOOD_SPEED))

        elif f.kind == FOOD_SHRINK:
            snake.shrink(2)
            self.score = max(0, self.score - 5)
            self.score_breakdown["penalty"] -= 5
            self.sounds.play(self.sounds.shrink)
            self.particles.burst(px, py, self.food_color(FOOD_SHRINK), count=12)
            self._spawn_score_popup(px, py, "-5", DANGER)

        self._spawn_food()

    def _consume_downerup(self, tag: str, d: Downerup) -> None:
        """Bomb/curse: these are downerups (hazard power-ups), not food - see
        constants.DOWNERUP_* - so unlike _consume_food this never touches
        self.foods, and a Magnet or Teleport power-up can no longer drag you
        into one by accident."""
        px, py = grid_to_px(*self._center((d.x, d.y)))

        if d.kind == DOWNERUP_CURSE:
            self.curse_timer = CURSE_DURATION
            self.score = max(0, self.score - 5)
            self.score_breakdown["penalty"] -= 5
            self.sounds.play(self.sounds.curse)
            self.particles.burst(px, py, self.downerup_color(DOWNERUP_CURSE), count=16, speed=180)
            self._announce("CURSED!", self.downerup_color(DOWNERUP_CURSE), life=1.0)
            self._spawn_score_popup(px, py, "-5", DANGER)

        elif d.kind == DOWNERUP_BOMB:
            if POWERUP_SHIELD in self.active_powerups:
                del self.active_powerups[POWERUP_SHIELD]
                self.stats["bombs_survived"] = self.stats.get("bombs_survived", 0) + 1
                self.particles.burst(px, py, (120, 255, 190), count=20)
                self.shake(0.25, 5)
                self._announce("DEFUSED!", GREEN)
            else:
                self.particles.burst(px, py, DANGER, count=30, speed=260, life=0.7)
                self.shake(0.35, 8)
                self.sounds.play(self.sounds.bomb)
                self._kill_snake(tag, "You detonated a bomb.")

    # ---------- death / game over ----------

    def _kill_snake(self, tag: str, reason: str) -> None:
        snake = self.players[PTAGS.index(tag)]
        for i, (bx, by) in enumerate(snake.body):
            px, py = grid_to_px(*self._center((bx, by)))
            color = (255, 255, 255) if i == 0 else SNAKE_SKINS[SKIN_NAMES[self.skin_idx]][1]
            self.pending_death_bursts.append([i * 0.035, px, py, color])
        self.shake(0.4, 7)
        self._rumble(1.0, 0.8, 450)
        self.sounds.play(self.sounds.death)

        self.players_alive[PTAGS.index(tag)] = False
        self.last_death_reason[tag] = reason

        cfg = self.mode_cfg()
        if not cfg["coop"]:
            self.game_over_reason = reason
            self.death_pause_timer = DEATH_PAUSE_SECONDS
            return

        if not any(self.players_alive[i] for i in range(self.match_size)):
            parts = [f"{PLAYER_LABELS[i]}: {self.last_death_reason.get(PTAGS[i], '-')}"
                     for i in range(self.match_size)]
            self.game_over_reason = "   ".join(parts)
            self.death_pause_timer = DEATH_PAUSE_SECONDS

    def _time_up(self) -> None:
        self.game_over_reason = "Time's up!"
        self.sounds.play(self.sounds.achievement)
        self._finalize_game_over()

    def _finalize_game_over(self) -> None:
        today = datetime.date.today()
        today_iso = today.isoformat()
        yesterday_iso = (today - datetime.timedelta(days=1)).isoformat()

        # Combo and length decay during a run (combo timeout, shrink food), so the
        # value at death understates what was reached. Progress bars and quests
        # should credit the peak.
        final = dict(self.stats)
        final["score"] = self.score
        final["combo"] = self.stats["combo_peak"]
        final["length"] = self.stats["length_peak"]

        self.data["games_played"] = self.data.get("games_played", 0) + 1
        self.data["total_food_eaten"] = self.data.get("total_food_eaten", 0) + self.stats["food_eaten"]
        self.data["achievements"] = sorted(self.tracker.unlocked)
        persistence.update_stat_bests(self.data, final)
        persistence.add_run_history(self.data, self.score, self.mode_name(), today_iso)

        self.run_coins_earned = max(0, self.score // 10)
        self.wallet += self.run_coins_earned
        streak_bonus = persistence.apply_daily_streak(self.data, today_iso, yesterday_iso)
        self.run_streak_bonus = streak_bonus or 0
        self.wallet += self.run_streak_bonus
        self.streak_count = self.data.get("streak", {}).get("count", self.streak_count)

        self.run_quest_rewards = []
        quest_state = persistence.quest_state_for_today(self.data, today_iso)
        for q in quests_for_date(today_iso):
            if q.id not in quest_state["completed"] and q.check(final, self.mode_name()):
                quest_state["completed"].append(q.id)
                self.wallet += q.reward
                self.run_quest_rewards.append((q.description, q.reward))
        self.data["wallet"] = self.wallet

        # Re-check now that lifetime totals, the streak and today's quests include
        # this run, so "play 10 games" and friends unlock the moment they're earned.
        end_stats = dict(final, mode=self.mode_name(),
                         lifetime_games=self.data["games_played"], lifetime_food=self.data["total_food_eaten"],
                         streak=self.streak_count, quests_today=len(quest_state["completed"]))
        self.run_new_achievements = [a.name for a in self.tracker.check(end_stats)]
        if self.run_new_achievements:
            self.sounds.play(self.sounds.achievement)
        self.data["achievements"] = sorted(self.tracker.unlocked)
        persistence.update_stat_bests(self.data, {k: v for k, v in end_stats.items() if isinstance(v, (int, float))})

        self.run_new_ghost = False
        if self.ghost_enabled:
            self.run_new_ghost = persistence.save_ghost_if_better(
                self.ghosts, self.mode_name(), self.score, self.recording_trail,
            )

        self.final_stats = final

        if self.lan_role == "host" and self.lan_link and self.lan_link.connected:
            self.lan_link.send(self._build_snapshot(game_over=True))

        # Letter-by-letter initials entry only makes sense solo: in a LAN/
        # online match the other player is already sitting at their OWN Game
        # Over screen (reached independently via the game_over snapshot, not
        # through this method at all - only the host ever calls it), with no
        # way to see or take part in this one. Worse, while the host sat here
        # the link went fully quiet - no snapshots, no heartbeat, nothing
        # polls it - for however long typing initials took, which was enough
        # on its own to cause a real "disconnected" after an actual new high
        # score. So multiplayer always skips straight to Game Over instead.
        if self.lan_role is None and persistence.would_qualify_for_leaderboard(self.data, self.score):
            self.pending_score_entry = {"score": self.score, "mode": self.mode_name(), "date": today_iso}
            self.pending_initials = ["A", "A", "A"]
            self.initials_cursor = 0
            persistence.save(self.data)
            self.state = STATE_ENTER_INITIALS
        else:
            persistence.add_high_score(self.data, self.score, self.mode_name(), today_iso, "---")
            persistence.save(self.data)
            self.state = STATE_GAME_OVER

    def _commit_high_score(self) -> None:
        if self.pending_score_entry:
            initials = "".join(self.pending_initials)
            persistence.add_high_score(
                self.data, self.pending_score_entry["score"], self.pending_score_entry["mode"],
                self.pending_score_entry["date"], initials,
            )
            persistence.save(self.data)
            self.pending_score_entry = None
        self.state = STATE_GAME_OVER

    # ---------- drawing ----------

    def _pulse_color(self, color: Tuple[int, int, int], i: int, t: float) -> Tuple[int, int, int]:
        wave = 10 * (0.5 + 0.5 * ((t * 3 - i * 0.4) % 6.283 - 3.14) / 3.14)
        return clamp_color((color[0] + wave - 5, color[1] + wave - 5, color[2] + wave - 5))

    # ---------- art ----------

    def _draw_backdrop(self, dim: float = 0.8) -> None:
        """The night-meadow painting behind every menu screen, cover-fitted to the
        canvas and darkened by `dim` so text stays readable. Cached per resolution."""
        key = (round(gfx.scale(), 4), round(dim, 2))
        surf = self._bg_cache.get(key)
        if surf is None:
            raw = art.raw.get("menu_bg")
            if raw is None:
                surf = False
            else:
                cw, ch = pygame.Surface.get_size(screen)
                rw, rh = raw.get_size()
                sc = max(cw / rw, ch / rh)
                big = pygame.transform.smoothscale(raw, (math.ceil(rw * sc), math.ceil(rh * sc)))
                big = self._grade_backdrop(big)
                surf = gfx.surface((SCREEN_W, SCREEN_H))
                pygame.Surface.blit(surf, big, (-(big.get_width() - cw) // 2, -int((big.get_height() - ch) * 0.1)))
                if dim > 0:
                    shade = pygame.Surface((cw, ch), pygame.SRCALPHA)
                    shade.fill((6, 8, 14, int(255 * dim)))
                    pygame.Surface.blit(surf, shade, (0, 0))
            self._bg_cache[key] = surf
        if surf:
            screen.blit(surf, (0, 0))
        else:
            screen.fill(BG)

    @staticmethod
    def _grade_backdrop(img: pygame.Surface) -> pygame.Surface:
        """Take the edge off the cartoon painting for the menus: mute the colours, darken it and
        soften it out of focus, so it reads as atmosphere behind crisp UI rather than as a picture."""
        w, h = img.get_size()
        arr = pygame.surfarray.array3d(img).astype(np.float32)
        gray = arr.mean(axis=2, keepdims=True)
        arr = (gray + (arr - gray) * 0.42) * 0.78
        out = pygame.Surface((w, h))
        pygame.surfarray.blit_array(out, np.clip(arr, 0, 255).astype(np.uint8))
        img = pygame.transform.smoothscale(out, (max(1, w // 12), max(1, h // 12)))
        while img.get_width() < w // 2:  # climb back in 1.5x steps: a single big jump looks blocky
            img = pygame.transform.smoothscale(img, (int(img.get_width() * 1.5), int(img.get_height() * 1.5)))
        return pygame.transform.smoothscale(img, (w, h))

    def _board_floor(self) -> gfx.HSurface:
        """Checkered arena floor aligned to the game's cells, with grass tufts in the corners
        (default map only; themed maps keep their own tint)."""
        tint = self.theme.get("bg_tint")
        key = (round(gfx.scale(), 4), tint)
        floor = self._floor_cache.get(key)
        if floor is None:
            if tint:
                tones = (tint, tuple(min(255, c + 7) for c in tint))
            else:
                tones = ((9, 47, 62), (12, 62, 78))
            floor = gfx.surface((GRID_W * CELL_SIZE, GRID_H * CELL_SIZE))
            for gy in range(GRID_H):
                for gx in range(GRID_W):
                    floor.fill(tones[(gx + gy) % 2], (gx * CELL_SIZE, gy * CELL_SIZE, CELL_SIZE, CELL_SIZE))
            if not tint:
                spots = [(0.3, 0.2, 0), (GRID_W - 2.2, 0.3, 1), (0.1, GRID_H - 1.9, 2), (GRID_W - 2.1, GRID_H - 1.8, 3),
                         (0.2, 8.6, 1), (GRID_W - 1.6, 12.0, 0)]
                for gx, gy, idx in spots:
                    tuft = art.get(f"tuft_{idx}", w=CELL_SIZE * (1.5 if idx < 2 else 1.3))
                    if tuft:
                        floor.blit(tuft, (gx * CELL_SIZE, gy * CELL_SIZE))
            self._floor_cache[key] = floor
        return floor

    def _sprite_icon(self, surface, name: str, cx: float, cy: float, radius: float) -> bool:
        """Draw art sprite `name` centred at (cx, cy); False means "no art, draw the vector
        fallback" (art missing, or colour-blind mode, which relies on the recoloured vectors)."""
        if self.colorblind:
            return False
        spr = art.get(name, fit=radius * 2.4)
        if spr is None:
            return False
        bob = math.sin(pygame.time.get_ticks() / 260.0 + cx * 0.07) * radius * 0.07
        surface.blit(spr, (cx - spr.get_width() / 2, cy - spr.get_height() / 2 + bob))
        return True

    # Snake sizes are THICKNESSES (logical px), so art with different proportions keeps the same
    # weight on the grid. The body is one smooth tube; only the head is a sprite.
    SPR_HEAD_THICK, SPR_BODY_THICK = 19.0, 16.0
    TUBE_STEP = 1.3  # px between the circles that make up the tube: finer = smoother tail tip

    @staticmethod
    def _length_for(name: str, thick: float) -> float:
        w, h = art.raw[name].get_size()
        return thick * w / h

    # Tongue sprite sheet (tongue_0..N in assets/art): frame width in logical px, how long one flick
    # plays, and where the mouth is on the head sprite when it faces right (forward, down) in px.
    # TONGUE_MOUTH_DOWN: how far below the head's centre line the mouth is (0 = tip of the snout).
    TONGUE_W, TONGUE_SECONDS, TONGUE_MOUTH_DOWN = 26.0, 0.45, 0.0

    def _draw_tongue_sprite(self, board, root, ux: float, uy: float, theta: float, t: float, phase: float) -> bool:
        """Play the tongue animation sheet from `root` (the mouth) along the heading (ux, uy).
        False only when there's no sheet, so the caller can fall back to the drawn tongue."""
        frames = 0
        while art.has(f"tongue_{frames}"):
            frames += 1
        if frames == 0:
            return False
        since = (t + phase * 1.7 + 1.3) % TONGUE_PERIOD
        if since >= self.TONGUE_SECONDS:
            return True
        spr = art.get(f"tongue_{min(frames - 1, int(since / self.TONGUE_SECONDS * frames))}",
                      w=self.TONGUE_W, angle=theta)
        if spr is not None:  # the sheet's root is the middle of the left edge, so the centre is half a width out
            cx, cy = root[0] + ux * self.TONGUE_W / 2, root[1] + uy * self.TONGUE_W / 2
            board.blit(spr, (cx - spr.get_width() / 2, cy - spr.get_height() / 2))
        return True

    @staticmethod
    def _smooth_path(points):
        """Corner-cutting (Chaikin): rounds every turn into a curve, ends stay put."""
        pts = list(points)
        for _ in range(3):
            if len(pts) < 3:
                break
            out = [pts[0]]
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                out.append((0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by))
                out.append((0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by))
            out.append(pts[-1])
            pts = out
        return pts

    @staticmethod
    def _resample(pts, step: float):
        """Evenly spaced points along a polyline (always includes both ends)."""
        out = [pts[0]]
        need = step
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            seg = math.hypot(bx - ax, by - ay)
            if seg < 1e-9:
                continue
            pos = 0.0
            while seg - pos >= need:
                pos += need
                f = pos / seg
                out.append((ax + (bx - ax) * f, ay + (by - ay) * f))
                need = step
            need -= seg - pos
        if out[-1] != pts[-1]:
            out.append(pts[-1])
        return out

    def _draw_tube(self, board, pts, colors, thick: float, taper: float = 30.0) -> None:
        """A thick rounded tube along `pts` in three flat tones: a darker rim, the body, and a
        lighter belly band that sits low on the tube. The last `taper` px narrow to a tail tip."""
        k = board.k
        step = self.TUBE_STEP
        shadow, base, belly = colors
        n = len(pts)
        widths = [min(1.0, 0.28 + 0.72 * ((n - 1 - i) * step) / taper) if taper else 1.0 for i in range(n)]
        circle = pygame.draw.circle
        for color, off, rad in ((shadow, 0.0, thick / 2), (base, 0.0, thick / 2 - 1.3),
                                (belly, thick * 0.2, thick * 0.17)):
            for (x, y), f in zip(pts, widths):
                circle(board, color, (x * k, (y + off * f) * k), max(1, round(rad * f * k)))

    def _draw_snake_sprites(self, board, cells, positions, direction, tint, ghost: bool, alive: bool,
                             anim=None, t: float = 0.0, phase: float = 0.0) -> bool:
        """Draw a snake: one continuous rounded tube that bends smoothly through turns, a head sprite
        that rotates to follow it, and the tongue. False if the art isn't there."""
        if not art.has("snake_head"):
            return False
        n = len(cells)
        if n == 0:
            return True
        C = CELL_SIZE
        tint = tint if alive else (52, 62, 58)
        palette = art.snake_palette(tint)
        if ghost and alive:  # fade toward the floor so it reads as see-through
            palette = tuple(tuple(int(c * 0.45 + f * 0.55) for c, f in zip(col, (12, 60, 76))) for col in palette)
        centres = [((x + 0.5) * C, (y + 0.5) * C) for x, y in positions]

        # The chain of interpolated segment centres is already a smoothly sliding curve; split it
        # wherever it wraps around the board edge so no tube is drawn across the screen.
        runs, run = [], [centres[0]]
        for i in range(1, n):
            if abs(positions[i][0] - positions[i - 1][0]) > 1.5 or abs(positions[i][1] - positions[i - 1][1]) > 1.5:
                runs.append(run)
                run = []
            run.append(centres[i])
        runs.append(run)

        head_curve = None
        for ri, r in enumerate(runs):
            if len(r) == 1:
                r = [r[0], r[0]]
            curve = self._resample(self._smooth_path(r), self.TUBE_STEP)
            if ri == 0:
                head_curve = curve
            self._draw_tube(board, curve, palette, self.SPR_BODY_THICK,  # head end first, so the taper lands on the tail
                            taper=30.0 if ri == len(runs) - 1 else 0.0)

        # Heading from the head end of the curve: it rotates smoothly through a turn.
        hx, hy = centres[0]
        ux, uy = float(direction[0]), float(direction[1])
        if head_curve is not None and len(head_curve) > 4:
            qx, qy = head_curve[min(4, len(head_curve) - 1)]
            d = math.hypot(hx - qx, hy - qy)
            if d > 1e-6:
                ux, uy = (hx - qx) / d, (hy - qy) / d
        theta = math.degrees(math.atan2(-uy, ux))
        length = self._length_for("snake_head", self.SPR_HEAD_THICK)

        tongue_done = (not alive) or ghost or self._draw_tongue_sprite(
            board, (hx + ux * (length / 2 - 1.5), hy + uy * (length / 2 - 1.5)), ux, uy, theta, t, phase)
        spr = art.get("snake_head", w=length, angle=theta, vflip=ux < -0.001, tint=tint,
                      alpha=150 if (ghost and alive) else None)
        if spr is not None:
            cx, cy = hx + ux * 3.0, hy + uy * 3.0
            board.blit(spr, (cx - spr.get_width() / 2, cy - spr.get_height() / 2))
        if alive and not tongue_done:
            self._draw_tongue_flick(board, positions[0][0], positions[0][1], round(ux), round(uy), t, phase,
                                    reach=length / 2 + 1.5)
        return True

    def _draw_tongue_flick(self, board: pygame.Surface, fx: float, fy: float,
                            dx: int, dy: int, t: float, phase: float, reach: Optional[float] = None) -> None:
        """A forked tongue pokes out of the head every few seconds and
        retracts - one of a couple of idle "alive" tics (with the blink)
        that have nothing to do with gameplay, just personality."""
        tongue_t = (t + phase * 1.7 + 1.3) % TONGUE_PERIOD
        if tongue_t >= TONGUE_HOLD:
            return
        grow_until = TONGUE_HOLD * 0.4
        if tongue_t < grow_until:
            out = tongue_t / grow_until
        else:
            out = max(0.0, 1.0 - (tongue_t - grow_until) / (TONGUE_HOLD - grow_until))
        reach = CELL_SIZE // 2 - 1 if reach is None else reach
        base_x = fx * CELL_SIZE + CELL_SIZE // 2 + dx * reach
        base_y = fy * CELL_SIZE + CELL_SIZE // 2 + dy * reach
        tip_x, tip_y = base_x + dx * 7 * out, base_y + dy * 7 * out
        color = (230, 60, 80)
        gfx.draw.line(board, color, (base_x, base_y), (tip_x, tip_y), 2)
        perp_x, perp_y = -dy, dx
        fork = 3 * out
        gfx.draw.line(board, color, (tip_x, tip_y),
                          (tip_x + (perp_x - dx) * fork, tip_y + (perp_y - dy) * fork), 1)
        gfx.draw.line(board, color, (tip_x, tip_y),
                          (tip_x + (-perp_x - dx) * fork, tip_y + (-perp_y - dy) * fork), 1)

    def _draw_snake(self, board: pygame.Surface, snake: PlayerSnake, skin: list, alpha: float,
                     ghost_active: bool, alive: bool, name_tag: str) -> None:
        t = pygame.time.get_ticks() / 1000.0
        # Desyncs blink/tongue timing between snakes so a 4-player match
        # doesn't look like everyone's blinking in unison.
        phase = (id(snake) % 1000) * 0.001
        positions = snake.render_positions(alpha) if alive else [(x, y) for x, y in snake.body]
        drawn = self._draw_snake_sprites(board, list(snake.body), positions, snake.direction, skin[1],
                                         ghost_active, alive, anim=snake, t=t, phase=phase)
        for i, (fx, fy) in enumerate([] if drawn else positions):
            base_color = skin[0] if i == 0 else skin[1]
            color = self._pulse_color(base_color, i, t) if alive else tuple(max(0, c // 3) for c in base_color)
            if ghost_active and alive:
                s = gfx.surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                gfx.draw.rect(s, (*color, 140), (1, 1, CELL_SIZE - 2, CELL_SIZE - 2), border_radius=6)
                board.blit(s, (fx * CELL_SIZE, fy * CELL_SIZE))
            else:
                r = pygame.Rect(fx * CELL_SIZE + 1, fy * CELL_SIZE + 1, CELL_SIZE - 2, CELL_SIZE - 2)
                if alive and i == len(positions) - 1 and snake.tail_pop_anim < TAIL_GROW_POP_DURATION:
                    # The newest tail segment scales in from nothing instead
                    # of just appearing full-size - a little "pop" when you eat.
                    scale = snake.tail_pop_anim / TAIL_GROW_POP_DURATION
                    r = r.inflate(-r.width * (1 - scale), -r.height * (1 - scale))
                if alive and i == 0 and snake.turn_anim < TURN_SQUASH_DURATION:
                    # Cartoon squash-and-stretch on the head right after a
                    # turn: stretched along the new heading, squashed across
                    # it, easing back to normal - a turn reads as a deliberate
                    # snap instead of the grid silently relabeling "direction".
                    frac = snake.turn_anim / TURN_SQUASH_DURATION
                    stretch = 1.0 + 0.3 * (1 - frac)
                    squash = 1.0 - 0.22 * (1 - frac)
                    dx, dy = snake.direction
                    new_w = r.width * (stretch if dx else squash)
                    new_h = r.height * (stretch if dy else squash)
                    r = r.inflate(new_w - r.width, new_h - r.height)
                gfx.draw.rect(board, color, r, border_radius=6 if i > 0 else 8)
                if i == 0 and alive:
                    eye_dx, eye_dy = snake.direction
                    ex = fx * CELL_SIZE + CELL_SIZE // 2 + eye_dx * 4
                    ey = fy * CELL_SIZE + CELL_SIZE // 2 + eye_dy * 4
                    blink_t = (t + phase) % BLINK_PERIOD
                    if blink_t < BLINK_HOLD:
                        gfx.draw.line(board, (10, 10, 15), (int(ex) - 3, int(ey)), (int(ex) + 3, int(ey)), 2)
                    else:
                        gfx.draw.circle(board, (10, 10, 15), (int(ex), int(ey)), 3)
                    self._draw_tongue_flick(board, fx, fy, eye_dx, eye_dy, t, phase)

        if alive and positions:
            speed_tier = min(5, self.score // 60)
            if self.speed_boost_timer > 0 or speed_tier >= 3:
                hx, hy = positions[0]
                cx, cy = hx * CELL_SIZE + CELL_SIZE // 2, hy * CELL_SIZE + CELL_SIZE // 2
                glow_color = self.trail_color(t) or skin[0]
                glow = gfx.surface((CELL_SIZE * 3, CELL_SIZE * 3), pygame.SRCALPHA)
                gfx.draw.circle(glow, (*glow_color, 55), (CELL_SIZE * 3 // 2, CELL_SIZE * 3 // 2), CELL_SIZE)
                board.blit(glow, (cx - CELL_SIZE * 1.5, cy - CELL_SIZE * 1.5), special_flags=pygame.BLEND_RGBA_ADD)

    def ghost_point(self) -> Optional[List[int]]:
        """[x, y, score] of the best run at the same tick as the current run, or
        None if there's no ghost or the ghost's run already ended."""
        if not self.ghost_trail or self.ghost_index <= 0 or self.ghost_index > len(self.ghost_trail):
            return None
        return self.ghost_trail[self.ghost_index - 1]

    def _draw_ghost(self, board: pygame.Surface) -> None:
        point = self.ghost_point()
        if point is None or not self.settings["show_ghost"]:
            return
        gx, gy = point[0], point[1]
        if not (0 <= gx < GRID_W and 0 <= gy < GRID_H):
            return
        cx, cy = gx * CELL_SIZE + CELL_SIZE // 2, gy * CELL_SIZE + CELL_SIZE // 2
        s = gfx.surface((CELL_SIZE * 2, CELL_SIZE * 2), pygame.SRCALPHA)
        gfx.draw.circle(s, (220, 225, 255, 70), (CELL_SIZE, CELL_SIZE), CELL_SIZE // 2)
        gfx.draw.circle(s, (220, 225, 255, 150), (CELL_SIZE, CELL_SIZE), CELL_SIZE // 2, width=2)
        board.blit(s, (cx - CELL_SIZE, cy - CELL_SIZE))

    def _vignette_band(self, length: int, vertical: bool) -> pygame.Surface:
        """A red band fading from opaque at the wall to clear inward. Cached per
        size/orientation since it's identical every frame."""
        key = (length, vertical)
        cache = self._vignette_cache
        if key not in cache:
            depth = CELL_SIZE * 3
            surf = gfx.surface((depth, length) if vertical else (length, depth), pygame.SRCALPHA)
            for i in range(depth):
                a = int(150 * (1 - i / depth) ** 2)
                if vertical:
                    gfx.draw.line(surf, (255, 40, 40, a), (i, 0), (i, length))
                else:
                    gfx.draw.line(surf, (255, 40, 40, a), (0, i), (length, i))
            cache[key] = surf
        return cache[key]

    def _draw_wall_vignette(self, board: pygame.Surface) -> None:
        if self.mode_cfg()["wrap"] or not self.player_alive or POWERUP_GHOST in self.active_powerups:
            return
        hx, hy = self.player.head
        w, h = board.get_size()
        pulse = 0.65 + 0.35 * abs(((pygame.time.get_ticks() / 1000.0 * 2.5) % 2) - 1)
        edges = [
            (hx, "left"), (GRID_W - 1 - hx, "right"),
            (hy, "top"), (GRID_H - 1 - hy, "bottom"),
        ]
        for dist, side in edges:
            if dist > 2:
                continue
            strength = (3 - dist) / 3 * pulse
            if side in ("left", "right"):
                band = self._vignette_band(h, vertical=True)
                if side == "right":
                    band = gfx.flip(band, True, False)
                pos = (0, 0) if side == "left" else (w - band.get_width(), 0)
            else:
                band = self._vignette_band(w, vertical=False)
                if side == "bottom":
                    band = gfx.flip(band, False, True)
                pos = (0, 0) if side == "top" else (0, h - band.get_height())
            band = band.copy()
            band.set_alpha(int(255 * strength))
            board.blit(band, pos)

    def _draw_announcer(self, board: pygame.Surface) -> None:
        w, h = board.get_size()
        for i, (text, color, life, max_life) in enumerate(self.announcer_queue):
            elapsed = max_life - life
            fade = min(1.0, life / (max_life * 0.4))
            rise = int(elapsed * 22)
            y = h // 3 + i * 48 - rise
            shadow = font_big.render(text, True, (0, 0, 0))
            label = font_big.render(text, True, color)
            shadow = shadow.copy()  # rendered text is cached; don't fade the shared copy
            shadow.set_alpha(int(180 * fade))
            label = label.copy()  # rendered text is cached; don't fade the shared copy
            label.set_alpha(int(255 * fade))
            x = w // 2 - label.get_width() // 2
            board.blit(shadow, (x + 3, y + 3))
            board.blit(label, (x, y))

    def _draw_obstacle(self, board: pygame.Surface, gx: int, gy: int) -> None:
        shape = self.theme.get("shape", "block")
        color = self.theme.get("obstacle_color", DEFAULT_THEME["obstacle_color"])
        glow = self.theme.get("glow_color")
        cx, cy, size = gx * CELL_SIZE, gy * CELL_SIZE, CELL_SIZE

        if shape == "block":
            wall = art.get("wall_tile", fit=CELL_SIZE + 2)
            if wall:
                board.blit(wall, (cx - 1, cy - 1))
                return

        if shape == "rock":
            r = pygame.Rect(cx + 2, cy + 2, size - 4, size - 4)
            gfx.draw.rect(board, color, r, border_radius=2)
            if glow:
                t = pygame.time.get_ticks() / 400.0
                pulse = 0.5 + 0.5 * abs(((t + gx * 0.3 + gy * 0.7) % 2) - 1)
                crack = tuple(int(glow[i] * pulse + color[i] * (1 - pulse)) for i in range(3))
                gfx.draw.line(board, crack, (cx + 5, cy + size - 5), (cx + size - 5, cy + 5), 2)
        elif shape == "peak":
            gfx.draw.polygon(board, color, [
                (cx + size // 2, cy + 2), (cx + 2, cy + size - 2), (cx + size - 2, cy + size - 2),
            ])
            if glow:
                gfx.draw.polygon(board, glow, [
                    (cx + size // 2, cy + 2), (cx + size // 2 - 4, cy + size // 2), (cx + size // 2 + 4, cy + size // 2),
                ])
        elif shape == "dune":
            r = pygame.Rect(cx + 1, cy + size // 3, size - 2, size - size // 3 - 1)
            gfx.draw.ellipse(board, color, r)
        elif shape == "crystal":
            pts = [(cx + size // 2, cy + 1), (cx + size - 2, cy + size // 2),
                   (cx + size // 2, cy + size - 2), (cx + 2, cy + size // 2)]
            gfx.draw.polygon(board, color, pts)
            if glow:
                gfx.draw.polygon(board, glow, pts, width=1)
        else:
            r = pygame.Rect(cx + 2, cy + 2, size - 4, size - 4)
            gfx.draw.rect(board, color, r, border_radius=4)

    def _spawn_ambient(self, kind: str) -> None:
        board_w, board_h = GRID_W * CELL_SIZE, GRID_H * CELL_SIZE
        glow = self.theme.get("glow_color") or (255, 255, 255)
        if kind == "embers":
            p = [random.uniform(board_w * 0.55, board_w * 0.95), board_h * 0.15,
                 random.uniform(-6, 6), random.uniform(-35, -18)]
        elif kind == "snow":
            p = [random.uniform(0, board_w), -5, random.uniform(-8, 8), random.uniform(14, 26)]
        elif kind == "sand":
            p = [-5, random.uniform(0, board_h), random.uniform(18, 34), random.uniform(-3, 3)]
        else:  # sparkle
            p = [random.uniform(0, board_w), random.uniform(0, board_h), 0.0, 0.0]
        life = random.uniform(0.5, 1.0) if kind == "sparkle" else random.uniform(1.5, 5.0)
        self.ambient_particles.append(p + [life, life, random.uniform(1.2, 2.6), glow])

    def _update_ambient(self, dt: float) -> None:
        kind = self.theme.get("ambient")
        if kind:
            self._ambient_spawn_accum += dt
            while self._ambient_spawn_accum >= 0.12:
                self._ambient_spawn_accum -= 0.12
                self._spawn_ambient(kind)

        board_h = GRID_H * CELL_SIZE
        alive = []
        for p in self.ambient_particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
            if p[4] > 0 and -20 <= p[1] <= board_h + 20:
                alive.append(p)
        self.ambient_particles = alive

    def _draw_ambient(self, board: pygame.Surface) -> None:
        for (x, y, vx, vy, life, max_life, radius, color) in self.ambient_particles:
            t = max(0.0, min(1.0, life / max_life))
            alpha = int(200 * t)
            r = max(1, int(radius))
            s = gfx.surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            gfx.draw.circle(s, (*color, alpha), (r + 1, r + 1), r)
            board.blit(s, (x - r, y - r), special_flags=pygame.BLEND_RGBA_ADD)

    def draw_playing(self, alpha: float) -> None:
        ox, oy = self.particles.get_shake_offset() if self.screen_shake_enabled else (0, 0)
        board = gfx.surface((GRID_W * CELL_SIZE, GRID_H * CELL_SIZE))
        board.blit(self._board_floor(), (0, 0))

        combo_t = min(1.0, self.combo / 20)
        line_color = tuple(int(GRID_LINE[i] + (ACCENT[i] - GRID_LINE[i]) * combo_t * 0.4) for i in range(3))
        if self.settings["grid_lines"]:
            for gx in range(GRID_W + 1):
                gfx.draw.line(board, line_color, (gx * CELL_SIZE, 0), (gx * CELL_SIZE, GRID_H * CELL_SIZE))
            for gy in range(GRID_H + 1):
                gfx.draw.line(board, line_color, (0, gy * CELL_SIZE), (GRID_W * CELL_SIZE, gy * CELL_SIZE))

        for (ox2, oy2) in self.obstacles:
            self._draw_obstacle(board, ox2, oy2)

        self._draw_ambient(board)

        if self.portal_pair:
            t = pygame.time.get_ticks() / 300.0
            for (px_, py_), color in zip(self.portal_pair, (PORTAL_A, PORTAL_B)):
                cx, cy = px_ * CELL_SIZE + CELL_SIZE // 2, py_ * CELL_SIZE + CELL_SIZE // 2
                for ring in range(2):
                    rad = CELL_SIZE // 2 - 2 - ring * 4
                    if rad > 0:
                        start = t + ring * 2
                        gfx.draw.arc(board, color, (cx - rad, cy - rad, rad * 2, rad * 2), start, start + 4, 2)

        for f in self.foods:
            cx, cy = f.x * CELL_SIZE + CELL_SIZE // 2, f.y * CELL_SIZE + CELL_SIZE // 2
            self._draw_food_icon(board, f.kind, cx, cy, CELL_SIZE // 2 - 2)

        for p in self.powerups:
            cx, cy = p.x * CELL_SIZE + CELL_SIZE // 2, p.y * CELL_SIZE + CELL_SIZE // 2
            self._draw_powerup_icon(board, p.kind, cx, cy, CELL_SIZE // 2 - 2)

        for d in self.downerups:
            cx, cy = d.x * CELL_SIZE + CELL_SIZE // 2, d.y * CELL_SIZE + CELL_SIZE // 2
            self._draw_downerup_icon(board, d.kind, cx, cy, CELL_SIZE // 2 - 2)

        for rival in self.rivals:
            if not rival.alive:
                continue
            if self._draw_snake_sprites(board, rival.body, rival.body, rival.direction, rival.color, False, True):
                continue
            for i, (bx, by) in enumerate(rival.body):
                shade = rival.color if i == 0 else tuple(max(0, c - 40) for c in rival.color)
                r = pygame.Rect(bx * CELL_SIZE + 1, by * CELL_SIZE + 1, CELL_SIZE - 2, CELL_SIZE - 2)
                gfx.draw.rect(board, shade, r, border_radius=6)

        self._draw_ghost(board)
        self._draw_trail(board)

        skin = SNAKE_SKINS[SKIN_NAMES[self.skin_idx]]
        ghost_active = POWERUP_GHOST in self.active_powerups
        self._draw_snake(board, self.player, skin, alpha, ghost_active, self.player_alive, "p1")
        for i in range(1, self.match_size):
            if self.players[i] is not None:
                self._draw_snake(board, self.players[i], PLAYER_COLORS[i], alpha, ghost_active,
                                  self.players_alive[i], PTAGS[i])

        if POWERUP_SHIELD in self.active_powerups and self.player_alive:
            hx, hy = self.player.render_positions(alpha)[0]
            cx, cy = hx * CELL_SIZE + CELL_SIZE // 2, hy * CELL_SIZE + CELL_SIZE // 2
            gfx.draw.circle(board, self.powerup_color(POWERUP_SHIELD), (int(cx), int(cy)), CELL_SIZE, width=2)

        self.particles.draw(board)
        self._draw_score_popups(board)
        self._draw_near_miss_flash(board)
        self._draw_wall_vignette(board)
        self._draw_announcer(board)

        self._draw_backdrop(0.8)  # shows in the strips above/below the board
        frame = pygame.Rect(-3, BOARD_Y - 3, GRID_W * CELL_SIZE + 6, GRID_H * CELL_SIZE + 6)
        gfx.draw.rect(screen, (8, 10, 16), frame, border_radius=6)
        gfx.draw.rect(screen, (92, 200, 255), frame.inflate(-2, -2), width=2, border_radius=5)
        if self.zoom_timer > 0:
            frac = self.zoom_timer / self.zoom_duration
            scale = 1 + self.zoom_mag * frac
            w, h = board.get_size()
            scaled = gfx.zoom(board, scale)
            dx = (scaled.get_width() - w) // 2
            dy = (scaled.get_height() - h) // 2
            screen.blit(scaled, (ox - dx, oy + BOARD_Y - dy))
        else:
            screen.blit(board, (ox, oy + BOARD_Y))

    def draw_sidebar(self) -> None:
        panel = pygame.Rect(GRID_W * CELL_SIZE, 0, SIDEBAR_W, SCREEN_H)
        side_art = art.get("sidebar_bg", w=SIDEBAR_W, h=SCREEN_H)
        if side_art:
            screen.blit(side_art, panel.topleft)
        else:
            gfx.draw.rect(screen, SIDEBAR_BG, panel)
        x = GRID_W * CELL_SIZE + 18
        y = 14

        screen.blit(font_mid.render("MEGA SNAKE", True, ACCENT), (x, y))
        y += 30
        mode_line = f"Mode: {self.mode_name()}  [{self.difficulty}]"
        if self.lan_role:
            net = "Online" if self.lan_online else "LAN"
            mode_line = f"{net} {'Host' if self.lan_role == 'host' else 'Client'}: {self.lan_ruleset_name}"
        screen.blit(font_small.render(mode_line, True, TEXT_DIM), (x, y))
        y += 24

        if self.time_remaining is not None:
            t_color = DANGER if self.time_remaining < 10 else TEXT
            screen.blit(font_mid.render(f"Time: {self.time_remaining:0.1f}s", True, t_color), (x, y))
            y += 30

        screen.blit(font_big.render(str(self.score), True, TEXT), (x, y))
        y += 42
        screen.blit(font_small.render("SCORE", True, TEXT_DIM), (x, y))
        y += 26

        high = max((s["score"] for s in self.data.get("high_scores", []) if s["mode"] == self.mode_name()), default=0)
        screen.blit(font_small.render(f"Best ({self.mode_name()}): {high}", True, TEXT_DIM), (x, y))
        y += 20
        screen.blit(font_tiny.render(f"Coins: {self.wallet}", True, GOLD), (x, y))
        y += 22

        combo_color = GOLD if self.combo >= 5 else TEXT
        screen.blit(font_small.render(f"Combo x{self.combo}", True, combo_color), (x, y))
        y += 20
        screen.blit(font_small.render(f"Length: {len(self.player.body)}", True, TEXT_DIM), (x, y))
        y += 20

        if self.ghost_trail:
            point = self.ghost_point()
            if point is not None:
                diff = self.score - point[2]
                if diff > 0:
                    ghost_text, ghost_color = f"Ghost: +{diff} ahead", GREEN
                elif diff < 0:
                    ghost_text, ghost_color = f"Ghost: {diff} behind", DANGER
                else:
                    ghost_text, ghost_color = "Ghost: dead even", TEXT_DIM
            else:
                ghost_text, ghost_color = f"Ghost done ({self.ghost_best_score})", TEXT_DIM
            screen.blit(font_tiny.render(ghost_text, True, ghost_color), (x, y))
            y += 20

        if self.match_size > 1:
            for i in range(self.match_size - 1, -1, -1):  # P2.. first, P1 last (unchanged order)
                snake = self.players[i]
                if snake is None:
                    continue
                alive = self.players_alive[i]
                status = "alive" if alive else "down"
                color = TEXT if alive else DANGER
                extra = f"  len {len(snake.body)}" if i > 0 else ""
                screen.blit(font_tiny.render(f"{PLAYER_LABELS[i]}: {status}{extra}", True, color), (x, y))
                y += 20

        if self.curse_timer > 0:
            screen.blit(font_tiny.render(f"CURSED: controls reversed! {self.curse_timer:0.1f}s", True, self.downerup_color(DOWNERUP_CURSE)), (x, y))
            y += 20

        y += 6
        if self.active_powerups:
            screen.blit(font_small.render("ACTIVE:", True, TEXT_DIM), (x, y))
            y += 18
            for kind, remaining in self.active_powerups.items():
                self._draw_powerup_icon(screen, kind, x + 7, y + 7, radius=7)
                screen.blit(font_tiny.render(f"{kind}  {remaining:0.1f}s", True, TEXT), (x + 20, y))
                y += 18
            y += 6

        y = SCREEN_H - 130
        if self.lan_role:
            y -= 16
        screen.blit(font_tiny.render("Arrows/WASD/hjkl  |  P pause", True, TEXT_DIM), (x, y)); y += 16
        screen.blit(font_tiny.render(self._hint("M mute  |  Esc menu"), True, TEXT_DIM), (x, y)); y += 16
        if self.lan_role:
            hint_color = GOLD if self.chat_unread else TEXT_DIM
            screen.blit(font_tiny.render(self._chat_hint(), True, hint_color), (x, y)); y += 16
        mute_state = "muted" if self.sounds.muted else f"{round(self.sounds.master_volume * 100)}%"
        screen.blit(font_tiny.render(f"Volume: {mute_state}", True, TEXT_DIM), (x, y)); y += 20

        legend = [
            (self._draw_food_icon, FOOD_NORMAL, "Food"),
            (self._draw_food_icon, FOOD_GOLDEN, "Golden (+50)"),
            (self._draw_downerup_icon, DOWNERUP_CURSE, "Curse (reversed!)"),
            (self._draw_downerup_icon, DOWNERUP_BOMB, "Bomb (danger!)"),
        ]
        for draw_fn, kind, label in legend:
            draw_fn(screen, kind, x + 6, y + 6, radius=6)
            screen.blit(font_tiny.render(label, True, TEXT_DIM), (x + 18, y - 4))
            y += 15

        ty = 10
        for title, subtitle, life in self.toast_queue[:3]:
            alpha_t = min(1.0, life)
            s = gfx.surface((220, 46), pygame.SRCALPHA)
            gfx.draw.rect(s, (30, 30, 45, int(220 * alpha_t)), s.get_rect(), border_radius=8)
            gfx.draw.rect(s, (*GOLD, int(255 * alpha_t)), s.get_rect(), width=2, border_radius=8)
            s.blit(font_tiny.render(title, True, GOLD), (10, 6))
            s.blit(font_small.render(subtitle, True, TEXT), (10, 22))
            screen.blit(s, (GRID_W * CELL_SIZE - 230, ty))
            ty += 52

    def draw_menu_snake(self, y_center: int) -> None:
        t = pygame.time.get_ticks() / 1000.0
        skin = SNAKE_SKINS[SKIN_NAMES[self.skin_idx]]
        segs = 14
        for i in range(segs):
            x = ((t * 80 - i * 20) % (SCREEN_W + 200)) - 100
            y = y_center + 8 * (i % 2 == 0 and 1 or -1) * abs((((t * 2 - i * 0.3) % 2) - 1))
            color = skin[0] if i == 0 else skin[1]
            gfx.draw.circle(screen, color, (int(x), int(y)), 6)

    def _draw_menu_title(self) -> int:
        """A quiet, letter-spaced wordmark with thin ornaments, in the same visual language as the
        menu selector. Returns the y just below it."""
        letters = [font_title.render(ch, True, ACCENT) for ch in "MEGA SNAKE"]
        shadows = [font_title.render(ch, True, (4, 6, 10)) for ch in "MEGA SNAKE"]
        gap = 9
        total = sum(l.get_width() for l in letters) + gap * (len(letters) - 1)
        x, y = SCREEN_W // 2 - total // 2, 22
        for l, sh in zip(letters, shadows):
            screen.blit(sh, (x + 2, y + 3))
            screen.blit(l, (x, y))
            x += l.get_width() + gap
        ly = y + font_title.get_height() + 6
        cx = SCREEN_W // 2
        for side in (-1, 1):
            for i in range(110):
                a = int(150 * (1 - i / 110) ** 1.5)
                gfx.draw.line(screen, tuple(int(c * a / 255 + 10 * (1 - a / 255)) for c in ACCENT),
                              (cx + side * (14 + i), ly), (cx + side * (15 + i), ly), 1)
        gfx.draw.polygon(screen, ACCENT, [(cx, ly - 5), (cx + 5, ly), (cx, ly + 5), (cx - 5, ly)])
        return ly + 10

    def draw_menu(self) -> None:
        self._draw_backdrop(0.35)
        self.draw_menu_snake(SCREEN_H - 24)
        sub_y = self._draw_menu_title()
        sub = font_small.render(f"snake, but with way too many features  (v{GAME_VERSION})", True, TEXT)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, sub_y))

        wallet_r = font_small.render(f"Coins: {self.wallet}", True, GOLD)
        screen.blit(wallet_r, (18, 18))
        if self.streak_count > 0:
            streak_r = font_small.render(f"Streak: {self.streak_count} day{'s' if self.streak_count != 1 else ''}", True, ACCENT)
            screen.blit(streak_r, (18, 40))

        done, total = self._quest_progress()
        labels = {
            "Mode": f"Mode:  < {self.mode_name()} >",
            "Skin": f"Skin:  < {SKIN_NAMES[self.skin_idx]} >",
            "Daily Quests": f"Daily Quests  ({done}/{total})",
        }
        items = [labels.get(name, name) for name in MENU_ITEMS]
        start_y = sub_y + 30
        line_h = 24
        row_x = SCREEN_W // 2 - 180
        panel = gfx.surface((340, len(items) * line_h + 14), pygame.SRCALPHA)
        gfx.draw.rect(panel, (6, 9, 16, 170), panel.get_rect(), border_radius=14)
        screen.blit(panel, (SCREEN_W // 2 - 170, start_y - 8))
        for i, item in enumerate(items):
            selected = i == self.menu_index
            color = ACCENT if selected else TEXT
            prefix = "  "
            text = font_small.render(item, True, color)
            tx = SCREEN_W // 2 - text.get_width() // 2
            screen.blit(text, (tx, start_y + i * line_h))
            name = MENU_ITEMS[i]
            row = pygame.Rect(SCREEN_W // 2 - 130, start_y + i * line_h - 2, 260, line_h)
            if name in ("Mode", "Skin"):
                step = (lambda d, name=name: self._cycle_menu_choice(name, d))
                ui.draw_row_highlight(screen, row, selected)
                self._hot(row, "menu_index", i, lambda step=step: step(1), step)
                head, value = item.split("<")[0], "<" + item.split("<", 1)[1]
                self._arrow_hots("menu_index", i, font_small, tx, row.y, row.h, head, value, step)
            else:
                self._list_row(row, "menu_index", i)

        desc = MODE_DESC[self.mode_name()]
        desc_r = font_tiny.render(desc, True, TEXT_DIM)
        screen.blit(desc_r, (SCREEN_W // 2 - desc_r.get_width() // 2, start_y + len(items) * line_h + 8))

        skin_name = SKIN_NAMES[self.skin_idx]
        skin_colors = SNAKE_SKINS[skin_name]
        py = start_y + len(items) * line_h + 28
        for i in range(6):
            color = skin_colors[0] if i == 0 else skin_colors[1]
            r = pygame.Rect(SCREEN_W // 2 - 60 + i * 22, py, 16, 16)
            gfx.draw.rect(screen, color, r, border_radius=5)

        foot = font_tiny.render("Click to choose   Wheel or < > to change Mode/Skin   (or Up/Down + Enter)",
                                True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def _cycle_menu_choice(self, name: str, direction: int) -> None:
        if name == "Mode":
            self.mode_idx = (self.mode_idx + direction) % len(MODES)
        else:
            self.cycle_skin(direction)
        self.sounds.play(self.sounds.menu_move)

    def _chat_hint(self) -> str:
        if self.chat_unread:
            return f"T: chat ({self.chat_unread} new)"
        return "T: chat"

    def draw_paused(self) -> None:
        overlay = gfx.surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        screen.blit(overlay, (0, 0))

        if self.lan_role == "client":
            t = font_big.render("HOST PAUSED", True, TEXT)
            screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, SCREEN_H // 2 - 60))
            sub = font_small.render("Waiting for the host to resume...", True, TEXT_DIM)
            screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, SCREEN_H // 2 - 10))
            s = font_tiny.render(f"Esc: leave game   {self._chat_hint()}", True, TEXT_DIM)
            screen.blit(s, (SCREEN_W // 2 - s.get_width() // 2, SCREEN_H // 2 + 40))
            self._button(pygame.Rect(SCREEN_W // 2 - 100, SCREEN_H // 2 + 70, 200, 38), "Leave Game",
                         lambda: self._press(pygame.K_ESCAPE))
            if self.chat_active:
                self._draw_chat_panel()
            return

        t = font_big.render("PAUSED", True, TEXT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, SCREEN_H // 2 - 130))

        items = self._pause_items()
        for i, item in enumerate(items):
            selected = i == self.pause_index
            color = ACCENT if selected else TEXT
            prefix = "  "
            text = font_mid.render(item, True, color)
            screen.blit(text, (SCREEN_W // 2 - text.get_width() // 2, SCREEN_H // 2 - 50 + i * 40))
            self._list_row(pygame.Rect(SCREEN_W // 2 - 130, SCREEN_H // 2 - 54 + i * 40, 260, 38),
                           "pause_index", i)

        if self.lan_role == "host":
            note = font_tiny.render("Your friend also sees PAUSED while you're here.", True, TEXT_DIM)
            screen.blit(note, (SCREEN_W // 2 - note.get_width() // 2, SCREEN_H // 2 - 50 + len(items) * 40 + 6))

        s = font_tiny.render(self._hint(f"Click to choose   Right-click or P to resume   Esc menu   {self._chat_hint()}"), True, TEXT_DIM)
        screen.blit(s, (SCREEN_W // 2 - s.get_width() // 2, SCREEN_H // 2 + 130))

        if self.chat_active:
            self._draw_chat_panel()

    def _safe_render_chat(self, text: str, color) -> pygame.Surface:
        """font_chat is just the game's own, already-proven-everywhere font
        now (see its comment) - no emoji/Unicode font-picking left to go
        wrong, and _clean_chat_text() restricts input to printable ASCII
        before it ever reaches here. This still can't ever raise, as a last
        line of defense."""
        try:
            return font_chat.render(text or " ", True, color)
        except (pygame.error, UnicodeError):
            cleaned = "".join(ch if ch.isascii() else "?" for ch in text)
            try:
                return font_chat.render(cleaned or "?", True, color)
            except (pygame.error, UnicodeError):
                return font_chat.render("?", True, color)

    def _draw_chat_panel(self) -> None:
        # Narrow enough, still centered like the rest of the pause screen, to
        # stay inside the play area instead of bleeding under the sidebar.
        panel_w, panel_h = 480, 260
        px = SCREEN_W // 2 - panel_w // 2
        py = SCREEN_H // 2 - panel_h // 2 + 40
        panel = gfx.surface((panel_w, panel_h), pygame.SRCALPHA)
        gfx.draw.rect(panel, (16, 17, 24, 235), (0, 0, panel_w, panel_h), border_radius=10)
        gfx.draw.rect(panel, ACCENT, (0, 0, panel_w, panel_h), width=2, border_radius=10)
        screen.blit(panel, (px, py))

        label = font_tiny.render("CHAT", True, ACCENT)
        screen.blit(label, (px + 14, py + 10))

        log_y = py + 34
        log_h = panel_h - 34 - 44
        visible = self.chat_log[-CHAT_VISIBLE:]
        # Bottom-anchored so the newest message always sits just above the input box.
        y = log_y + log_h - 22
        for who, text in reversed(visible):
            color = ACCENT if who == "You" else GOLD
            prefix = self._safe_render_chat(f"{who}:", color)
            line = self._safe_render_chat(text, TEXT)
            avail = panel_w - 14 - prefix.get_width() - 6 - 14
            if line.get_width() > avail > 0:
                clipped = gfx.surface((avail, line.get_height()), pygame.SRCALPHA)
                clipped.blit(line, (0, 0))
                line = clipped
            screen.blit(prefix, (px + 14, y))
            screen.blit(line, (px + 14 + prefix.get_width() + 6, y))
            y -= 22
            if y < log_y:
                break

        box_y = py + panel_h - 36
        box = pygame.Rect(px + 12, box_y, panel_w - 24, 28)
        gfx.draw.rect(screen, (28, 30, 40), box, border_radius=6)
        gfx.draw.rect(screen, (70, 74, 92), box, width=1, border_radius=6)
        cursor = "|" if (pygame.time.get_ticks() // 500) % 2 == 0 else ""
        shown = self.chat_input + cursor
        inp = self._safe_render_chat(shown or " ", TEXT)
        # Horizontal scroll: keep the tail visible once typing outgrows the box.
        avail = box.width - 12
        if inp.get_width() > avail:
            clip = gfx.surface((avail, inp.get_height()), pygame.SRCALPHA)
            clip.blit(inp, (avail - inp.get_width(), 0))
            inp = clip
        screen.blit(inp, (box.x + 6, box.y + box.height // 2 - inp.get_height() // 2))

        foot = font_tiny.render(f"Enter send ({CHAT_MAX_LEN - len(self.chat_input)} left)   Esc close", True, TEXT_DIM)
        screen.blit(foot, (px + panel_w - foot.get_width() - 14, py + 10))

    def draw_game_over(self) -> None:
        self._draw_backdrop()
        t = font_big.render("GAME OVER", True, DANGER)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 40))
        r = font_small.render(self.game_over_reason, True, TEXT_DIM)
        screen.blit(r, (SCREEN_W // 2 - r.get_width() // 2, 84))

        left_x = SCREEN_W // 2 - 260
        right_x = SCREEN_W // 2 + 20
        y0 = 130

        stats_lines = [
            f"Score: {self.final_stats.get('score', 0)}",
            f"Food eaten: {self.final_stats.get('food_eaten', 0)}",
            f"Golden apples: {self.final_stats.get('golden_eaten', 0)}",
            f"Max length: {self.final_stats.get('length', 0)}",
            f"Time alive: {self.final_stats.get('time_alive', 0):.1f}s",
        ]
        y = y0
        screen.blit(font_small.render("RUN STATS", True, ACCENT), (left_x, y)); y += 26
        for line in stats_lines:
            text = font_small.render(line, True, TEXT)
            screen.blit(text, (left_x, y))
            y += 26

        bd = self.score_breakdown
        y = y0
        screen.blit(font_small.render("SCORE BREAKDOWN", True, ACCENT), (right_x, y)); y += 26
        breakdown_lines = [
            f"Normal food:   +{bd['normal']}",
            f"Golden bonus:  +{bd['golden']}",
            f"2x multiplier: +{bd['mult_bonus']}",
            f"Penalties:     {bd['penalty']}",
        ]
        for line in breakdown_lines:
            text = font_small.render(line, True, TEXT)
            screen.blit(text, (right_x, y))
            y += 26
        total = bd["normal"] + bd["golden"] + bd["mult_bonus"] + bd["penalty"]
        text = font_small.render(f"Total: {total}", True, GOLD)
        screen.blit(text, (right_x, y + 6))

        coin_y = y0 + 5 * 26 + 46
        coin_line = f"Coins earned: +{self.run_coins_earned}"
        if self.run_streak_bonus:
            coin_line += f"   Streak bonus: +{self.run_streak_bonus} ({self.streak_count} day streak)"
        coin_line += f"   Wallet: {self.wallet}"
        coin_text = font_small.render(coin_line, True, GOLD)
        screen.blit(coin_text, (SCREEN_W // 2 - coin_text.get_width() // 2, coin_y))

        extra_y = coin_y + 30
        for desc, reward in self.run_quest_rewards:
            q_text = font_small.render(f"Quest complete: {desc}  +{reward} coins", True, GREEN)
            screen.blit(q_text, (SCREEN_W // 2 - q_text.get_width() // 2, extra_y))
            extra_y += 22
        if self.run_new_ghost:
            g_text = font_small.render(f"New ghost recorded for {self.mode_name()} - race it next time!", True, ACCENT)
            screen.blit(g_text, (SCREEN_W // 2 - g_text.get_width() // 2, extra_y))

        if self.run_new_achievements:
            extra_y += 22
            shown = ", ".join(self.run_new_achievements[:3])
            more = len(self.run_new_achievements) - 3
            a_text = font_small.render(
                f"Achievement{'s' if len(self.run_new_achievements) != 1 else ''} unlocked: {shown}"
                + (f" +{more} more" if more > 0 else ""), True, GOLD)
            screen.blit(a_text, (SCREEN_W // 2 - a_text.get_width() // 2, extra_y))

        if self.lan_role:
            self._button(pygame.Rect(SCREEN_W // 2 - 110, SCREEN_H - 58, 220, 40), "Leave Match",
                         lambda: self._press(pygame.K_RETURN), primary=True, font=font_small)
        else:
            self._button(pygame.Rect(SCREEN_W // 2 - 230, SCREEN_H - 58, 220, 40), "Play Again",
                         lambda: self._press(pygame.K_RETURN), primary=True, font=font_small)
            self._button(pygame.Rect(SCREEN_W // 2 + 10, SCREEN_H - 58, 220, 40), "Main Menu",
                         lambda: self._press(pygame.K_ESCAPE), font=font_small)

    def draw_leaderboard(self) -> None:
        self._draw_backdrop()
        self._draw_back_button()
        t = font_big.render("LEADERBOARD", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 40))
        scores = self.data.get("high_scores", [])
        y = 110
        if not scores:
            s = font_small.render("No scores yet. Go play!", True, TEXT_DIM)
            screen.blit(s, (SCREEN_W // 2 - s.get_width() // 2, y))
        for i, entry in enumerate(scores[:12]):
            initials = entry.get("initials", "---")
            line = f"{i + 1:>2}.  {initials:<4} {entry['score']:<6}  {entry['mode']:<9}  {entry['date']}"
            color = GOLD if i == 0 else TEXT
            text = font_small.render(line, True, color)
            screen.blit(text, (SCREEN_W // 2 - 190, y))
            y += 26
        foot = font_small.render(self._hint("Esc: back"), True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def draw_enter_initials(self) -> None:
        self._draw_backdrop()
        t = font_big.render("NEW HIGH SCORE!", True, GOLD)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 140))

        entry = self.pending_score_entry or {}
        sub = font_mid.render(f"{entry.get('score', self.score)} pts  -  {entry.get('mode', self.mode_name())}", True, TEXT)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 200))

        box_w, gap = 56, 16
        total_w = box_w * 3 + gap * 2
        start_x = SCREEN_W // 2 - total_w // 2
        y = 260
        for i, letter in enumerate(self.pending_initials):
            x = start_x + i * (box_w + gap)
            selected = i == self.initials_cursor
            color = ACCENT if selected else TEXT_DIM
            rect = pygame.Rect(x, y, box_w, box_w)
            gfx.draw.rect(screen, (30, 32, 42), rect, border_radius=8)
            gfx.draw.rect(screen, color, rect, width=3, border_radius=8)
            letter_r = font_big.render(letter, True, TEXT)
            screen.blit(letter_r, (x + box_w // 2 - letter_r.get_width() // 2, y + box_w // 2 - letter_r.get_height() // 2))
            self._hot(rect, "initials_cursor", i, adjust=lambda d, i=i: self._initial_step(i, d))
            up = pygame.Rect(x, y - 26, box_w, 22)
            down = pygame.Rect(x, y + box_w + 4, box_w, 22)
            col = ACCENT if ui.hovered(up) else TEXT_DIM
            gfx.draw.polygon(screen, col, [(up.centerx - 8, up.bottom - 5), (up.centerx + 8, up.bottom - 5), (up.centerx, up.y + 4)])
            col = ACCENT if ui.hovered(down) else TEXT_DIM
            gfx.draw.polygon(screen, col, [(down.centerx - 8, down.y + 5), (down.centerx + 8, down.y + 5), (down.centerx, down.bottom - 4)])
            self._hot(up, "initials_cursor", i, lambda i=i: self._initial_step(i, 1))
            self._hot(down, "initials_cursor", i, lambda i=i: self._initial_step(i, -1))

        foot = font_small.render("Click a letter, use the arrows or scroll   Enter: confirm", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, y + box_w + 40))
        self._button(pygame.Rect(SCREEN_W // 2 - 90, y + box_w + 74, 180, 40), "Confirm",
                     lambda: self._press(pygame.K_RETURN), primary=True, font=font_small)

    def _initial_step(self, i: int, direction: int) -> None:
        self.initials_cursor = i
        idx = (LETTERS.index(self.pending_initials[i]) + direction) % len(LETTERS)
        self.pending_initials[i] = LETTERS[idx]
        self.sounds.play(self.sounds.menu_move)

    ACH_FILTERS = ["All", "Unlocked", "Locked"]
    ACH_CARD_H = 58
    ACH_GAP = 6

    def _ach_visible(self) -> list:
        unlocked = self.tracker.unlocked
        mode = self.ACH_FILTERS[self.ach_filter]
        return [a for a in ACHIEVEMENTS
                if mode == "All" or (mode == "Unlocked") == (a.id in unlocked)]

    def _ach_layout(self) -> Tuple[pygame.Rect, float]:
        """The scrolling list's viewport and the total height of its content."""
        view = pygame.Rect(30, 118, SCREEN_W - 60 - 18, SCREEN_H - 118 - 46)
        rows = (len(self._ach_visible()) + 1) // 2
        return view, max(0, rows * (self.ACH_CARD_H + self.ACH_GAP) - self.ACH_GAP)

    def _ach_scroll_by(self, delta: float) -> None:
        view, content_h = self._ach_layout()
        self.ach_scroll = max(0.0, min(max(0.0, content_h - view.h), self.ach_scroll + delta))

    def _set_ach_filter(self, i: int) -> None:
        self.ach_filter = i
        self.ach_scroll = 0.0
        self.sounds.play(self.sounds.menu_move)

    def draw_achievements(self) -> None:
        self._draw_backdrop()
        t = font_big.render("ACHIEVEMENTS", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 24))
        self._draw_back_button()

        unlocked = self.tracker.unlocked
        stat_bests = self.data.get("stat_bests", {})
        skin_for = {req: name for name, req in SKIN_UNLOCK_REQUIREMENT.items() if req}

        # Filter tabs with live counts.
        counts = [len(ACHIEVEMENTS), len(unlocked), len(ACHIEVEMENTS) - len(unlocked)]
        tab_w, gap = 140, 8
        x = SCREEN_W // 2 - (3 * tab_w + 2 * gap) // 2
        for i, name in enumerate(self.ACH_FILTERS):
            rect = pygame.Rect(x + i * (tab_w + gap), 76, tab_w, 30)
            active = i == self.ach_filter
            gfx.draw.rect(screen, ui.PANEL_HOVER if (active or ui.hovered(rect)) else ui.PANEL, rect, border_radius=8)
            if active:
                gfx.draw.rect(screen, ACCENT, (rect.x + 10, rect.bottom - 3, rect.w - 20, 3), border_radius=2)
            lbl = font_small.render(f"{name} ({counts[i]})", True, TEXT if active else TEXT_DIM)
            screen.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.centery - lbl.get_height() // 2 - 1))
            self._hot(rect, click=lambda i=i: self._set_ach_filter(i))

        view, content_h = self._ach_layout()
        self._ach_scroll_by(0)  # re-clamp after a filter change shrinks the list
        cols = 2
        card_w = (view.w - 12) // cols
        step_y = self.ACH_CARD_H + self.ACH_GAP
        self._hot(view, adjust=lambda d: self._ach_scroll_by(-d * step_y))

        screen.set_clip(view)
        for i, ach in enumerate(self._ach_visible()):
            card = pygame.Rect(view.x + (i % cols) * (card_w + 12),
                               view.y + (i // cols) * step_y - int(self.ach_scroll), card_w, self.ACH_CARD_H)
            if card.bottom < view.top or card.top > view.bottom:
                continue
            got = ach.id in unlocked
            over = ui.hovered(card) and view.collidepoint(gfx.mouse_pos())
            gfx.draw.rect(screen, ui.PANEL_HOVER if over else ui.PANEL, card, border_radius=8)
            if got:
                gfx.draw.rect(screen, GREEN, (card.x, card.y + 6, 3, card.h - 12), border_radius=2)
            secret = ach.hidden and not got
            name = font_small.render(f"{'[x]' if got else '[ ]'} {'???' if secret else ach.name}", True,
                                     GREEN if got else TEXT)
            screen.blit(name, (card.x + 12, card.y + 4))
            skin = skin_for.get(ach.id)
            if skin and not secret:
                reward = font_tiny.render(f"Unlocks {skin} skin", True, GOLD if got else TEXT_DIM)
                screen.blit(reward, (card.right - reward.get_width() - 10, card.y + 7))
            desc = font_tiny.render("Hidden achievement" if secret else ach.description, True, TEXT_DIM)
            screen.blit(desc, (card.x + 28, card.y + 26))

            if ach.stat_key and ach.target and not secret:
                bar_w, bar_h = card.w - 100, 5
                bar_x, bar_y = card.x + 28, card.y + 47
                best_val = stat_bests.get(ach.stat_key, 0)
                progress = 1.0 if got else min(1.0, best_val / ach.target)
                gfx.draw.rect(screen, (40, 42, 54), (bar_x, bar_y, bar_w, bar_h), border_radius=3)
                if progress > 0:
                    gfx.draw.rect(screen, GOLD if got else ACCENT, (bar_x, bar_y, int(bar_w * progress), bar_h),
                                     border_radius=3)
                val_str = f"{int(min(best_val, ach.target))}/{int(ach.target)}"
                val_r = font_tiny.render(val_str, True, TEXT_DIM)
                screen.blit(val_r, (bar_x + bar_w + 8, bar_y - 8))
        screen.set_clip(None)

        if not self._ach_visible():
            empty = font_small.render("Nothing here yet - go earn some!", True, TEXT_DIM)
            screen.blit(empty, (view.centerx - empty.get_width() // 2, view.y + 40))

        track = pygame.Rect(view.right + 4, view.y, 10, view.h)
        thumb = ui.draw_scrollbar(screen, track, self.ach_scroll, content_h, view.h)
        if content_h > view.h:
            span = max(1, track.h - thumb.h)
            self._hot(track.inflate(10, 0), drag=lambda pos: self._ach_scroll_by(
                (pos[1] - track.y - thumb.h / 2) / span * (content_h - view.h) - self.ach_scroll))

        pct = int(100 * len(unlocked) / len(ACHIEVEMENTS))
        foot = font_small.render(f"{len(unlocked)}/{len(ACHIEVEMENTS)} unlocked ({pct}%)", True, ACCENT)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 34))
        hint = font_tiny.render(self._hint("Scroll or drag the bar   Right-click: back"), True, TEXT_DIM)
        screen.blit(hint, (SCREEN_W - hint.get_width() - 20, SCREEN_H - 30))

    def draw_shop(self) -> None:
        self._draw_backdrop()
        t = font_big.render("SHOP", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 40))
        wallet_r = font_mid.render(f"Wallet: {self.wallet} coins", True, GOLD)
        screen.blit(wallet_r, (SCREEN_W // 2 - wallet_r.get_width() // 2, 90))
        hint_r = font_tiny.render("Trails leave a glowing streak behind your snake for the whole run.", True, TEXT_DIM)
        screen.blit(hint_r, (SCREEN_W // 2 - hint_r.get_width() // 2, 124))

        items = TRAIL_NAMES + ["Back"]
        y = 150
        for i, name in enumerate(items):
            selected = i == self.shop_index
            prefix = "  "
            row = pygame.Rect(SCREEN_W // 2 - 230, y - 4, 560, 40)
            self._list_row(row, "shop_index", i)
            if name == "Back":
                color = ACCENT if selected else TEXT
                screen.blit(font_mid.render(prefix + "Back", True, color), (SCREEN_W // 2 - 200, y))
                y += 44
                continue

            spec = TRAIL_EFFECTS[name]
            owned = name in self.owned_trails
            equipped = name == self.equipped_trail
            if equipped:
                status = "[EQUIPPED]"
                status_color = GREEN
            elif owned:
                status = "[owned - Enter to equip]"
                status_color = TEXT_DIM
            else:
                status = f"[{spec['cost']} coins - Enter to buy]"
                status_color = GOLD if self.wallet >= spec["cost"] else DANGER

            color = ACCENT if selected else TEXT
            label = font_mid.render(f"{prefix}{name}", True, color)
            screen.blit(label, (SCREEN_W // 2 - 200, y))

            cx = SCREEN_W // 2 + 60
            if spec["color"] == "rainbow":
                t_anim = pygame.time.get_ticks() / 1000.0
                hue = (t_anim * 0.3) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
                gfx.draw.circle(screen, (int(r * 255), int(g * 255), int(b * 255)), (cx, y + 12), 9)
            elif spec["color"] is not None:
                gfx.draw.circle(screen, spec["color"], (cx, y + 12), 9)
            else:
                gfx.draw.circle(screen, (90, 90, 100), (cx, y + 12), 9, width=2)

            status_r = font_tiny.render(status, True, status_color)
            screen.blit(status_r, (SCREEN_W // 2 + 90, y + 6))
            y += 44

        foot = font_tiny.render("Click a trail to buy or equip it   Right-click: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))
        self._draw_back_button()

    def draw_lan_menu(self) -> None:
        self._draw_backdrop()
        t = font_big.render("MULTIPLAYER", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 50))
        sub = [
            "LAN: same Wi-Fi/network, join by IP.",
            "Online: anywhere with internet, join by room code.",
        ]
        y = 100
        for line in sub:
            r = font_small.render(line, True, TEXT_DIM)
            screen.blit(r, (SCREEN_W // 2 - r.get_width() // 2, y))
            y += 22

        y = 170
        for i, item in enumerate(LAN_MENU_ITEMS):
            selected = i == self.lan_menu_index
            color = ACCENT if selected else TEXT
            prefix = "  "
            text = font_mid.render(item, True, color)
            screen.blit(text, (SCREEN_W // 2 - text.get_width() // 2, y))
            self._list_row(pygame.Rect(SCREEN_W // 2 - 150, y - 4, 300, 38), "lan_menu_index", i)
            y += 44

        if self.local_ip:
            ip_r = font_small.render(f"Your LAN IP: {self.local_ip}", True, TEXT_DIM)
            screen.blit(ip_r, (SCREEN_W // 2 - ip_r.get_width() // 2, SCREEN_H - 60))

        foot = font_tiny.render("Click to choose   Right-click: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))
        self._draw_back_button()

    def draw_lan_host_wait(self) -> None:
        self._draw_backdrop()
        dots = "." * (1 + int(pygame.time.get_ticks() / 400) % 3)
        is_host = self.lan_role != "client"
        label = "HOSTING ONLINE" if (is_host and self.lan_online) else ("HOSTING" if is_host else "JOINED")
        t = font_big.render(label, True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 90))

        if is_host:
            if self.lan_online:
                code = self.lan_host.code if self.lan_host else None
                if code:
                    code_r = font_big.render(f"Room code:  {code}", True, GOLD)
                    share = "Send this code to friends - up to 3 can join (Join Online Game)."
                else:
                    code_r = font_mid.render(f"Creating room{dots}", True, GOLD)
                    share = "Connecting to the online server."
                screen.blit(code_r, (SCREEN_W // 2 - code_r.get_width() // 2, 150))
            else:
                ip_r = font_mid.render(f"IP: {self.local_ip}   Port: {network.DEFAULT_PORT}", True, GOLD)
                screen.blit(ip_r, (SCREEN_W // 2 - ip_r.get_width() // 2, 150))
                share = "Share this with friends on your network - up to 3 can join."
            share_r = font_small.render(share, True, TEXT_DIM)
            screen.blit(share_r, (SCREEN_W // 2 - share_r.get_width() // 2, 190))
        else:
            waiting_r = font_mid.render(f"Waiting for the host to start{dots}", True, TEXT)
            screen.blit(waiting_r, (SCREEN_W // 2 - waiting_r.get_width() // 2, 160))

        setup_r = font_small.render(f"Ruleset: {self.lan_ruleset_name}   Map: {self.map_name}", True, TEXT)
        screen.blit(setup_r, (SCREEN_W // 2 - setup_r.get_width() // 2, 220))

        y = 260
        if is_host:
            # The host's channel always knows the real roster (LAN tracks it
            # directly; Online gets it from the relay).
            channel = self.lan_host.link if self.lan_online else self.lan_host
            roster = dict(channel.roster) if channel else {"host": True}
            roster_label = font_small.render("Players:", True, TEXT_DIM)
            screen.blit(roster_label, (SCREEN_W // 2 - 90, y))
            y += 26
            for slot in ["host"] + network.GUEST_SLOTS:
                if slot not in roster:
                    continue
                up = roster[slot]
                tag = " (you)" if slot == "host" else ""
                color = TEXT if up else TEXT_DIM
                row = font_small.render(f"  {SLOT_LABEL[slot]}{tag} - {'connected' if up else 'reconnecting...'}", True, color)
                screen.blit(row, (SCREEN_W // 2 - 90, y))
                y += 24
            ready = len(roster) > 1
            hint = "Ready - start the match!" if ready else "Waiting for at least one player..."
            hint_r = font_mid.render(hint, True, GOLD if ready else TEXT_DIM)
            screen.blit(hint_r, (SCREEN_W // 2 - hint_r.get_width() // 2, y + 10))
        elif self.lan_online:
            # Online guests DO get the real roster from the relay.
            roster = dict(self.lan_link.roster) if self.lan_link else {}
            for slot in ["host"] + network.GUEST_SLOTS:
                if slot not in roster:
                    continue
                me = getattr(self.lan_link, "my_slot", None) == slot
                row = font_small.render(f"  {SLOT_LABEL[slot]}{' (you)' if me else ''}", True, TEXT)
                screen.blit(row, (SCREEN_W // 2 - 90, y))
                y += 24
        else:
            # A LAN guest's own socket has no visibility into who ELSE has
            # joined (unlike the host, or Online where the relay tells
            # everyone) - say so rather than guess.
            note = font_tiny.render("(other players may have joined too - the host can see everyone)", True, TEXT_DIM)
            screen.blit(note, (SCREEN_W // 2 - note.get_width() // 2, y))

        if self.lan_toast and pygame.time.get_ticks() / 1000.0 < self.lan_toast_until:
            toast_r = font_tiny.render(self.lan_toast, True, DANGER)
            screen.blit(toast_r, (SCREEN_W // 2 - toast_r.get_width() // 2, SCREEN_H - 90))

        if is_host:
            channel = self.lan_host.link if self.lan_online else self.lan_host
            ready = bool(channel and len(channel.roster) > 1)
            self._button(pygame.Rect(SCREEN_W // 2 - 230, SCREEN_H - 62, 220, 40), "Start Match",
                         lambda: self._press(pygame.K_RETURN), primary=True, enabled=ready, font=font_small)
            self._button(pygame.Rect(SCREEN_W // 2 + 10, SCREEN_H - 62, 220, 40), "Cancel",
                         lambda: self._press(pygame.K_ESCAPE), font=font_small)
        else:
            self._button(pygame.Rect(SCREEN_W // 2 - 110, SCREEN_H - 62, 220, 40), "Leave",
                         lambda: self._press(pygame.K_ESCAPE), font=font_small)

    def draw_lan_setup(self) -> None:
        self._draw_backdrop()
        t = font_big.render("MATCH SETUP", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 60))

        # Live selection, not the "committed" self.lan_ruleset_name/map_name
        # (those only update when Start Hosting is actually pressed) - this
        # screen must reflect whatever's currently highlighted as you browse.
        live_ruleset = LAN_RULESET_NAMES[self.lan_ruleset_idx]
        live_map = MAP_NAMES[self.map_idx]

        values = [
            f"< {live_ruleset} >",
            f"< {live_map} >",
            "",
        ]
        y = 150
        for i, label in enumerate(LAN_SETUP_ITEMS):
            selected = i == self.lan_setup_index
            color = ACCENT if selected else TEXT
            prefix = "  "
            line = f"{prefix}{label}"
            if values[i]:
                line += "  " + values[i]
            text = font_mid.render(line, True, color)
            screen.blit(text, (SCREEN_W // 2 - 160, y))
            row = pygame.Rect(SCREEN_W // 2 - 190, y - 4, 420, 40)
            if values[i]:
                ui.draw_row_highlight(screen, row, selected)
                self._hot(row, "lan_setup_index", i, lambda: self._step_key(1), self._step_key)
                self._arrow_hots("lan_setup_index", i, font_mid, SCREEN_W // 2 - 160, row.y, row.h,
                                 f"{prefix}{label}  ", values[i], self._step_key)
            else:
                self._list_row(row, "lan_setup_index", i)
            y += 44

        desc = LAN_RULESETS[live_ruleset]["desc"]
        desc_r = font_small.render(desc, True, TEXT_DIM)
        screen.blit(desc_r, (SCREEN_W // 2 - desc_r.get_width() // 2, y + 10))

        self._draw_map_preview(live_map, y + 34)

        foot = font_tiny.render("Click or scroll to change   Right-click: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 20))
        self._draw_back_button()

    def _draw_map_preview(self, map_name: str, y: int) -> None:
        """Shared by the LAN Match Setup and local Coop map-select screens:
        obstacle count line + a tiny themed preview of the layout."""
        theme = MAP_THEMES.get(map_name, DEFAULT_THEME)
        obstacle_count = len(MAPS[map_name])
        map_r = font_small.render(
            f"{obstacle_count} obstacle{'s' if obstacle_count != 1 else ''} on this map" if obstacle_count else "No obstacles on this map",
            True, TEXT_DIM,
        )
        screen.blit(map_r, (SCREEN_W // 2 - map_r.get_width() // 2, y))

        preview_w, preview_h = 220, 150
        px0 = SCREEN_W // 2 - preview_w // 2
        py0 = y + 32
        bg = theme.get("bg_tint") or (24, 26, 36)
        gfx.draw.rect(screen, bg, (px0, py0, preview_w, preview_h), border_radius=6)
        gfx.draw.rect(screen, (48, 52, 66), (px0, py0, preview_w, preview_h), width=1, border_radius=6)
        sx, sy = preview_w / GRID_W, preview_h / GRID_H
        obstacle_color = theme.get("obstacle_color", DEFAULT_THEME["obstacle_color"])
        for (ox, oy) in MAPS[map_name]:
            gfx.draw.rect(screen, obstacle_color, (px0 + ox * sx, py0 + oy * sy, max(2, sx), max(2, sy)))
        spawn_xs = (GRID_W // 2, GRID_W // 2 - 6) if MODE_CONFIG[self.mode_name()]["coop"] else (GRID_W // 2,)
        for hx in spawn_xs:
            gfx.draw.circle(screen, GREEN, (int(px0 + hx * sx), int(py0 + GRID_H // 2 * sy)), 3)

    def draw_map_select(self) -> None:
        self._draw_backdrop()
        t = font_big.render("CHOOSE A MAP", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 50))
        if MODE_CONFIG[self.mode_name()]["coop"]:
            sub_text = f"{self.mode_name()} - arrows/hjkl move P1, WASD moves P2"
        else:
            sub_text = f"{self.mode_name()} - {MODE_DESC[self.mode_name()]}"
        sub = font_small.render(sub_text, True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 96))

        live_map = MAP_NAMES[self.map_idx]
        items = [f"< {live_map} >", ""]
        y = 150
        for i, label in enumerate(MAP_SETUP_ITEMS):
            selected = i == self.map_setup_index
            color = ACCENT if selected else TEXT
            prefix = "  "
            line = f"{prefix}{label}"
            if items[i]:
                line += "  " + items[i]
            text = font_mid.render(line, True, color)
            screen.blit(text, (SCREEN_W // 2 - 160, y))
            row = pygame.Rect(SCREEN_W // 2 - 190, y - 4, 420, 40)
            if items[i]:
                ui.draw_row_highlight(screen, row, selected)
                self._hot(row, "map_setup_index", i, lambda: self._step_key(1), self._step_key)
                self._arrow_hots("map_setup_index", i, font_mid, SCREEN_W // 2 - 160, row.y, row.h,
                                 f"{prefix}{label}  ", items[i], self._step_key)
            else:
                self._list_row(row, "map_setup_index", i)
            y += 44

        self._draw_map_preview(live_map, y + 10)

        foot = font_tiny.render("Click or scroll to change the map   Right-click: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 20))
        self._draw_back_button()

    def draw_lan_join_ip(self) -> None:
        self._draw_backdrop()
        t = font_big.render("JOIN GAME", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 100))
        sub = font_small.render("Enter the host's LAN IP address:", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 170))

        cursor = "_" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
        box_w = 280
        rect = pygame.Rect(SCREEN_W // 2 - box_w // 2, 220, box_w, 50)
        gfx.draw.rect(screen, (30, 32, 42), rect, border_radius=8)
        gfx.draw.rect(screen, ACCENT, rect, width=2, border_radius=8)
        ip_r = font_mid.render(self.lan_ip_input + cursor, True, TEXT)
        screen.blit(ip_r, (rect.x + 14, rect.y + 12))

        self._button(pygame.Rect(SCREEN_W // 2 - 90, 300, 180, 40), "Connect",
                     lambda: self._press(pygame.K_RETURN), primary=True, enabled=bool(self.lan_ip_input),
                     font=font_small)
        self._draw_back_button()
        foot = font_tiny.render("Type IP   Enter connect   Backspace delete   Esc / right-click: cancel", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_online_join_code(self) -> None:
        self._draw_backdrop()
        t = font_big.render("JOIN ONLINE", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 100))
        sub = font_small.render("Enter the room code from the host:", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 170))

        box_w, box_h, gap = 52, 60, 12
        total = network.ROOM_CODE_LEN * box_w + (network.ROOM_CODE_LEN - 1) * gap
        x0 = SCREEN_W // 2 - total // 2
        blink = (pygame.time.get_ticks() // 500) % 2 == 0
        for i in range(network.ROOM_CODE_LEN):
            rect = pygame.Rect(x0 + i * (box_w + gap), 215, box_w, box_h)
            active = i == len(self.online_code_input)
            gfx.draw.rect(screen, (30, 32, 42), rect, border_radius=8)
            gfx.draw.rect(screen, ACCENT if active else (60, 64, 80), rect, width=2, border_radius=8)
            ch = self.online_code_input[i] if i < len(self.online_code_input) else ("_" if active and blink else "")
            if ch:
                r = font_big.render(ch, True, TEXT)
                screen.blit(r, (rect.centerx - r.get_width() // 2, rect.centery - r.get_height() // 2))

        self._button(pygame.Rect(SCREEN_W // 2 - 90, 300, 180, 40), "Join",
                     lambda: self._press(pygame.K_RETURN), primary=True,
                     enabled=len(self.online_code_input) == network.ROOM_CODE_LEN, font=font_small)
        self._draw_back_button()
        foot = font_tiny.render("Type code   Enter join   Backspace delete   Esc / right-click: cancel", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def _draw_net_banner(self) -> None:
        issue = self._net_issue()
        if not issue:
            return
        play_w = GRID_W * CELL_SIZE
        overlay = gfx.surface((play_w, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))
        dots = "." * (1 + int(pygame.time.get_ticks() / 400) % 3)
        r = font_mid.render(issue.rstrip(".") + dots, True, GOLD)
        screen.blit(r, (play_w // 2 - r.get_width() // 2, SCREEN_H // 2 - 20))
        hint = font_tiny.render("The match is frozen until the connection is back.", True, TEXT_DIM)
        screen.blit(hint, (play_w // 2 - hint.get_width() // 2, SCREEN_H // 2 + 16))

    def draw_lan_connecting(self) -> None:
        self._draw_backdrop()
        t = font_big.render("CONNECTING", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 140))
        target = self.lan_client.label if self.lan_client else self.lan_connect_label
        dots = "." * (1 + int(pygame.time.get_ticks() / 400) % 3)
        sub = font_mid.render(f"Connecting to {target}{dots}", True, TEXT)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 210))
        self._button(pygame.Rect(SCREEN_W // 2 - 90, SCREEN_H - 90, 180, 38), "Cancel",
                     lambda: self._press(pygame.K_ESCAPE), font=font_small)
        foot = font_small.render("Esc: cancel", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def draw_lan_error(self) -> None:
        self._draw_backdrop()
        t = font_big.render("CONNECTION ERROR", True, DANGER)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 160))
        msg_r = font_small.render(str(self.lan_error_msg), True, TEXT)
        screen.blit(msg_r, (SCREEN_W // 2 - msg_r.get_width() // 2, 220))
        self._button(pygame.Rect(SCREEN_W // 2 - 90, SCREEN_H - 90, 180, 38), "OK",
                     lambda: self._press(pygame.K_RETURN), primary=True, font=font_small)
        foot = font_small.render(self._hint("Enter / Esc: back"), True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def _settings_rows(self) -> List[SettingDef]:
        return [d for d in SETTING_DEFS if d.tab == SETTING_TABS[self.settings_tab]]

    def _slider_to(self, d: SettingDef, track: pygame.Rect, mx: int) -> None:
        frac = max(0.0, min(1.0, (mx - track.x) / track.w))
        val = round((d.lo + frac * (d.hi - d.lo)) / d.step) * d.step
        val = max(d.lo, min(d.hi, val))
        if val != self.setting_get(d.key):
            self.setting_set(d.key, val, save=False)

    def _set_settings_tab(self, i: int) -> None:
        self.settings_tab = i % len(SETTING_TABS)
        self.settings_index = 0
        self.sounds.play(self.sounds.menu_move)

    def draw_settings(self) -> None:
        self._draw_backdrop()
        t = font_big.render("SETTINGS", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 30))
        self._draw_back_button()

        tab_w, tab_h, gap = 150, 32, 8
        x = SCREEN_W // 2 - (len(SETTING_TABS) * tab_w + (len(SETTING_TABS) - 1) * gap) // 2
        for i, name in enumerate(SETTING_TABS):
            rect = pygame.Rect(x + i * (tab_w + gap), 88, tab_w, tab_h)
            active = i == self.settings_tab
            over = ui.hovered(rect)
            gfx.draw.rect(screen, ui.PANEL_HOVER if (active or over) else ui.PANEL, rect, border_radius=8)
            if active:
                gfx.draw.rect(screen, ACCENT, (rect.x + 10, rect.bottom - 3, rect.w - 20, 3), border_radius=2)
            label = font_small.render(name, True, TEXT if active else TEXT_DIM)
            screen.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2 - 1))
            self._hot(rect, click=lambda i=i: self._set_settings_tab(i))

        rows = self._settings_rows()
        self.settings_index = min(self.settings_index, len(rows) - 1)
        x0, w, rh = SCREEN_W // 2 - 330, 660, 40
        for i, d in enumerate(rows):
            rect = pygame.Rect(x0, 134 + i * rh, w, rh - 4)
            ui.draw_row_highlight(screen, rect, i == self.settings_index)
            step = lambda direction, d=d: self.setting_step(d, direction)
            toggle_on_click = (lambda d=d: self.setting_step(d, 1)) if d.kind == "toggle" else None
            self._hot(rect, "settings_index", i, toggle_on_click, step)
            screen.blit(font_mid.render(d.label, True, TEXT), (rect.x + 16, rect.centery - 14))

            val = self.setting_get(d.key)
            right = rect.right - 16
            if d.kind == "toggle":
                sw = pygame.Rect(right - 46, rect.centery - 11, 46, 22)
                ui.draw_toggle(screen, sw, bool(val))
                lbl = font_small.render("On" if val else "Off", True, ACCENT if val else TEXT_DIM)
                screen.blit(lbl, (sw.x - 12 - lbl.get_width(), rect.centery - lbl.get_height() // 2))
            elif d.kind == "slider":
                lbl = font_small.render(f"{val}{d.unit}", True, TEXT)
                screen.blit(lbl, (right - lbl.get_width(), rect.centery - lbl.get_height() // 2))
                track = pygame.Rect(right - 70 - 220, rect.centery - 4, 220, 8)
                ui.draw_slider(screen, track, (val - d.lo) / (d.hi - d.lo), self.drag_hot is not None)
                self._hot(track.inflate(18, 24), "settings_index", i,
                          drag=lambda pos, d=d, tr=track: self._slider_to(d, tr, pos[0]), adjust=step)
            else:
                seg_w = min(82, 400 // len(d.options))
                for j, opt in enumerate(reversed(d.options)):
                    seg = pygame.Rect(right - (j + 1) * seg_w - j * 4, rect.centery - 15, seg_w, 30)
                    on = opt == val
                    gfx.draw.rect(screen, ACCENT if on else (ui.PANEL_HOVER if ui.hovered(seg) else ui.PANEL),
                                     seg, border_radius=7)
                    lbl = font_small.render(opt, True, (14, 16, 22) if on else TEXT_DIM)
                    screen.blit(lbl, (seg.centerx - lbl.get_width() // 2, seg.centery - lbl.get_height() // 2))
                    self._hot(seg, "settings_index", i, lambda d=d, opt=opt: self.setting_set(d.key, opt), step)

        hint = rows[self.settings_index].hint
        if hint:
            h = font_small.render(hint, True, TEXT_DIM)
            screen.blit(h, (SCREEN_W // 2 - h.get_width() // 2, SCREEN_H - 58))
        foot = font_tiny.render(self._hint("Click, drag or scroll to change   Tab: next tab   F11: fullscreen   Esc / right-click: back"),
                                True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 28))

    def draw_stats(self) -> None:
        self._draw_backdrop()
        self._draw_back_button()
        t = font_big.render("STATS", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 40))

        scores = self.data.get("high_scores", [])
        best_overall = max((s["score"] for s in scores), default=0)
        mode_counts: Dict[str, int] = {}
        for s in scores:
            mode_counts[s["mode"]] = mode_counts.get(s["mode"], 0) + 1
        favorite = max(mode_counts, key=mode_counts.get) if mode_counts else "-"

        done, total = self._quest_progress()
        lines = [
            f"Games played: {self.data.get('games_played', 0)}",
            f"Total food eaten: {self.data.get('total_food_eaten', 0)}",
            f"Best score overall: {best_overall}",
            f"Favorite mode: {favorite}",
            f"Achievements: {len(self.tracker.unlocked)}/{len(ACHIEVEMENTS)}",
            f"Quests today: {done}/{total}",
        ]
        left_x = 70
        y = 100
        for line in lines:
            text = font_small.render(line, True, TEXT)
            screen.blit(text, (left_x, y))
            y += 26

        y += 12
        screen.blit(font_small.render("BEST PER MODE", True, ACCENT), (left_x, y))
        y += 26
        for mode in MODES:
            best = max((s["score"] for s in scores if s["mode"] == mode), default=None)
            text = font_small.render(f"{mode:<10} {best if best is not None else '-'}", True, TEXT_DIM)
            screen.blit(text, (left_x, y))
            y += 22

        self._draw_run_history_chart(530, 100, 430, 220)

        foot = font_small.render(self._hint("Esc: back"), True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def _draw_run_history_chart(self, x: int, y: int, w: int, h: int) -> None:
        """Single-series bar chart of the last 20 runs, oldest to newest."""
        screen.blit(font_small.render("LAST 20 RUNS", True, ACCENT), (x, y))
        history = self.data.get("run_history", [])[-20:]
        plot_top = y + 34
        plot_h = h - 34 - 22
        baseline = plot_top + plot_h
        gfx.draw.line(screen, (48, 52, 66), (x, baseline), (x + w, baseline), 1)

        if not history:
            msg = font_tiny.render("No runs yet - go play!", True, TEXT_DIM)
            screen.blit(msg, (x + w // 2 - msg.get_width() // 2, plot_top + plot_h // 2 - 8))
            return

        max_score = max(1, max(r["score"] for r in history))
        slot = w / 20
        bar_w = max(4, int(slot) - 2)  # 2px surface gap between adjacent bars
        best_i = max(range(len(history)), key=lambda i: history[i]["score"])
        bar_color = (43, 149, 208)

        for i, run in enumerate(history):
            bx = x + int(i * slot)
            bh = int(plot_h * run["score"] / max_score)
            if bh > 0:
                rect = pygame.Rect(bx, baseline - bh, bar_w, bh)
                gfx.draw.rect(screen, bar_color, rect,
                                 border_top_left_radius=min(4, bh), border_top_right_radius=min(4, bh))
            if i == best_i or i == len(history) - 1:
                label = font_tiny.render(str(run["score"]), True, TEXT if i == best_i else TEXT_DIM)
                lx = bx + bar_w // 2 - label.get_width() // 2
                screen.blit(label, (lx, baseline - bh - 16))

        axis = font_tiny.render("oldest", True, TEXT_DIM)
        screen.blit(axis, (x, baseline + 6))
        axis = font_tiny.render("newest", True, TEXT_DIM)
        screen.blit(axis, (x + w - axis.get_width(), baseline + 6))

        avg = sum(r["score"] for r in history) / len(history)
        summary = font_tiny.render(f"Average: {avg:.0f}   Best shown: {history[best_i]['score']} ({history[best_i]['mode']})", True, TEXT_DIM)
        screen.blit(summary, (x, baseline + 26))

    def draw_changelog(self) -> None:
        self._draw_backdrop()
        self._draw_back_button()
        t = font_big.render("CHANGELOG", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 30))
        y = 84
        limit = SCREEN_H - 40
        for version, entries in CHANGELOG:
            block_h = 26 + len(entries) * 20 + 10
            if y + block_h > limit:
                older = font_tiny.render("... older versions omitted", True, TEXT_DIM)
                screen.blit(older, (SCREEN_W // 2 - 260, y))
                break
            screen.blit(font_mid.render(f"v{version}", True, GOLD), (SCREEN_W // 2 - 260, y))
            y += 26
            for entry in entries:
                screen.blit(font_tiny.render(f"- {entry}", True, TEXT), (SCREEN_W // 2 - 240, y))
                y += 20
            y += 10
        foot = font_small.render(self._hint("Esc: back"), True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def _draw_food_icon(self, surface: pygame.Surface, kind: str, cx: float, cy: float, radius: float = 7) -> None:
        """Food/power-up/downerup icons are drawn with simple vector shapes
        (no image assets) so each kind reads as the thing it represents even
        at cell size - an apple, a star, a bolt, a bomb - instead of a plain
        colored circle or square. Same shapes are used on the board and in
        the small HUD/legend/how-to-play dots, just at a different radius."""
        if self._sprite_icon(surface, f"food_{kind}", cx, cy, radius):
            return
        color = self.food_color(kind)
        cx, cy = int(cx), int(cy)
        if kind == FOOD_NORMAL:
            gfx.draw.circle(surface, color, (cx, cy + int(radius * 0.1)), int(radius))
            gfx.draw.line(surface, (120, 80, 40), (cx, cy - int(radius)),
                              (cx + int(radius * 0.35), cy - int(radius * 1.35)), max(1, int(radius * 0.22)))
            leaf = [(cx + radius * 0.3, cy - radius * 1.1), (cx + radius * 0.95, cy - radius * 1.25),
                    (cx + radius * 0.45, cy - radius * 0.7)]
            gfx.draw.polygon(surface, (90, 200, 90), leaf)
        elif kind == FOOD_GOLDEN:
            outer = self._star_points(cx, cy, radius * 1.15, radius * 0.45)
            gfx.draw.polygon(surface, color, outer)
            gfx.draw.polygon(surface, (255, 255, 230), outer, 1)
        elif kind == FOOD_SPEED:
            bolt = [
                (cx + radius * 0.15, cy - radius * 1.1), (cx - radius * 0.55, cy + radius * 0.15),
                (cx - radius * 0.05, cy + radius * 0.15), (cx - radius * 0.3, cy + radius * 1.1),
                (cx + radius * 0.55, cy - radius * 0.1), (cx + radius * 0.05, cy - radius * 0.1),
            ]
            gfx.draw.polygon(surface, color, bolt)
        elif kind == FOOD_SHRINK:
            neck = (cx - radius * 0.22, cy - radius * 1.1, radius * 0.44, radius * 0.5)
            gfx.draw.rect(surface, color, neck)
            gfx.draw.circle(surface, color, (cx, cy + int(radius * 0.15)), int(radius * 0.8))
            gfx.draw.rect(surface, (255, 255, 255), neck, 1)
            gfx.draw.circle(surface, (255, 255, 255), (cx, cy + int(radius * 0.15)), int(radius * 0.8), 1)

    @staticmethod
    def _star_points(cx: float, cy: float, outer: float, inner: float, n: int = 5) -> List[Tuple[float, float]]:
        pts = []
        rot = -math.pi / 2
        for i in range(n * 2):
            ang = rot + i * math.pi / n
            rad = outer if i % 2 == 0 else inner
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        return pts

    def _draw_downerup_icon(self, surface: pygame.Surface, kind: str, cx: float, cy: float, radius: float = 7) -> None:
        if self._sprite_icon(surface, f"hz_{kind}", cx, cy, radius):
            return
        color = self.downerup_color(kind)
        cx, cy = int(cx), int(cy)
        if kind == DOWNERUP_BOMB:
            gfx.draw.circle(surface, color, (cx, cy + int(radius * 0.15)), int(radius * 0.85))
            gfx.draw.circle(surface, (90, 90, 95), (cx - int(radius * 0.3), cy - int(radius * 0.1)),
                                max(1, int(radius * 0.22)))
            fuse_end = (cx + int(radius * 0.6), cy - int(radius * 1.1))
            gfx.draw.line(surface, (150, 100, 50), (cx + int(radius * 0.3), cy - int(radius * 0.6)),
                              fuse_end, max(1, int(radius * 0.18)))
            gfx.draw.circle(surface, (255, 200, 60), fuse_end, max(2, int(radius * 0.22)))
        elif kind == DOWNERUP_CURSE:
            gfx.draw.circle(surface, color, (cx, cy), int(radius))
            skull = (235, 235, 245)
            gfx.draw.circle(surface, skull, (cx, cy - int(radius * 0.2)), int(radius * 0.52))
            gfx.draw.rect(surface, skull, (cx - radius * 0.32, cy + radius * 0.05, radius * 0.64, radius * 0.3),
                              border_radius=max(1, int(radius * 0.1)))
            eye_r = max(1, int(radius * 0.13))
            gfx.draw.circle(surface, color, (cx - int(radius * 0.2), cy - int(radius * 0.22)), eye_r)
            gfx.draw.circle(surface, color, (cx + int(radius * 0.2), cy - int(radius * 0.22)), eye_r)

    def _draw_powerup_icon(self, surface: pygame.Surface, kind: str, cx: float, cy: float, radius: float = 7) -> None:
        if self._sprite_icon(surface, POWERUP_SPRITES.get(kind, ""), cx, cy, radius):
            return
        color = self.powerup_color(kind)
        cx, cy = int(cx), int(cy)
        if kind == POWERUP_GHOST:
            top_cy = cy - radius * 0.15
            dome = [(cx + radius * 0.75 * math.cos(math.radians(a)), top_cy + radius * 0.75 * math.sin(math.radians(a)))
                    for a in range(180, 361, 30)]
            bottom_y = cy + radius * 0.75
            right_x, left_x = cx + radius * 0.75, cx - radius * 0.75
            scallop = [
                (right_x, bottom_y - radius * 0.3), (right_x - radius * 0.5, bottom_y),
                (cx + radius * 0.25, bottom_y - radius * 0.3), (cx - radius * 0.25, bottom_y),
                (left_x + radius * 0.5, bottom_y - radius * 0.3), (left_x, bottom_y),
            ]
            gfx.draw.polygon(surface, color, dome + scallop)
            eye = (40, 40, 60)
            gfx.draw.circle(surface, eye, (cx - int(radius * 0.28), cy - int(radius * 0.1)), max(1, int(radius * 0.15)))
            gfx.draw.circle(surface, eye, (cx + int(radius * 0.28), cy - int(radius * 0.1)), max(1, int(radius * 0.15)))
        elif kind == POWERUP_MAGNET:
            leg_w = max(2, int(radius * 0.32))
            top_y = cy - radius * 0.9
            bottom_y = cy + radius * 0.15
            left_x = cx - radius * 0.5
            right_x = cx + radius * 0.5 - leg_w
            gfx.draw.rect(surface, color, (left_x, top_y, leg_w, bottom_y - top_y), border_radius=leg_w // 2)
            gfx.draw.rect(surface, color, (right_x, top_y, leg_w, bottom_y - top_y), border_radius=leg_w // 2)
            arc_rect = (left_x, cy - radius * 0.45, right_x + leg_w - left_x, radius * 1.1)
            gfx.draw.arc(surface, color, arc_rect, math.pi, 2 * math.pi, leg_w)
            tip = (235, 235, 245)
            tip_h = max(2, int(radius * 0.3))
            gfx.draw.rect(surface, tip, (left_x, top_y, leg_w, tip_h))
            gfx.draw.rect(surface, tip, (right_x, top_y, leg_w, tip_h))
        elif kind == POWERUP_SHIELD:
            pts = [
                (cx - radius * 0.8, cy - radius * 0.7), (cx + radius * 0.8, cy - radius * 0.7),
                (cx + radius * 0.7, cy + radius * 0.15), (cx, cy + radius), (cx - radius * 0.7, cy + radius * 0.15),
            ]
            gfx.draw.polygon(surface, color, pts)
            w = max(1, int(radius * 0.16))
            gfx.draw.line(surface, (255, 255, 255), (cx, cy - radius * 0.35), (cx, cy + radius * 0.35), w)
            gfx.draw.line(surface, (255, 255, 255), (cx - radius * 0.3, cy), (cx + radius * 0.3, cy), w)
        elif kind == POWERUP_SLOWMO:
            gfx.draw.circle(surface, color, (cx, cy), int(radius * 0.85), max(1, int(radius * 0.18)))
            gfx.draw.line(surface, color, (cx, cy), (cx, cy - radius * 0.5), max(1, int(radius * 0.16)))
            gfx.draw.line(surface, color, (cx, cy), (cx + radius * 0.35, cy + radius * 0.15), max(1, int(radius * 0.16)))
        elif kind == POWERUP_MULT:
            gfx.draw.circle(surface, color, (cx, cy), int(radius * 0.9))
            label = _icon_font(max(8, int(radius * 1.3))).render("x2", True, (30, 25, 15))
            surface.blit(label, (cx - label.get_width() // 2, cy - label.get_height() // 2))
        elif kind == POWERUP_FREEZE:
            for ang_deg in range(0, 360, 60):
                ang = math.radians(ang_deg)
                dx, dy = math.cos(ang), math.sin(ang)
                end = (cx + radius * 0.9 * dx, cy + radius * 0.9 * dy)
                gfx.draw.line(surface, color, (cx, cy), end, max(1, int(radius * 0.16)))
                bx, by = cx + radius * 0.55 * dx, cy + radius * 0.55 * dy
                perp = ang + math.pi / 2
                pdx, pdy = math.cos(perp) * radius * 0.22, math.sin(perp) * radius * 0.22
                gfx.draw.line(surface, color, (bx - pdx, by - pdy), (bx + pdx, by + pdy), max(1, int(radius * 0.12)))
        elif kind == POWERUP_TELEPORT:
            for frac in (1.0, 0.6, 0.25):
                gfx.draw.circle(surface, color, (cx, cy), max(1, int(radius * frac)), 1)
        elif kind == POWERUP_REVIVE:
            lobe_r = max(1, int(radius * 0.45))
            gfx.draw.circle(surface, color, (cx - int(radius * 0.35), cy - int(radius * 0.2)), lobe_r)
            gfx.draw.circle(surface, color, (cx + int(radius * 0.35), cy - int(radius * 0.2)), lobe_r)
            pts = [(cx - radius * 0.8, cy - radius * 0.05), (cx, cy + radius * 0.9), (cx + radius * 0.8, cy - radius * 0.05)]
            gfx.draw.polygon(surface, color, pts)

    def draw_howto(self) -> None:
        self._draw_backdrop()
        self._draw_back_button()
        t = font_big.render("HOW TO PLAY", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 24))

        left_x, right_x = 60, 540
        y = 84
        screen.blit(font_small.render("CONTROLS", True, ACCENT), (left_x, y)); y += 24
        for line in [
            "Arrows / WASD / hjkl   move",
            "P   pause      M   mute      Esc   menu",
            "Coop: P1 = Arrows/hjkl, P2 = WASD",
        ]:
            screen.blit(font_tiny.render(line, True, TEXT), (left_x, y)); y += 18

        y += 14
        screen.blit(font_small.render("FOOD", True, ACCENT), (left_x, y)); y += 24
        foods = [
            (FOOD_NORMAL, "Food: +10 x combo, grow 1"),
            (FOOD_GOLDEN, "Golden: +50, grow 1"),
            (FOOD_SPEED, "Speed: +10, 4s speed boost"),
            (FOOD_SHRINK, "Shrink: lose 2 length, -5"),
        ]
        for kind, desc in foods:
            self._draw_food_icon(screen, kind, left_x + 8, y + 8)
            screen.blit(font_tiny.render(desc, True, TEXT), (left_x + 24, y + 1))
            y += 22

        y += 14
        screen.blit(font_small.render("DOWNERUPS", True, ACCENT), (left_x, y)); y += 24
        downerups = [
            (DOWNERUP_CURSE, "Curse (X): every move you make, you'll make in reverse, 4.5s"),
            (DOWNERUP_BOMB, "Bomb (ring): instant death unless shielded"),
        ]
        for kind, desc in downerups:
            self._draw_downerup_icon(screen, kind, left_x + 8, y + 8)
            screen.blit(font_tiny.render(desc, True, TEXT), (left_x + 24, y + 1))
            y += 22

        y += 14
        screen.blit(font_small.render("TIPS", True, ACCENT), (left_x, y)); y += 24
        for line in [
            "Eat again within 2.6s to build your combo (max x20).",
            "Portals warp your whole snake to the other ring.",
            "The faint ring is your ghost: your best run in this mode.",
            "Red edges = a wall is close (non-wrap modes).",
        ]:
            screen.blit(font_tiny.render(line, True, TEXT_DIM), (left_x, y)); y += 18

        y = 84
        screen.blit(font_small.render("POWER-UPS", True, ACCENT), (right_x, y)); y += 24
        powerups = [
            (POWERUP_GHOST, "Ghost: pass through walls & yourself (6s)"),
            (POWERUP_MAGNET, "Magnet: auto-eat food within 3 tiles (8s)"),
            (POWERUP_SHIELD, "Shield: survive one fatal hit (12s)"),
            (POWERUP_SLOWMO, "Slow-mo: everything slows down (5s)"),
            (POWERUP_MULT, "2x: double score (10s)"),
            (POWERUP_FREEZE, "Freeze: rival snakes stop (6s)"),
            (POWERUP_TELEPORT, "Teleport: instantly eat the nearest food"),
            (POWERUP_REVIVE, "Revive: brings your Coop/LAN teammate back (only spawns when they're down)"),
        ]
        for kind, desc in powerups:
            self._draw_powerup_icon(screen, kind, right_x + 8, y + 8)
            screen.blit(font_tiny.render(desc, True, TEXT), (right_x + 24, y + 1))
            y += 22

        y += 14
        screen.blit(font_small.render("MODES", True, ACCENT), (right_x, y)); y += 24
        for mode in MODES:
            screen.blit(font_tiny.render(f"{mode:<9} {MODE_DESC[mode]}", True, TEXT_DIM), (right_x, y)); y += 18

        foot = font_small.render(self._hint("Esc: back"), True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_quests(self) -> None:
        self._draw_backdrop()
        self._draw_back_button()
        t = font_big.render("DAILY QUESTS", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 60))

        today_iso = datetime.date.today().isoformat()
        sub = font_small.render(f"{today_iso}  -  new quests every day at midnight", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 110))

        q = self.data.get("quests", {})
        completed = q.get("completed", []) if q.get("date") == today_iso else []

        card_w, card_h = 560, 70
        x = SCREEN_W // 2 - card_w // 2
        y = 160
        for quest in quests_for_date(today_iso):
            done = quest.id in completed
            rect = pygame.Rect(x, y, card_w, card_h)
            gfx.draw.rect(screen, (26, 29, 40), rect, border_radius=10)
            gfx.draw.rect(screen, GREEN if done else (48, 52, 66), rect, width=2, border_radius=10)
            screen.blit(font_mid.render(quest.description, True, TEXT if not done else TEXT_DIM), (x + 20, y + 14))
            status = font_small.render("DONE" if done else f"+{quest.reward} coins", True, GREEN if done else GOLD)
            screen.blit(status, (x + card_w - status.get_width() - 20, y + 42))
            y += card_h + 16

        note = font_tiny.render("Quests are checked when a run ends. Each pays out once per day.", True, TEXT_DIM)
        screen.blit(note, (SCREEN_W // 2 - note.get_width() // 2, y + 6))

        foot = font_small.render(self._hint("Esc: back"), True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def _draw_progress_bar(self, frac: float, y: int, label: str) -> None:
        bar_w, bar_h = 420, 22
        x = SCREEN_W // 2 - bar_w // 2
        gfx.draw.rect(screen, (30, 32, 42), (x, y, bar_w, bar_h), border_radius=6)
        fill_w = int(bar_w * max(0.0, min(1.0, frac)))
        if fill_w > 0:
            gfx.draw.rect(screen, ACCENT, (x, y, fill_w, bar_h), border_radius=6)
        gfx.draw.rect(screen, (60, 64, 80), (x, y, bar_w, bar_h), width=1, border_radius=6)
        pct = font_small.render(label, True, TEXT)
        screen.blit(pct, (SCREEN_W // 2 - pct.get_width() // 2, y + bar_h + 10))

    def draw_update_check(self) -> None:
        self._draw_backdrop()
        t = font_big.render("CHECKING FOR UPDATES", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 180))
        # Indeterminate-feeling fill: ramps toward ~92% while waiting on the
        # network call, then snaps to 100% the frame it actually completes.
        frac = min(0.92, self.update_check_anim) if not (self.update_checker and self.update_checker.done) else 1.0
        self._draw_progress_bar(frac, 250, f"{int(frac * 100)}% done")
        sub = font_small.render(f"Current version: v{GAME_VERSION}", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 310))

    def draw_update_prompt(self) -> None:
        self._draw_backdrop()
        t = font_big.render("UPDATE AVAILABLE", True, GOLD)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 70))

        sub = font_small.render("New updates:", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 130))

        y = 160
        last_idx = len(self.update_releases) - 1
        for i, rel in enumerate(self.update_releases):
            label = rel.tag if rel.tag.startswith("v") else f"v{rel.tag}"
            if i == last_idx:
                label += "  [latest]"
            color = GOLD if i == last_idx else TEXT
            line = font_mid.render(label, True, color)
            screen.blit(line, (SCREEN_W // 2 - line.get_width() // 2, y))
            y += 32

        q = font_mid.render("Do you want to update?", True, TEXT)
        screen.blit(q, (SCREEN_W // 2 - q.get_width() // 2, y + 20))

        options = ["YES", "NO"]
        ox = SCREEN_W // 2 - 90
        for i, label in enumerate(options):
            selected = i == self.update_choice_index
            color = ACCENT if selected else TEXT_DIM
            box = pygame.Rect(ox + i * 120, y + 64, 90, 40)
            gfx.draw.rect(screen, (30, 32, 42), box, border_radius=8)
            gfx.draw.rect(screen, color, box, width=2, border_radius=8)
            text = font_mid.render(label, True, color)
            screen.blit(text, (box.centerx - text.get_width() // 2, box.centery - text.get_height() // 2))
            self._hot(box, "update_choice_index", i, lambda: self._press(pygame.K_RETURN))

        foot = font_tiny.render("Click YES or NO   Esc / right-click: skip for now", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_update_none(self) -> None:
        self._draw_backdrop()
        t = font_big.render("UP TO DATE", True, GREEN)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 200))
        sub = font_small.render(f"You're on the latest version, v{GAME_VERSION}.", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 260))
        self._button(pygame.Rect(SCREEN_W // 2 - 90, SCREEN_H - 90, 180, 38), "OK",
                     lambda: self._press(pygame.K_RETURN), primary=True, font=font_small)
        foot = font_small.render(self._hint("Enter / Esc: back"), True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def draw_update_download(self) -> None:
        self._draw_backdrop()
        t = font_big.render("UPDATING", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 180))
        dl = self.update_downloader
        frac = dl.progress() if dl else 0.0
        if dl and dl.total:
            label = f"{int(frac * 100)}%  ({dl.received // 1024} / {dl.total // 1024} KB)"
        else:
            label = "Starting..."
        self._draw_progress_bar(frac, 250, label)
        sub = font_small.render("Downloading, then relaunching automatically...", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 310))

    def draw_update_error(self) -> None:
        self._draw_backdrop()
        t = font_big.render("UPDATE FAILED", True, DANGER)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 180))
        y = 240
        for line in textwrap.wrap(str(self.update_error_msg), 80) or [""]:
            msg = font_small.render(line, True, TEXT)
            screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, y))
            y += 24
        hint = font_tiny.render(f"You can always grab it manually from {updater.RELEASES_PAGE}", True, TEXT_DIM)
        screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, y + 8))
        self._button(pygame.Rect(SCREEN_W // 2 - 90, SCREEN_H - 90, 180, 38), "OK",
                     lambda: self._press(pygame.K_RETURN), primary=True, font=font_small)
        foot = font_small.render(self._hint("Enter / Esc: back"), True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def draw_easter_warning(self) -> None:
        warning = EASTER_WARNINGS[self.easter_stage]
        ox, oy = self.particles.get_shake_offset() if self.screen_shake_enabled else (0, 0)
        screen.fill((0, 0, 0))

        t = font_big.render(warning["title"], True, warning["color"])
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2 + ox, 190 + oy))

        y = 250 + oy
        for line in warning["lines"]:
            r = font_small.render(line, True, warning["color"])
            screen.blit(r, (SCREEN_W // 2 - r.get_width() // 2 + ox, y))
            y += 26

    def draw_secret_shop(self) -> None:
        t_anim = pygame.time.get_ticks() / 1000.0
        screen.fill((4, 2, 8))

        # A slow rainbow sweep across the whole backdrop.
        for i in range(0, SCREEN_W, 4):
            hue = ((i / SCREEN_W) + t_anim * 0.08) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 0.12)
            gfx.draw.line(screen, (int(r * 255), int(g * 255), int(b * 255)), (i, 0), (i, SCREEN_H))

        title_hue = (t_anim * 0.15) % 1.0
        tr, tg, tb = colorsys.hsv_to_rgb(title_hue, 0.7, 1.0)
        t = font_big.render("??? SHOP ???", True, (int(tr * 255), int(tg * 255), int(tb * 255)))
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 30))

        card_w, card_h, gap = 230, 110, 16
        cols = 3
        grid_w = cols * card_w + (cols - 1) * gap
        x0 = SCREEN_W // 2 - grid_w // 2
        y0 = 100
        for i, (name, price, desc) in enumerate(SECRET_SHOP_ITEMS):
            col, row = i % cols, i // cols
            x = x0 + col * (card_w + gap)
            y = y0 + row * (card_h + gap)
            hue = ((i / len(SECRET_SHOP_ITEMS)) + t_anim * 0.1) % 1.0
            cr, cg, cb = colorsys.hsv_to_rgb(hue, 0.6, 0.9)
            border = (int(cr * 255), int(cg * 255), int(cb * 255))

            rect = pygame.Rect(x, y, card_w, card_h)
            gfx.draw.rect(screen, (16, 14, 22), rect, border_radius=10)
            gfx.draw.rect(screen, border, rect, width=2, border_radius=10)
            name_r = font_small.render(name, True, TEXT)
            screen.blit(name_r, (x + 12, y + 10))
            price_r = font_tiny.render(price, True, border)
            screen.blit(price_r, (x + 12, y + 36))
            desc_r = font_tiny.render(desc, True, TEXT_DIM)
            screen.blit(desc_r, (x + 12, y + 60))
            # A simple drawn padlock instead of an emoji glyph, which several
            # of pygame's bundled fonts render as a fallback "tofu" box.
            lx, ly = x + card_w - 28, y + card_h - 26
            gfx.draw.rect(screen, TEXT_DIM, (lx, ly + 5, 14, 10), border_radius=2)
            gfx.draw.arc(screen, TEXT_DIM, (lx + 2, ly - 2, 10, 10), 3.14, 6.28, 2)

        note = font_small.render("There is nothing to buy here. There never was.", True, TEXT_DIM)
        screen.blit(note, (SCREEN_W // 2 - note.get_width() // 2, y0 + 2 * (card_h + gap) + 10))
        foot = font_tiny.render("Esc: leave", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 24))

        if pygame.time.get_ticks() < self.secret_shop_toast_until:
            ach = ACHIEVEMENTS_BY_ID["trespasser"]
            head = font_small.render("Achievement Unlocked!", True, GOLD)
            name_r = font_mid.render(ach.name, True, TEXT)
            w = max(head.get_width(), name_r.get_width()) + 40
            box = pygame.Rect(SCREEN_W // 2 - w // 2, SCREEN_H - 120, w, 70)
            gfx.draw.rect(screen, (16, 14, 22), box, border_radius=10)
            gfx.draw.rect(screen, GOLD, box, width=2, border_radius=10)
            screen.blit(head, (SCREEN_W // 2 - head.get_width() // 2, box.y + 8))
            screen.blit(name_r, (SCREEN_W // 2 - name_r.get_width() // 2, box.y + 32))

    # ---------- input ----------

    def handle_menu_key(self, key) -> None:
        n = len(MENU_ITEMS)
        # Easter egg: only the literal Down arrow counts (not the WASD "s"
        # alias) - any other key breaks the streak.
        # The streak has to run all the way to the last item and then
        # EASTER_EXTRA_PRESSES past it, measured from where it started.
        if key == pygame.K_DOWN:
            if self.easter_down_count == 0:
                self.easter_streak_start = self.menu_index
            self.easter_down_count += 1
            needed = (n - 1 - self.easter_streak_start) + EASTER_EXTRA_PRESSES
            if self.easter_down_count >= needed:
                self.easter_down_count = 0
                self.easter_stage = 0
                if self.data.get("secret_shop_found"):
                    self._enter_secret_shop()
                else:
                    self.state = STATE_EASTER_WARNING
                return
        else:
            self.easter_down_count = 0

        if key in (pygame.K_UP, pygame.K_w):
            self.menu_index = (self.menu_index - 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.menu_index = (self.menu_index + 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
            direction = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
            choice = MENU_ITEMS[self.menu_index]
            if choice == "Mode":
                self.mode_idx = (self.mode_idx + direction) % len(MODES)
                self.sounds.play(self.sounds.menu_move)
            elif choice == "Skin":
                self.cycle_skin(direction)
                self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_RETURN:
            self.sounds.play(self.sounds.menu_select)
            choice = MENU_ITEMS[self.menu_index]
            if choice == "Start Game":
                if self.mode_name() == "Daily":
                    # Daily is a fixed, date-seeded layout shared by everyone -
                    # no map picker, same contract as before.
                    self.reset_run()
                    self.state = STATE_PLAYING
                else:
                    self.map_setup_index = 0
                    self.state = STATE_MAP_SELECT
            elif choice == "Multiplayer":
                if self.local_ip is None:
                    self.local_ip = network.get_local_ip()
                self.lan_menu_index = 0
                self.state = STATE_LAN_MENU
            elif choice == "Daily Quests":
                self.state = STATE_QUESTS
            elif choice == "Shop":
                self.shop_index = 0
                self.state = STATE_SHOP
            elif choice == "Settings":
                self.prev_state = STATE_MENU
                self.settings_index = 0
                self.state = STATE_SETTINGS
            elif choice == "How to Play":
                self.state = STATE_HOWTO
            elif choice == "Stats":
                self.state = STATE_STATS
            elif choice == "Leaderboard":
                self.state = STATE_LEADERBOARD
            elif choice == "Achievements":
                self.state = STATE_ACHIEVEMENTS
            elif choice == "Changelog":
                self.state = STATE_CHANGELOG
            elif choice == "Check for Updates":
                self._start_update_check(silent=False)
            elif choice == "Quit":
                pygame.quit()
                sys.exit(0)

    def handle_update_prompt_key(self, key) -> None:
        if key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            self.update_choice_index = 1 - self.update_choice_index
            self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_RETURN:
            self.sounds.play(self.sounds.menu_select)
            if self.update_choice_index == 0:
                self._begin_update_download()
            else:
                self.state = STATE_MENU
        elif key == pygame.K_ESCAPE:
            self.state = STATE_MENU

    def handle_easter_warning_key(self, key) -> None:
        if key == pygame.K_DOWN:
            self.easter_stage += 1
            self.sounds.play(self.sounds.menu_select)
            if self.easter_stage >= len(EASTER_WARNINGS):
                self.easter_stage = 0
                self._enter_secret_shop()
            if self.screen_shake_enabled:
                self.particles.shake(0.3, 4 + self.easter_stage * 2)
        else:
            # Any other key loses your nerve - back to the menu, progress reset.
            self.easter_stage = 0
            self.easter_down_count = 0
            self.state = STATE_MENU

    def _enter_secret_shop(self) -> None:
        self.state = STATE_SECRET_SHOP
        self.data["secret_shop_found"] = True
        if "trespasser" not in self.tracker.unlocked:
            self.tracker.unlocked.add("trespasser")
            self.data["achievements"] = sorted(self.tracker.unlocked)
            self.sounds.play(self.sounds.achievement)
            self.secret_shop_toast_until = pygame.time.get_ticks() + 3500
        persistence.save(self.data)

    def handle_secret_shop_key(self, key) -> None:
        if key == pygame.K_ESCAPE:
            self.state = STATE_MENU
        # Every other key is intentionally ignored - there is genuinely
        # nothing to interact with in here.

    def handle_lan_menu_key(self, key) -> None:
        n = len(LAN_MENU_ITEMS)
        if key in (pygame.K_UP, pygame.K_w):
            self.lan_menu_index = (self.lan_menu_index - 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.lan_menu_index = (self.lan_menu_index + 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_ESCAPE:
            self.state = STATE_MENU
        elif key == pygame.K_RETURN:
            self.sounds.play(self.sounds.menu_select)
            choice = LAN_MENU_ITEMS[self.lan_menu_index]
            online = "Online" in choice
            if online and not self._online_server_url():
                self.lan_error_msg = "Online play isn't switched on in this version yet."
                self.state = STATE_LAN_ERROR
                return
            self.lan_online = online
            if choice in ("Host LAN Game", "Host Online Game"):
                self.lan_setup_index = 0
                self.state = STATE_LAN_SETUP
            elif choice == "Join LAN Game":
                self.lan_ip_input = ""
                self.state = STATE_LAN_JOIN_IP
            elif choice == "Join Online Game":
                self.online_code_input = ""
                self.state = STATE_ONLINE_JOIN_CODE
            elif choice == "Back":
                self.state = STATE_MENU

    def handle_lan_host_wait_key(self, key) -> None:
        """The lobby screen, shared by host and guest (see draw_lan_host_wait).
        The host can start once at least one guest has joined; a guest just
        waits here until the host does, or leaves."""
        if self.lan_role == "host":
            channel = self.lan_host.link if self.lan_online else self.lan_host
            if key == pygame.K_RETURN and channel and len(channel.roster) > 1:
                self.sounds.play(self.sounds.menu_select)
                match_size = len(channel.roster)
                channel.send({"type": "start"})
                self._lan_begin_session("host", match_size=match_size)
            elif key == pygame.K_ESCAPE:
                self._lan_teardown()
                self.lan_cfg_override = None
                self.state = STATE_LAN_MENU
        else:
            if key == pygame.K_ESCAPE:
                if self.lan_link:
                    self.lan_link.send({"type": "client_left"})
                self._lan_teardown()
                self.state = STATE_LAN_MENU

    def handle_lan_setup_key(self, key) -> None:
        n = len(LAN_SETUP_ITEMS)
        if key in (pygame.K_UP, pygame.K_w):
            self.lan_setup_index = (self.lan_setup_index - 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.lan_setup_index = (self.lan_setup_index + 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
            direction = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
            choice = LAN_SETUP_ITEMS[self.lan_setup_index]
            if choice == "Ruleset":
                self.lan_ruleset_idx = (self.lan_ruleset_idx + direction) % len(LAN_RULESET_NAMES)
                self.sounds.play(self.sounds.menu_move)
            elif choice == "Map":
                self.map_idx = (self.map_idx + direction) % len(MAP_NAMES)
                self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_RETURN:
            choice = LAN_SETUP_ITEMS[self.lan_setup_index]
            if choice == "Start Hosting":
                self.sounds.play(self.sounds.menu_select)
                self.lan_ruleset_name = LAN_RULESET_NAMES[self.lan_ruleset_idx]
                self.map_name = MAP_NAMES[self.map_idx]
                self.lan_cfg_override = dict(LAN_RULESETS[self.lan_ruleset_name])
                try:
                    if self.lan_online:
                        self.lan_host = network.OnlineHost(self._online_server_url(), GAME_VERSION)
                    else:
                        self.lan_host = network.Host()
                    self.state = STATE_LAN_HOST_WAIT
                except OSError as e:
                    self.lan_cfg_override = None
                    self.lan_error_msg = f"Could not start hosting: {e}"
                    self.state = STATE_LAN_ERROR
        elif key == pygame.K_ESCAPE:
            self.state = STATE_LAN_MENU

    def handle_map_select_key(self, key) -> None:
        n = len(MAP_SETUP_ITEMS)
        if key in (pygame.K_UP, pygame.K_w):
            self.map_setup_index = (self.map_setup_index - 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.map_setup_index = (self.map_setup_index + 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
            if MAP_SETUP_ITEMS[self.map_setup_index] == "Map":
                direction = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
                self.map_idx = (self.map_idx + direction) % len(MAP_NAMES)
                self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_RETURN:
            if MAP_SETUP_ITEMS[self.map_setup_index] == "Start Game":
                self.sounds.play(self.sounds.menu_select)
                self.map_name = MAP_NAMES[self.map_idx]
                self.reset_run()
                self.state = STATE_PLAYING
        elif key == pygame.K_ESCAPE:
            self.state = STATE_MENU

    def handle_lan_join_ip_key(self, key) -> None:
        if key == pygame.K_RETURN:
            if self.lan_ip_input:
                self.lan_client = network.Client(self.lan_ip_input)
                self.state = STATE_LAN_CONNECTING
        elif key == pygame.K_BACKSPACE:
            self.lan_ip_input = self.lan_ip_input[:-1]
        elif key == pygame.K_ESCAPE:
            self.state = STATE_LAN_MENU
        elif len(self.lan_ip_input) < 15:
            if pygame.K_0 <= key <= pygame.K_9:
                self.lan_ip_input += chr(key)
            elif key in (pygame.K_PERIOD, pygame.K_KP_PERIOD):
                self.lan_ip_input += "."

    def handle_online_join_code_key(self, key) -> None:
        if key == pygame.K_RETURN:
            if len(self.online_code_input) == network.ROOM_CODE_LEN:
                self.sounds.play(self.sounds.menu_select)
                self.lan_client = network.OnlineClient(
                    self._online_server_url(), self.online_code_input, GAME_VERSION)
                self.state = STATE_LAN_CONNECTING
        elif key == pygame.K_BACKSPACE:
            self.online_code_input = self.online_code_input[:-1]
        elif key == pygame.K_ESCAPE:
            self.state = STATE_LAN_MENU
        elif len(self.online_code_input) < network.ROOM_CODE_LEN:
            name = pygame.key.name(key)
            if len(name) == 1 and name.isalnum():
                ch = network.normalize_room_code(name)
                if ch in network.ROOM_CODE_CHARS:
                    self.online_code_input += ch

    def handle_shop_key(self, key) -> None:
        items = TRAIL_NAMES + ["Back"]
        n = len(items)
        if key in (pygame.K_UP, pygame.K_w):
            self.shop_index = (self.shop_index - 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.shop_index = (self.shop_index + 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_ESCAPE:
            self.state = STATE_MENU
        elif key == pygame.K_RETURN:
            name = items[self.shop_index]
            if name == "Back":
                self.state = STATE_MENU
                return
            spec = TRAIL_EFFECTS[name]
            if name == self.equipped_trail:
                return
            if name in self.owned_trails:
                self.equipped_trail = name
                self.sounds.play(self.sounds.menu_select)
                self.save_wallet()
            elif self.wallet >= spec["cost"]:
                self.wallet -= spec["cost"]
                self.owned_trails.add(name)
                self.equipped_trail = name
                self.sounds.play(self.sounds.unlock)
                self.save_wallet()
                self._unlock("fashionista")
                if all(t in self.owned_trails for t in TRAIL_NAMES):
                    self._unlock("collector")

    def handle_initials_key(self, key) -> None:
        if key == pygame.K_UP:
            cur = self.pending_initials[self.initials_cursor]
            idx = (LETTERS.index(cur) + 1) % len(LETTERS)
            self.pending_initials[self.initials_cursor] = LETTERS[idx]
            self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_DOWN:
            cur = self.pending_initials[self.initials_cursor]
            idx = (LETTERS.index(cur) - 1) % len(LETTERS)
            self.pending_initials[self.initials_cursor] = LETTERS[idx]
            self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_LEFT:
            self.initials_cursor = (self.initials_cursor - 1) % 3
        elif key == pygame.K_RIGHT:
            self.initials_cursor = (self.initials_cursor + 1) % 3
        elif key == pygame.K_RETURN:
            self.sounds.play(self.sounds.menu_select)
            self._commit_high_score()
        elif pygame.K_a <= key <= pygame.K_z:
            letter = chr(key).upper()
            self.pending_initials[self.initials_cursor] = letter
            self.initials_cursor = (self.initials_cursor + 1) % 3

    def handle_playing_key(self, key) -> None:
        if self.lan_role != "client" and self.death_pause_timer > 0:
            return  # the run is over; don't let Esc -> Main Menu skip saving it
        if self.lan_role == "client":
            d = None
            if key in (pygame.K_UP, pygame.K_w, pygame.K_k):
                d = (0, -1)
            elif key in (pygame.K_DOWN, pygame.K_s, pygame.K_j):
                d = (0, 1)
            elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_h):
                d = (-1, 0)
            elif key in (pygame.K_RIGHT, pygame.K_d, pygame.K_l):
                d = (1, 0)
            if d and self.lan_link:
                self.lan_link.send({"type": "input", "dir": list(d)})
            if key == pygame.K_ESCAPE:
                if self.lan_link:
                    self.lan_link.send({"type": "client_left"})
                self._lan_teardown()
                self.state = STATE_MENU
            elif key == pygame.K_m:
                self.sounds.muted = not self.sounds.muted
                self.save_settings()
            elif key == pygame.K_t and not self.chat_pending_open and not self.chat_active:
                # The client can't pause on its own - ask the host to, and
                # open chat as soon as that pause actually comes back.
                if self.lan_link:
                    self.lan_link.send({"type": "chat_pause_request"})
                self.chat_pending_open = True
            return

        cfg = self.mode_cfg()
        is_lan_host = self.lan_role == "host"
        if cfg["coop"]:
            # hjkl are vim-style alternates for Player 1's arrows (not WASD,
            # which is already Player 2's local-coop control scheme).
            if key in (pygame.K_UP, pygame.K_k):
                self._p1_set_direction((0, -1))
            elif key in (pygame.K_DOWN, pygame.K_j):
                self._p1_set_direction((0, 1))
            elif key in (pygame.K_LEFT, pygame.K_h):
                self._p1_set_direction((-1, 0))
            elif key in (pygame.K_RIGHT, pygame.K_l):
                self._p1_set_direction((1, 0))
            elif not is_lan_host and key == pygame.K_w and self.player2:
                self.player2.set_direction((0, -1))
            elif not is_lan_host and key == pygame.K_s and self.player2:
                self.player2.set_direction((0, 1))
            elif not is_lan_host and key == pygame.K_a and self.player2:
                self.player2.set_direction((-1, 0))
            elif not is_lan_host and key == pygame.K_d and self.player2:
                self.player2.set_direction((1, 0))
        else:
            if key in (pygame.K_UP, pygame.K_w, pygame.K_k):
                self._p1_set_direction((0, -1))
            elif key in (pygame.K_DOWN, pygame.K_s, pygame.K_j):
                self._p1_set_direction((0, 1))
            elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_h):
                self._p1_set_direction((-1, 0))
            elif key in (pygame.K_RIGHT, pygame.K_d, pygame.K_l):
                self._p1_set_direction((1, 0))

        if key == pygame.K_p:
            self.pause_index = 0
            self.state = STATE_PAUSED
            if is_lan_host and self.lan_link:
                self.lan_link.send({"type": "paused"})
        elif key == pygame.K_ESCAPE:
            if is_lan_host:
                self._host_end_session()
            else:
                self.state = STATE_MENU
        elif key == pygame.K_m:
            self.sounds.muted = not self.sounds.muted
            self.save_settings()
        elif key == pygame.K_t and is_lan_host:
            # Pause (same as P) and open chat in one press, host side - the
            # host IS the pause authority, so no round trip is needed.
            self.pause_index = 0
            self.state = STATE_PAUSED
            if self.lan_link:
                self.lan_link.send({"type": "paused"})
            self._open_chat()

    def handle_settings_key(self, key) -> None:
        rows = self._settings_rows()
        n = len(rows)
        if key in (pygame.K_UP, pygame.K_w):
            self.settings_index = (self.settings_index - 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.settings_index = (self.settings_index + 1) % n
            self.sounds.play(self.sounds.menu_move)
        elif key == pygame.K_TAB:
            self._set_settings_tab(self.settings_tab + (-1 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1))
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            direction = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
            self.setting_step(rows[self.settings_index], direction)
        elif key == pygame.K_RETURN:
            self.setting_step(rows[self.settings_index], 1)
        elif key == pygame.K_ESCAPE:
            self.state = self.prev_state

    def handle_pause_key(self, key) -> None:
        if self.lan_role == "client":
            # The client is a pure renderer of the host's game - it can't drive
            # Resume/Restart/Settings, since none of that state is theirs to
            # change. The only thing it can do locally is leave.
            if key == pygame.K_ESCAPE:
                if self.lan_link:
                    self.lan_link.send({"type": "client_left"})
                self._lan_teardown()
                self.state = STATE_MENU
            elif key == pygame.K_m:
                self.sounds.muted = not self.sounds.muted
                self.save_settings()
            elif key == pygame.K_t:
                self._open_chat()
            return

        items = self._pause_items()
        n = len(items)
        if key in (pygame.K_UP, pygame.K_w):
            self.pause_index = (self.pause_index - 1) % n
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.pause_index = (self.pause_index + 1) % n
        elif key == pygame.K_RETURN:
            choice = items[self.pause_index]
            if choice == "Resume":
                self.state = STATE_PLAYING
                if self.lan_role == "host" and self.lan_link:
                    self.lan_link.send({"type": "resumed"})
            elif choice == "Restart":
                self.reset_run()
                self.state = STATE_PLAYING
            elif choice == "Settings":
                self.prev_state = STATE_PAUSED
                self.settings_index = 0
                self.state = STATE_SETTINGS
            elif choice == "Main Menu":
                self.state = STATE_MENU
            elif choice == "End Session":
                self._host_end_session()
        elif key == pygame.K_p:
            self.state = STATE_PLAYING
            if self.lan_role == "host" and self.lan_link:
                self.lan_link.send({"type": "resumed"})
        elif key == pygame.K_ESCAPE:
            if self.lan_role == "host":
                self._host_end_session()
            else:
                self.state = STATE_MENU
        elif key == pygame.K_m:
            self.sounds.muted = not self.sounds.muted
            self.save_settings()
        elif key == pygame.K_t:
            self._open_chat()

    # ---------- mouse layer ----------

    def _hot(self, rect: pygame.Rect, attr: Optional[str] = None, index: int = 0, click=None,
             adjust=None, drag=None) -> None:
        self.hotspots.append(Hot(rect, attr, index, click, adjust, drag))

    def _hot_at(self, pos) -> Optional[Hot]:
        for h in reversed(self.hotspots):  # later draws sit on top of earlier ones
            if h.rect.collidepoint(pos):
                return h
        return None

    def _press(self, key: int) -> None:
        """Replay a key press: a click does exactly what the keyboard would."""
        self.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))

    def _button(self, rect: pygame.Rect, label: str, click, primary: bool = False,
                enabled: bool = True, font: Optional[pygame.font.Font] = None) -> None:
        ui.draw_button(screen, rect, label, font or font_small, primary, enabled)
        if enabled:
            self._hot(rect, click=click)

    def _draw_back_button(self, label: str = "< Back") -> None:
        self._button(pygame.Rect(16, 14, 96, 34), label, lambda: self._press(pygame.K_ESCAPE))

    def _list_row(self, rect: pygame.Rect, attr: str, index: int, click=None, adjust=None) -> None:
        ui.draw_row_highlight(screen, rect, getattr(self, attr) == index)
        self._hot(rect, attr, index, click or (lambda: self._press(pygame.K_RETURN)), adjust)

    def _arrow_hots(self, attr: str, index: int, font: pygame.font.Font, x: int, y: int, h: int,
                    head: str, value: str, adjust) -> None:
        """Make the '<' and '>' glyphs inside a 'Label  < value >' line clickable.
        `head` is everything drawn before the value on that line."""
        hx = x + font.size(head)[0]
        aw = font.size("<")[0] + 12
        self._hot(pygame.Rect(hx - 6, y, aw, h), attr, index, lambda: adjust(-1), adjust)
        end = hx + font.size(value)[0]
        self._hot(pygame.Rect(end - aw + 6, y, aw, h), attr, index, lambda: adjust(1), adjust)

    def _step_key(self, direction: int) -> None:
        self._press(pygame.K_RIGHT if direction > 0 else pygame.K_LEFT)

    def _mouse_back(self) -> None:
        """Right-click: the mouse equivalent of Esc, except on the pause menu, where Esc
        would throw the run away - there it resumes instead. The mouse does nothing
        while actually playing: the snake is keyboard-only."""
        st = self.state
        if st == STATE_PAUSED:
            if self.lan_role != "client":
                self._press(pygame.K_p)
        elif st == STATE_PLAYING:
            pass
        elif st not in (STATE_UPDATE_CHECK, STATE_UPDATE_DOWNLOAD, STATE_EASTER_WARNING,
                        STATE_ENTER_INITIALS, STATE_MENU):
            self._press(pygame.K_ESCAPE)

    def _handle_mouse(self, event: pygame.event.Event) -> None:
        if self.state == STATE_PLAYING:
            return  # gameplay is keyboard-only; the mouse is for menus and settings
        before = self.state
        if event.type == pygame.MOUSEMOTION:
            if self.drag_hot and event.buttons[0]:
                self.drag_hot.drag(gfx.to_logical(event.pos))
                return
            h = self._hot_at(gfx.to_logical(event.pos))
            if h and h.attr and getattr(self, h.attr) != h.index:
                setattr(self, h.attr, h.index)
                self.sounds.play(self.sounds.menu_move)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                pos = gfx.to_logical(event.pos)
                h = self._hot_at(pos)
                if h:
                    if h.attr:
                        setattr(self, h.attr, h.index)
                    if h.drag:
                        self.drag_hot = h
                        h.drag(pos)
                    elif h.click:
                        h.click()
            elif event.button == 3:
                self._mouse_back()
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.drag_hot:
                self.drag_hot = None
                if self.state == STATE_SETTINGS:
                    self.save_settings()  # sliders skip saving while dragging
                    self.sounds.play(self.sounds.menu_select)
        elif event.type == pygame.MOUSEWHEEL:
            h = self._hot_at(gfx.mouse_pos())
            if h and h.adjust and event.y:
                if h.attr:
                    setattr(self, h.attr, h.index)
                h.adjust(1 if event.y > 0 else -1)
        if self.state != before:
            self.hotspots = []  # stale for the new screen until it draws
            self.drag_hot = None

    def _draw_cursor(self, dt: float) -> None:
        """Draw the snake pointer last, over everything. The OS pointer is hidden."""
        if not self._cursor_hidden:
            pygame.mouse.set_visible(False)
            self._cursor_hidden = True
        if not pygame.mouse.get_focused() or self.state == STATE_PLAYING:
            return
        pos = gfx.mouse_pos()
        h = self._hot_at(pos)
        excited = bool(h and (h.click or h.drag))
        skin = SNAKE_SKINS[SKIN_NAMES[self.skin_idx]]
        self.cursor.update(pos)
        self.cursor.draw(screen, skin[0], skin[1], excited)

    PAD_HINTS = (
        ("Enter / Esc: back", "A / B: back"),
        ("Esc / right-click: back", "B: back"),
        ("Right-click: back", "B: back"),
        ("Click, drag or scroll to change   Tab: next tab   F11: fullscreen", "Left / Right: change   LB / RB: switch tab"),
        ("Esc: back", "B: back"),
        ("Right-click or P to resume   Esc menu", "Start or B: resume   Select: menu"),
        ("M mute  |  Esc menu", "Start: pause"),
    )

    def _hint(self, text: str) -> str:
        """Footer hint text, with key names swapped for pad buttons while a pad is the active device."""
        if self.pad_active:
            for keys, pad in self.PAD_HINTS:
                text = text.replace(keys, pad)
        return text

    def _open_pad(self, index: int) -> None:
        if index in self._pads or not sdl_controller.is_controller(index):
            return
        try:
            self._pads[index] = sdl_controller.Controller(index)
        except pygame.error:
            pass

    def _pad_press(self, key: int) -> None:
        """Controller input replays keys, like the mouse layer: Start pauses/resumes, B backs
        out (but never abandons a run from Playing), and Playing only accepts steering."""
        st = self.state
        if key == pygame.K_ESCAPE:
            if st == STATE_PLAYING or st == STATE_MENU:
                return
            if st == STATE_PAUSED:
                key = pygame.K_p
        elif key == pygame.K_p:
            if st not in (STATE_PLAYING, STATE_PAUSED) or self.lan_role == "client":
                key = pygame.K_RETURN
        elif key == pygame.K_RETURN and st == STATE_PLAYING:
            return
        self._press(key)
        self.pad_active = True

    def _handle_controller(self, event: pygame.event.Event) -> None:
        t = event.type
        if t == pygame.CONTROLLERDEVICEADDED:
            self._open_pad(event.device_index)
        elif t == pygame.CONTROLLERDEVICEREMOVED:
            self._pads = {i: c for i, c in self._pads.items() if c.attached()}
            self._stick_dir = dict.fromkeys(self._stick_dir, 0)
            if self.state == STATE_PLAYING and self.lan_role is None and not self._pads:
                self._press(pygame.K_p)  # pad unplugged mid-run: pause rather than crash into a wall
        elif not self.settings["controller_enabled"]:
            return
        elif t == pygame.CONTROLLERBUTTONDOWN:
            key = {
                pygame.CONTROLLER_BUTTON_DPAD_UP: pygame.K_UP,
                pygame.CONTROLLER_BUTTON_DPAD_DOWN: pygame.K_DOWN,
                pygame.CONTROLLER_BUTTON_DPAD_LEFT: pygame.K_LEFT,
                pygame.CONTROLLER_BUTTON_DPAD_RIGHT: pygame.K_RIGHT,
                pygame.CONTROLLER_BUTTON_A: pygame.K_RETURN,
                pygame.CONTROLLER_BUTTON_B: pygame.K_ESCAPE,
                pygame.CONTROLLER_BUTTON_START: pygame.K_p,
            }.get(event.button)
            if key is not None:
                self._pad_press(key)
            elif (event.button in (pygame.CONTROLLER_BUTTON_LEFTSHOULDER, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER)
                  and self.state == STATE_SETTINGS):
                self._set_settings_tab(self.settings_tab + (-1 if event.button == pygame.CONTROLLER_BUTTON_LEFTSHOULDER else 1))
                self.pad_active = True
            elif event.button == pygame.CONTROLLER_BUTTON_BACK and self.state == STATE_PAUSED:
                self._press(pygame.K_ESCAPE)  # Select leaves the run from Paused; B only resumes
                self.pad_active = True
        elif t == pygame.CONTROLLERAXISMOTION and event.axis in self._stick_dir:
            v = event.value
            cur = self._stick_dir[event.axis]
            # Hysteresis: release well below the engage point so a wobbly stick doesn't spam.
            engage = STICK_ENGAGE[self.settings["stick_sensitivity"]]
            if cur == 0:
                new = 1 if v > engage else -1 if v < -engage else 0
            else:
                new = cur if abs(v) > engage * 0.55 and (v > 0) == (cur > 0) else 0
            if new != cur:
                self._stick_dir[event.axis] = new
                if new:
                    horiz = event.axis == pygame.CONTROLLER_AXIS_LEFTX
                    self._pad_press((pygame.K_RIGHT if new > 0 else pygame.K_LEFT) if horiz
                                    else (pygame.K_DOWN if new > 0 else pygame.K_UP))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.pad_active = False
        if event.type in (pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED,
                          pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERAXISMOTION):
            if not self.chat_active:
                self._handle_controller(event)
            return
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
            if not self.chat_active:
                self._handle_mouse(event)
            return
        if event.type == pygame.WINDOWFOCUSLOST:
            if (self.state == STATE_PLAYING and self.lan_role is None and self.settings["auto_pause"]
                    and self.death_pause_timer <= 0):
                self._press(pygame.K_p)
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            self.setting_set("fullscreen", not self.settings["fullscreen"])
            return
        if event.type == pygame.TEXTINPUT:
            if self.chat_active:
                self.handle_chat_text(event.text)
            return
        if event.type != pygame.KEYDOWN:
            return
        self.pad_active = False
        key = event.key

        if self.chat_active:
            # Chat owns all keyboard input while open - it's only reachable from
            # Paused, so there's no snake to accidentally steer underneath it.
            self.handle_chat_key(key)
            return

        if self.state == STATE_MENU:
            self.handle_menu_key(key)
        elif self.state == STATE_PLAYING:
            self.handle_playing_key(key)
        elif self.state == STATE_PAUSED:
            self.handle_pause_key(key)
        elif self.state == STATE_SETTINGS:
            self.handle_settings_key(key)
        elif self.state == STATE_SHOP:
            self.handle_shop_key(key)
        elif self.state == STATE_ENTER_INITIALS:
            self.handle_initials_key(key)
        elif self.state == STATE_GAME_OVER:
            if self.lan_role:
                if key in (pygame.K_RETURN, pygame.K_ESCAPE):
                    self._lan_teardown()
                    self.state = STATE_MENU
            elif key == pygame.K_RETURN:
                self.reset_run()
                self.state = STATE_PLAYING
            elif key == pygame.K_ESCAPE:
                self.state = STATE_MENU
        elif self.state == STATE_LAN_MENU:
            self.handle_lan_menu_key(key)
        elif self.state == STATE_LAN_SETUP:
            self.handle_lan_setup_key(key)
        elif self.state == STATE_MAP_SELECT:
            self.handle_map_select_key(key)
        elif self.state == STATE_LAN_HOST_WAIT:
            self.handle_lan_host_wait_key(key)
        elif self.state == STATE_LAN_JOIN_IP:
            self.handle_lan_join_ip_key(key)
        elif self.state == STATE_ONLINE_JOIN_CODE:
            self.handle_online_join_code_key(key)
        elif self.state == STATE_LAN_CONNECTING:
            if key == pygame.K_ESCAPE:
                if self.lan_client:
                    self.lan_client.close()
                if self.lan_pending_link:
                    self.lan_pending_link.close()
                self.lan_client = None
                self.lan_pending_link = None
                self.state = STATE_ONLINE_JOIN_CODE if self.lan_online else STATE_LAN_JOIN_IP
        elif self.state == STATE_LAN_ERROR:
            if key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self._lan_teardown()
                self.state = STATE_LAN_MENU
        elif self.state in (STATE_LEADERBOARD, STATE_ACHIEVEMENTS, STATE_STATS, STATE_CHANGELOG,
                            STATE_HOWTO, STATE_QUESTS):
            if key == pygame.K_ESCAPE:
                self.state = STATE_MENU
        elif self.state == STATE_UPDATE_PROMPT:
            self.handle_update_prompt_key(key)
        elif self.state in (STATE_UPDATE_NONE, STATE_UPDATE_ERROR):
            if key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.state = STATE_MENU
        # STATE_UPDATE_CHECK and STATE_UPDATE_DOWNLOAD intentionally take no
        # input - they resolve on their own once the background thread is done.
        elif self.state == STATE_EASTER_WARNING:
            self.handle_easter_warning_key(key)
        elif self.state == STATE_SECRET_SHOP:
            self.handle_secret_shop_key(key)

    # ---------- main loop ----------

    def run(self) -> None:
        while True:
            self._frame(clock.tick(FPS) / 1000.0)

    def _frame(self, dt: float) -> None:
        dt = min(dt, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            self.handle_event(event)

        if self.state == STATE_UPDATE_CHECK:
            self._poll_update_check(dt)
        elif self.state == STATE_UPDATE_DOWNLOAD:
            self._poll_update_download()
        elif self.state == STATE_EASTER_WARNING:
            self.particles.update(dt)
        elif self.state == STATE_LAN_HOST_WAIT:
            if self.lan_role == "client":
                self._lan_client_poll(dt)
            else:
                self._lan_host_poll()
        elif self.state == STATE_LAN_CONNECTING:
            self._lan_connecting_poll()
        elif self.state == STATE_PAUSED and self.lan_role == "host":
            self._lan_host_pause_poll()
        elif self.state == STATE_PAUSED and self.lan_role == "client":
            self._lan_client_poll(dt)

        self.hotspots = []  # every draw_* below re-registers its clickable regions

        if self.state == STATE_PLAYING:
            if self.lan_role == "client":
                self._lan_client_poll(dt)
            else:
                self.update_playing(dt)
            if self.state == STATE_PLAYING:
                if self.lan_role == "client":
                    alpha = min(1.0, self.snapshot_age / NETWORK_SNAPSHOT_INTERVAL)
                else:
                    alpha = 1.0 if self.lan_role else min(1.0, self.move_accum / self.move_interval())
                self.draw_playing(alpha)
                self.draw_sidebar()
                self._draw_net_banner()
        elif self.state == STATE_PAUSED:
            self.draw_playing(1.0)
            self.draw_sidebar()
            self.draw_paused()
        elif self.state == STATE_MENU:
            self.draw_menu()
        elif self.state == STATE_GAME_OVER:
            self.draw_game_over()
        elif self.state == STATE_LEADERBOARD:
            self.draw_leaderboard()
        elif self.state == STATE_ACHIEVEMENTS:
            self.draw_achievements()
        elif self.state == STATE_SETTINGS:
            self.draw_settings()
        elif self.state == STATE_STATS:
            self.draw_stats()
        elif self.state == STATE_CHANGELOG:
            self.draw_changelog()
        elif self.state == STATE_SHOP:
            self.draw_shop()
        elif self.state == STATE_ENTER_INITIALS:
            self.draw_enter_initials()
        elif self.state == STATE_LAN_MENU:
            self.draw_lan_menu()
        elif self.state == STATE_LAN_SETUP:
            self.draw_lan_setup()
        elif self.state == STATE_MAP_SELECT:
            self.draw_map_select()
        elif self.state == STATE_LAN_HOST_WAIT:
            self.draw_lan_host_wait()
        elif self.state == STATE_LAN_JOIN_IP:
            self.draw_lan_join_ip()
        elif self.state == STATE_ONLINE_JOIN_CODE:
            self.draw_online_join_code()
        elif self.state == STATE_LAN_CONNECTING:
            self.draw_lan_connecting()
        elif self.state == STATE_LAN_ERROR:
            self.draw_lan_error()
        elif self.state == STATE_HOWTO:
            self.draw_howto()
        elif self.state == STATE_QUESTS:
            self.draw_quests()
        elif self.state == STATE_UPDATE_CHECK:
            self.draw_update_check()
        elif self.state == STATE_UPDATE_PROMPT:
            self.draw_update_prompt()
        elif self.state == STATE_UPDATE_NONE:
            self.draw_update_none()
        elif self.state == STATE_UPDATE_DOWNLOAD:
            self.draw_update_download()
        elif self.state == STATE_UPDATE_ERROR:
            self.draw_update_error()
        elif self.state == STATE_EASTER_WARNING:
            self.draw_easter_warning()
        elif self.state == STATE_SECRET_SHOP:
            self.draw_secret_shop()

        if self._fade_from is not None:
            self._fade_t -= dt
            if self._fade_t <= 0:
                self._fade_from = None
            else:
                # Old screen goes dark, then the new one comes up out of the dark. A straight
                # crossfade of two text-heavy screens just looks like a smeared double exposure.
                p = 1.0 - self._fade_t / FADE_SECONDS
                if p < FADE_OUT_SHARE:
                    screen.blit(self._fade_from, (0, 0))
                    dark = p / FADE_OUT_SHARE
                else:
                    dark = 1.0 - (p - FADE_OUT_SHARE) / (1.0 - FADE_OUT_SHARE)
                if self._fade_black is None or self._fade_black.k != gfx.scale():
                    self._fade_black = gfx.surface((SCREEN_W, SCREEN_H))
                    self._fade_black.fill((5, 7, 12))
                self._fade_black.set_alpha(int(255 * dark ** 1.3))
                screen.blit(self._fade_black, (0, 0))
        self._draw_ui_toasts(dt)
        if self.settings["show_fps"]:
            fps = font_tiny.render(f"{clock.get_fps():.0f} FPS", True, TEXT_DIM)
            screen.blit(fps, (SCREEN_W - fps.get_width() - 8, SCREEN_H - fps.get_height() - 4))
        self._draw_cursor(dt)
        display.fill(BG)  # letterbox bars blend into the background
        display.blit(screen, canvas_offset)
        pygame.display.flip()

    def _draw_ui_toasts(self, dt: float) -> None:
        """Achievement toasts earned outside a run (shop, settings). Mid-run ones use
        the sidebar's toast_queue instead."""
        if not self.ui_toasts:
            return
        y = 10
        for toast in self.ui_toasts[:3]:
            title, subtitle, life = toast
            a = min(1.0, life)
            card = gfx.surface((240, 46), pygame.SRCALPHA)
            gfx.draw.rect(card, (30, 30, 45, int(230 * a)), card.get_rect(), border_radius=8)
            gfx.draw.rect(card, (*GOLD, int(255 * a)), card.get_rect(), width=2, border_radius=8)
            card.blit(font_tiny.render(title, True, GOLD), (10, 6))
            card.blit(font_small.render(subtitle, True, TEXT), (10, 22))
            screen.blit(card, (SCREEN_W - 252, y))
            y += 52
            toast[2] -= dt
        self.ui_toasts = [t for t in self.ui_toasts if t[2] > 0]


if __name__ == "__main__":
    Game().run()
