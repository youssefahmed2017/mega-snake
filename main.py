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
import random
import sys
from collections import deque
from typing import Dict, List, Optional, Tuple

import pygame

import colorsys

from constants import (
    CELL_SIZE, GRID_W, GRID_H, SIDEBAR_W, SCREEN_W, SCREEN_H, FPS, BASE_MOVE_INTERVAL,
    BG, GRID_LINE, SIDEBAR_BG, TEXT, TEXT_DIM, ACCENT, DANGER, GOLD, GREEN, PURPLE,
    SNAKE_SKINS, SKIN_UNLOCK_REQUIREMENT, P2_COLOR, TRAIL_EFFECTS, TRAIL_NAMES,
    FOOD_NORMAL, FOOD_GOLDEN, FOOD_SPEED, FOOD_SHRINK, FOOD_BOMB, FOOD_CURSE, FOOD_COLORS,
    POWERUP_GHOST, POWERUP_MAGNET, POWERUP_SHIELD, POWERUP_SLOWMO, POWERUP_MULT,
    POWERUP_FREEZE, POWERUP_TELEPORT, POWERUP_COLORS, POWERUP_DURATIONS, CURSE_DURATION,
    PORTAL_A, PORTAL_B, MODES, MODE_CONFIG, MODE_DESC, DIFFICULTIES, DIFFICULTY_SPEED_MULT,
    GAME_VERSION, CHANGELOG, COLORBLIND_FOOD_COLORS, COLORBLIND_POWERUP_COLORS, GHOST_MAX_TICKS,
)
from snake import PlayerSnake
from enemy import EnemySnake
from food import Food, PowerUp, spawn_food, maybe_spawn_powerup, maybe_spawn_portal_pair, random_free_cell
from particles import ParticleSystem
from achievements import ACHIEVEMENTS, AchievementTracker
from audio import SoundBank
import persistence
import network
from quests import quests_for_date

pygame.init()
pygame.display.set_caption("MEGA SNAKE")
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
clock = pygame.time.Clock()

font_big = pygame.font.SysFont("consolas", 40, bold=True)
font_mid = pygame.font.SysFont("consolas", 24, bold=True)
font_small = pygame.font.SysFont("consolas", 16)
font_tiny = pygame.font.SysFont("consolas", 13)

SKIN_NAMES = list(SNAKE_SKINS.keys())

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
STATE_LAN_HOST_WAIT = "lan_host_wait"
STATE_LAN_JOIN_IP = "lan_join_ip"
STATE_LAN_CONNECTING = "lan_connecting"
STATE_LAN_ERROR = "lan_error"
STATE_HOWTO = "howto"
STATE_QUESTS = "quests"

MENU_ITEMS = [
    "Start Game", "Mode", "Skin", "LAN Multiplayer", "Daily Quests", "Shop", "Settings",
    "How to Play", "Stats", "Leaderboard", "Achievements", "Changelog", "Quit",
]
PAUSE_ITEMS = ["Resume", "Restart", "Settings", "Main Menu"]
LAN_HOST_PAUSE_ITEMS = ["Resume", "Settings", "End Session"]
SETTINGS_ITEMS = ["Volume", "Difficulty", "Screen Shake", "Mute", "Color Blind Mode", "Back"]
LAN_MENU_ITEMS = ["Host Game", "Join Game", "Back"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def grid_to_px(x: float, y: float) -> Tuple[float, float]:
    return x * CELL_SIZE, y * CELL_SIZE


def clamp_color(c: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return tuple(max(0, min(255, int(v))) for v in c)


class Game:
    def __init__(self) -> None:
        self.data = persistence.load()
        self.tracker = AchievementTracker(self.data.get("achievements", []))
        self.sounds = SoundBank()
        self.particles = ParticleSystem()

        settings = self.data["settings"]
        self.sounds.master_volume = settings.get("volume", 100) / 100
        self.sounds.muted = settings.get("muted", False)
        self.difficulty = settings.get("difficulty", "Normal")
        self.screen_shake_enabled = settings.get("screen_shake", True)
        self.colorblind = settings.get("colorblind", False)

        self.ghosts = persistence.load_ghosts()
        self.announcer_queue: List[list] = []  # [text, color, life, max_life]
        self._vignette_cache: Dict[Tuple[int, bool], pygame.Surface] = {}
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
        self.lan_ip_input = ""
        self.lan_error_msg = ""
        self.local_ip: Optional[str] = None

        self.reset_run()

    # ---------- helpers ----------

    def mode_name(self) -> str:
        return MODES[self.mode_idx]

    def mode_cfg(self) -> dict:
        return MODE_CONFIG[self.mode_name()]

    def _center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        return cell[0] + 0.5, cell[1] + 0.5

    def shake(self, duration: float, magnitude: float) -> None:
        if self.screen_shake_enabled:
            self.particles.shake(duration, magnitude)

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

    def save_settings(self) -> None:
        self.data["settings"] = {
            "volume": round(self.sounds.master_volume * 100),
            "difficulty": self.difficulty,
            "screen_shake": self.screen_shake_enabled,
            "muted": self.sounds.muted,
            "colorblind": self.colorblind,
        }
        persistence.save(self.data)

    def food_color(self, kind: str) -> Tuple[int, int, int]:
        return (COLORBLIND_FOOD_COLORS if self.colorblind else FOOD_COLORS)[kind]

    def powerup_color(self, kind: str) -> Tuple[int, int, int]:
        return (COLORBLIND_POWERUP_COLORS if self.colorblind else POWERUP_COLORS)[kind]

    def _quest_progress(self) -> Tuple[int, int]:
        today_iso = datetime.date.today().isoformat()
        todays = quests_for_date(today_iso)
        q = self.data.get("quests", {})
        completed = q.get("completed", []) if q.get("date") == today_iso else []
        return sum(1 for quest in todays if quest.id in completed), len(todays)

    def _announce(self, text: str, color: Tuple[int, int, int] = GOLD, life: float = 1.3) -> None:
        # Keep at most two callouts stacked so a burst of events stays readable.
        self.announcer_queue.append([text, color, life, life])
        del self.announcer_queue[:-2]

    def save_wallet(self) -> None:
        self.data["wallet"] = self.wallet
        self.data["owned_trails"] = sorted(self.owned_trails)
        self.data["equipped_trail"] = self.equipped_trail
        persistence.save(self.data)

    def trail_color(self, t: float) -> Optional[Tuple[int, int, int]]:
        spec = TRAIL_EFFECTS[self.equipped_trail]["color"]
        if spec is None:
            return None
        if spec == "rainbow":
            hue = (t * 0.3) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
            return int(r * 255), int(g * 255), int(b * 255)
        return spec

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
        self.lan_link = None
        self.lan_host = None
        self.lan_client = None
        self.lan_role = None

    def _build_snapshot(self, game_over: bool = False) -> dict:
        return {
            "type": "state",
            "mode": self.mode_name(),
            "skin_p1": SKIN_NAMES[self.skin_idx],
            "p1_body": [list(c) for c in self.player.body],
            "p1_dir": list(self.player.direction),
            "p1_alive": self.player_alive,
            "p2_body": [list(c) for c in self.player2.body] if self.player2 else [],
            "p2_dir": list(self.player2.direction) if self.player2 else [1, 0],
            "p2_alive": self.player2_alive,
            "foods": [{"x": f.x, "y": f.y, "kind": f.kind} for f in self.foods],
            "powerups": [{"x": p.x, "y": p.y, "kind": p.kind} for p in self.powerups],
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

    def apply_snapshot(self, snap: dict) -> None:
        self.player.body = deque(tuple(c) for c in snap["p1_body"])
        self.player.prev_body = list(self.player.body)
        self.player.direction = tuple(snap["p1_dir"])
        self.player_alive = snap["p1_alive"]

        if self.player2 is None:
            self.player2 = PlayerSnake(0, 0)
        self.player2.body = deque(tuple(c) for c in snap["p2_body"]) if snap["p2_body"] else deque([(0, 0)])
        self.player2.prev_body = list(self.player2.body)
        self.player2.direction = tuple(snap["p2_dir"])
        self.player2_alive = snap["p2_alive"]

        self.foods = [Food(f["x"], f["y"], f["kind"]) for f in snap["foods"]]
        self.powerups = [PowerUp(p["x"], p["y"], p["kind"]) for p in snap["powerups"]]
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

        if snap.get("game_over"):
            self.game_over_reason = snap.get("game_over_reason") or "Game over."
            self.final_stats = {
                "score": self.score, "food_eaten": 0, "golden_eaten": 0,
                "length": len(self.player.body) + len(self.player2.body), "time_alive": 0,
            }
            self.score_breakdown = {"normal": 0, "golden": 0, "mult_bonus": 0, "penalty": 0}
            self.run_coins_earned = 0
            self.run_streak_bonus = 0
            self.state = STATE_GAME_OVER

    def _lan_host_poll(self) -> None:
        if not self.lan_host:
            return
        link = self.lan_host.poll_new_connection()
        if link:
            self.lan_link = link
            self.lan_role = "host"
            self.mode_idx = MODES.index("Coop")
            self.reset_run()
            link.send({"type": "welcome", "mode": self.mode_name(), "skin": SKIN_NAMES[self.skin_idx]})
            self.state = STATE_PLAYING

    def _lan_connecting_poll(self) -> None:
        if not self.lan_client:
            return
        result = self.lan_client.poll_connect_result()
        if result is True:
            self.lan_link = self.lan_client.link
            self.lan_role = "client"
            self.lan_client = None
            self.mode_idx = MODES.index("Coop")
            self.reset_run()
            self.state = STATE_PLAYING
        elif result is False:
            self.lan_error_msg = self.lan_client.error or "Could not connect."
            self.lan_client = None
            self.state = STATE_LAN_ERROR

    def _lan_client_poll(self, dt: float) -> None:
        if not self.lan_link:
            return
        # Drain whatever already arrived before checking the connection flag -
        # a graceful "host_left" is usually sitting in the queue right before
        # the socket reports closed, and it explains *why* far better than a
        # generic disconnect message would.
        for msg in self.lan_link.poll():
            mtype = msg.get("type")
            if mtype == "state":
                self.apply_snapshot(msg)
            elif mtype == "host_left":
                self.lan_error_msg = "Host ended the session."
                self._lan_teardown()
                self.state = STATE_LAN_ERROR
                return
            elif mtype == "paused":
                self.state = STATE_PAUSED
            elif mtype == "resumed":
                self.state = STATE_PLAYING
        if not self.lan_link.connected:
            self.lan_error_msg = "Host disconnected."
            self._lan_teardown()
            self.state = STATE_LAN_ERROR
            return
        self.particles.update(dt)

    def _lan_host_pause_poll(self) -> None:
        """While the host has the game paused, update_playing() (and its usual
        network polling) never runs. Still drain the socket so a client
        disconnect is noticed immediately instead of only on resume."""
        if not self.lan_link:
            return
        for msg in self.lan_link.poll():
            if msg.get("type") == "client_left":
                self.lan_error_msg = "Player left the game."
                self._lan_teardown()
                self.state = STATE_LAN_ERROR
                return
            # "input" messages that arrive while paused are intentionally
            # dropped - the client is a pure renderer, queued moves from
            # before the pause shouldn't suddenly fire on resume.
        if not self.lan_link.connected:
            self.lan_error_msg = "Player disconnected."
            self._lan_teardown()
            self.state = STATE_LAN_ERROR

    # ---------- run lifecycle ----------

    def reset_run(self) -> None:
        cfg = self.mode_cfg()
        cx, cy = GRID_W // 2, GRID_H // 2

        self.player = PlayerSnake(cx, cy)
        self.player_alive = True
        self.player2: Optional[PlayerSnake] = None
        self.player2_alive = False
        if cfg["coop"]:
            self.player2 = PlayerSnake(cx - 6, cy)
            self.player2_alive = True

        self.rivals: List[EnemySnake] = []
        corners = [(GRID_W - 5, GRID_H - 5), (4, 4), (GRID_W - 5, 4), (4, GRID_H - 5)]
        for i in range(cfg["rivals"]):
            rx, ry = corners[i % len(corners)]
            self.rivals.append(EnemySnake(rx, ry))

        self.obstacles: set = set()
        self.foods: List[Food] = []
        self.powerups: List[PowerUp] = []
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
            powerups_collected=0, portals_used=0,
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
                    d = msg.get("dir")
                    if isinstance(d, list) and len(d) == 2 and self.player2:
                        self.player2.set_direction((int(d[0]), int(d[1])))
                elif mtype == "client_left":
                    self.lan_error_msg = "Player left the game."
                    self._lan_teardown()
                    self.state = STATE_LAN_ERROR
                    return
            if not self.lan_link.connected:
                self.lan_error_msg = "Player disconnected."
                self._lan_teardown()
                self.state = STATE_LAN_ERROR
                return

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

        for burst in list(self.pending_death_bursts):
            burst[0] -= dt
            if burst[0] <= 0:
                self.particles.burst(burst[1], burst[2], burst[3], count=8, speed=180, life=0.6)
                self.pending_death_bursts.remove(burst)

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

        newly = self.tracker.check(self.stats)
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
            self._announce("NEW PERSONAL BEST!", GREEN, life=1.8)
            self.sounds.play(self.sounds.achievement)
            self.zoom_timer = self.zoom_duration

        self.toast_queue = [(t, s, tl - dt) for (t, s, tl) in self.toast_queue if tl - dt > 0]
        for a in self.announcer_queue:
            a[2] -= dt
        self.announcer_queue = [a for a in self.announcer_queue if a[2] > 0]
        self.particles.update(dt)

        if self.lan_role == "host" and self.lan_link and self.lan_link.connected:
            self.lan_link.send(self._build_snapshot())

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

        self.active_powerups[kind] = POWERUP_DURATIONS[kind]
        self.sounds.play(self.sounds.freeze if kind == POWERUP_FREEZE else self.sounds.powerup)
        self.particles.burst(px, py, self.powerup_color(kind), count=18)

    def _blocking_set(self, exclude_tag: str) -> set:
        s = set(self.obstacles)
        if exclude_tag != "p1" and self.player_alive:
            s |= set(self.player.body)
        if exclude_tag != "p2" and self.player2 and self.player2_alive:
            s |= set(self.player2.body)
        for r in self.rivals:
            if r.alive:
                s |= r.occupies()
        return s

    def _tick(self) -> None:
        cfg = self.mode_cfg()
        ghost = POWERUP_GHOST in self.active_powerups
        cursed = self.curse_timer > 0
        wrap = cfg["wrap"] or ghost

        movers: List[Tuple[str, PlayerSnake]] = []
        if self.player_alive:
            movers.append(("p1", self.player))
        if cfg["coop"] and self.player2 and self.player2_alive:
            movers.append(("p2", self.player2))

        prev_heads = {}
        for tag, snake in movers:
            prev_heads[tag] = snake.head
            if cursed and tag == "p1":
                # Curse inverts the *intended* direction for whichever way was queued.
                dx, dy = snake.pending_direction
                snake.pending_direction = (-dx, -dy) if (dx, dy) != (0, 0) else (dx, dy)
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
                    self._announce("CLUTCH SAVE!", GREEN)
                else:
                    self._kill_snake(tag, reason)

        for tag, snake in movers:
            if self._snake_alive(tag):
                self._check_portal(tag, snake)

        for tag, snake in movers:
            if self._snake_alive(tag):
                hx, hy = snake.head
                for f in list(self.foods):
                    if (f.x, f.y) == (hx, hy):
                        self._consume_food(f, snake)

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
        return self.player_alive if tag == "p1" else self.player2_alive

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

        other = self.player2 if tag == "p1" else self.player
        other_alive = self.player2_alive if tag == "p1" else self.player_alive
        if cfg["coop"] and other is not None and other_alive and (nx, ny) in set(other.body):
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
            self.sounds.play(self.sounds.combo if self.combo > 1 else self.sounds.eat)
            self.particles.burst(px, py, self.food_color(FOOD_NORMAL), count=10)

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
            self.particles.burst(px, py, self.food_color(FOOD_GOLDEN), count=24, speed=200)
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
            self.particles.burst(px, py, self.food_color(FOOD_SPEED), count=14)

        elif f.kind == FOOD_SHRINK:
            snake.shrink(2)
            self.score = max(0, self.score - 5)
            self.score_breakdown["penalty"] -= 5
            self.sounds.play(self.sounds.shrink)
            self.particles.burst(px, py, self.food_color(FOOD_SHRINK), count=12)

        elif f.kind == FOOD_CURSE:
            self.curse_timer = CURSE_DURATION
            self.score = max(0, self.score - 5)
            self.score_breakdown["penalty"] -= 5
            self.sounds.play(self.sounds.curse)
            self.particles.burst(px, py, self.food_color(FOOD_CURSE), count=16, speed=180)
            self._announce("CURSED!", self.food_color(FOOD_CURSE), life=1.0)

        elif f.kind == FOOD_BOMB:
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
                tag = "p1" if snake is self.player else "p2"
                self._kill_snake(tag, "You detonated a bomb.")
                self._spawn_food()
                return

        self._spawn_food()

    # ---------- death / game over ----------

    def _kill_snake(self, tag: str, reason: str) -> None:
        snake = self.player if tag == "p1" else self.player2
        for i, (bx, by) in enumerate(snake.body):
            px, py = grid_to_px(*self._center((bx, by)))
            color = (255, 255, 255) if i == 0 else SNAKE_SKINS[SKIN_NAMES[self.skin_idx]][1]
            self.pending_death_bursts.append([i * 0.035, px, py, color])
        self.shake(0.4, 7)
        self.sounds.play(self.sounds.death)

        if tag == "p1":
            self.player_alive = False
        else:
            self.player2_alive = False
        self.last_death_reason[tag] = reason

        cfg = self.mode_cfg()
        if not cfg["coop"]:
            self.game_over_reason = reason
            self._finalize_game_over()
            return

        if not self.player_alive and not self.player2_alive:
            p1r = self.last_death_reason.get("p1", "-")
            p2r = self.last_death_reason.get("p2", "-")
            self.game_over_reason = f"P1: {p1r}   P2: {p2r}"
            self._finalize_game_over()

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

        self.run_new_ghost = False
        if self.ghost_enabled:
            self.run_new_ghost = persistence.save_ghost_if_better(
                self.ghosts, self.mode_name(), self.score, self.recording_trail,
            )

        self.final_stats = final

        if self.lan_role == "host" and self.lan_link and self.lan_link.connected:
            self.lan_link.send(self._build_snapshot(game_over=True))

        if persistence.would_qualify_for_leaderboard(self.data, self.score):
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

    def _draw_snake(self, board: pygame.Surface, snake: PlayerSnake, skin: list, alpha: float,
                     ghost_active: bool, alive: bool, name_tag: str) -> None:
        t = pygame.time.get_ticks() / 1000.0
        positions = snake.render_positions(alpha) if alive else [(x, y) for x, y in snake.body]
        for i, (fx, fy) in enumerate(positions):
            base_color = skin[0] if i == 0 else skin[1]
            color = self._pulse_color(base_color, i, t) if alive else tuple(max(0, c // 3) for c in base_color)
            if ghost_active and alive:
                s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                pygame.draw.rect(s, (*color, 140), (1, 1, CELL_SIZE - 2, CELL_SIZE - 2), border_radius=6)
                board.blit(s, (fx * CELL_SIZE, fy * CELL_SIZE))
            else:
                r = pygame.Rect(fx * CELL_SIZE + 1, fy * CELL_SIZE + 1, CELL_SIZE - 2, CELL_SIZE - 2)
                pygame.draw.rect(board, color, r, border_radius=6 if i > 0 else 8)
                if i == 0 and alive:
                    eye_dx, eye_dy = snake.direction
                    ex = fx * CELL_SIZE + CELL_SIZE // 2 + eye_dx * 4
                    ey = fy * CELL_SIZE + CELL_SIZE // 2 + eye_dy * 4
                    pygame.draw.circle(board, (10, 10, 15), (int(ex), int(ey)), 3)

        if alive and positions:
            speed_tier = min(5, self.score // 60)
            if self.speed_boost_timer > 0 or speed_tier >= 3:
                hx, hy = positions[0]
                cx, cy = hx * CELL_SIZE + CELL_SIZE // 2, hy * CELL_SIZE + CELL_SIZE // 2
                glow_color = self.trail_color(t) or skin[0]
                glow = pygame.Surface((CELL_SIZE * 3, CELL_SIZE * 3), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*glow_color, 55), (CELL_SIZE * 3 // 2, CELL_SIZE * 3 // 2), CELL_SIZE)
                board.blit(glow, (cx - CELL_SIZE * 1.5, cy - CELL_SIZE * 1.5), special_flags=pygame.BLEND_RGBA_ADD)

    def ghost_point(self) -> Optional[List[int]]:
        """[x, y, score] of the best run at the same tick as the current run, or
        None if there's no ghost or the ghost's run already ended."""
        if not self.ghost_trail or self.ghost_index <= 0 or self.ghost_index > len(self.ghost_trail):
            return None
        return self.ghost_trail[self.ghost_index - 1]

    def _draw_ghost(self, board: pygame.Surface) -> None:
        point = self.ghost_point()
        if point is None:
            return
        gx, gy = point[0], point[1]
        if not (0 <= gx < GRID_W and 0 <= gy < GRID_H):
            return
        cx, cy = gx * CELL_SIZE + CELL_SIZE // 2, gy * CELL_SIZE + CELL_SIZE // 2
        s = pygame.Surface((CELL_SIZE * 2, CELL_SIZE * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (220, 225, 255, 70), (CELL_SIZE, CELL_SIZE), CELL_SIZE // 2)
        pygame.draw.circle(s, (220, 225, 255, 150), (CELL_SIZE, CELL_SIZE), CELL_SIZE // 2, width=2)
        board.blit(s, (cx - CELL_SIZE, cy - CELL_SIZE))

    def _vignette_band(self, length: int, vertical: bool) -> pygame.Surface:
        """A red band fading from opaque at the wall to clear inward. Cached per
        size/orientation since it's identical every frame."""
        key = (length, vertical)
        cache = self._vignette_cache
        if key not in cache:
            depth = CELL_SIZE * 3
            surf = pygame.Surface((depth, length) if vertical else (length, depth), pygame.SRCALPHA)
            for i in range(depth):
                a = int(150 * (1 - i / depth) ** 2)
                if vertical:
                    pygame.draw.line(surf, (255, 40, 40, a), (i, 0), (i, length))
                else:
                    pygame.draw.line(surf, (255, 40, 40, a), (0, i), (length, i))
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
                    band = pygame.transform.flip(band, True, False)
                pos = (0, 0) if side == "left" else (w - band.get_width(), 0)
            else:
                band = self._vignette_band(w, vertical=False)
                if side == "bottom":
                    band = pygame.transform.flip(band, False, True)
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
            shadow.set_alpha(int(180 * fade))
            label.set_alpha(int(255 * fade))
            x = w // 2 - label.get_width() // 2
            board.blit(shadow, (x + 3, y + 3))
            board.blit(label, (x, y))

    def draw_playing(self, alpha: float) -> None:
        ox, oy = self.particles.get_shake_offset() if self.screen_shake_enabled else (0, 0)
        board = pygame.Surface((GRID_W * CELL_SIZE, GRID_H * CELL_SIZE))
        board.fill(BG)

        combo_t = min(1.0, self.combo / 20)
        line_color = tuple(int(GRID_LINE[i] + (ACCENT[i] - GRID_LINE[i]) * combo_t * 0.4) for i in range(3))
        for gx in range(GRID_W + 1):
            pygame.draw.line(board, line_color, (gx * CELL_SIZE, 0), (gx * CELL_SIZE, GRID_H * CELL_SIZE))
        for gy in range(GRID_H + 1):
            pygame.draw.line(board, line_color, (0, gy * CELL_SIZE), (GRID_W * CELL_SIZE, gy * CELL_SIZE))

        for (ox2, oy2) in self.obstacles:
            r = pygame.Rect(ox2 * CELL_SIZE + 2, oy2 * CELL_SIZE + 2, CELL_SIZE - 4, CELL_SIZE - 4)
            pygame.draw.rect(board, (70, 70, 80), r, border_radius=4)

        if self.portal_pair:
            t = pygame.time.get_ticks() / 300.0
            for (px_, py_), color in zip(self.portal_pair, (PORTAL_A, PORTAL_B)):
                cx, cy = px_ * CELL_SIZE + CELL_SIZE // 2, py_ * CELL_SIZE + CELL_SIZE // 2
                for ring in range(2):
                    rad = CELL_SIZE // 2 - 2 - ring * 4
                    if rad > 0:
                        start = t + ring * 2
                        pygame.draw.arc(board, color, (cx - rad, cy - rad, rad * 2, rad * 2), start, start + 4, 2)

        for f in self.foods:
            cx, cy = f.x * CELL_SIZE + CELL_SIZE // 2, f.y * CELL_SIZE + CELL_SIZE // 2
            color = self.food_color(f.kind)
            radius = CELL_SIZE // 2 - 3
            pygame.draw.circle(board, color, (cx, cy), radius)
            if f.kind == FOOD_BOMB:
                pygame.draw.circle(board, DANGER, (cx, cy), radius, 2)
            elif f.kind == FOOD_CURSE:
                pygame.draw.line(board, (255, 255, 255), (cx - 4, cy - 4), (cx + 4, cy + 4), 2)
                pygame.draw.line(board, (255, 255, 255), (cx - 4, cy + 4), (cx + 4, cy - 4), 2)

        for p in self.powerups:
            cx, cy = p.x * CELL_SIZE + CELL_SIZE // 2, p.y * CELL_SIZE + CELL_SIZE // 2
            color = self.powerup_color(p.kind)
            pulse = 2 + int(2 * abs((pygame.time.get_ticks() % 800) / 400 - 1))
            rect = pygame.Rect(0, 0, CELL_SIZE - 6 + pulse, CELL_SIZE - 6 + pulse)
            rect.center = (cx, cy)
            pygame.draw.rect(board, color, rect, border_radius=6, width=2)

        for rival in self.rivals:
            if not rival.alive:
                continue
            for i, (bx, by) in enumerate(rival.body):
                shade = rival.color if i == 0 else tuple(max(0, c - 40) for c in rival.color)
                r = pygame.Rect(bx * CELL_SIZE + 1, by * CELL_SIZE + 1, CELL_SIZE - 2, CELL_SIZE - 2)
                pygame.draw.rect(board, shade, r, border_radius=6)

        self._draw_ghost(board)

        skin = SNAKE_SKINS[SKIN_NAMES[self.skin_idx]]
        ghost_active = POWERUP_GHOST in self.active_powerups
        self._draw_snake(board, self.player, skin, alpha, ghost_active, self.player_alive, "p1")
        if self.player2:
            self._draw_snake(board, self.player2, P2_COLOR, alpha, ghost_active, self.player2_alive, "p2")

        if POWERUP_SHIELD in self.active_powerups and self.player_alive:
            hx, hy = self.player.render_positions(alpha)[0]
            cx, cy = hx * CELL_SIZE + CELL_SIZE // 2, hy * CELL_SIZE + CELL_SIZE // 2
            pygame.draw.circle(board, self.powerup_color(POWERUP_SHIELD), (int(cx), int(cy)), CELL_SIZE, width=2)

        self.particles.draw(board)
        self._draw_wall_vignette(board)
        self._draw_announcer(board)

        if self.zoom_timer > 0:
            frac = self.zoom_timer / self.zoom_duration
            scale = 1 + self.zoom_mag * frac
            w, h = board.get_size()
            scaled = pygame.transform.smoothscale(board, (int(w * scale), int(h * scale)))
            dx = (scaled.get_width() - w) // 2
            dy = (scaled.get_height() - h) // 2
            screen.blit(scaled, (ox - dx, oy - dy))
        else:
            screen.blit(board, (ox, oy))

    def draw_sidebar(self) -> None:
        panel = pygame.Rect(GRID_W * CELL_SIZE, 0, SIDEBAR_W, SCREEN_H)
        pygame.draw.rect(screen, SIDEBAR_BG, panel)
        x = GRID_W * CELL_SIZE + 18
        y = 14

        screen.blit(font_mid.render("MEGA SNAKE", True, ACCENT), (x, y))
        y += 30
        mode_line = f"Mode: {self.mode_name()}  [{self.difficulty}]"
        if self.lan_role:
            mode_line = f"LAN {'Host' if self.lan_role == 'host' else 'Client'}: {self.mode_name()}"
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

        if self.player2:
            p2_status = "alive" if self.player2_alive else "down"
            p2_color = TEXT if self.player2_alive else DANGER
            screen.blit(font_tiny.render(f"P2: {p2_status}  len {len(self.player2.body)}", True, p2_color), (x, y))
            y += 20
            p1_status = "alive" if self.player_alive else "down"
            p1_color = TEXT if self.player_alive else DANGER
            screen.blit(font_tiny.render(f"P1: {p1_status}", True, p1_color), (x, y))
            y += 20

        if self.curse_timer > 0:
            screen.blit(font_tiny.render(f"CURSED: controls reversed! {self.curse_timer:0.1f}s", True, self.food_color(FOOD_CURSE)), (x, y))
            y += 20

        y += 6
        if self.active_powerups:
            screen.blit(font_small.render("ACTIVE:", True, TEXT_DIM), (x, y))
            y += 18
            for kind, remaining in self.active_powerups.items():
                color = self.powerup_color(kind)
                pygame.draw.circle(screen, color, (x + 6, y + 7), 5)
                screen.blit(font_tiny.render(f"{kind}  {remaining:0.1f}s", True, TEXT), (x + 18, y))
                y += 18
            y += 6

        y = SCREEN_H - 130
        screen.blit(font_tiny.render("Arrows/WASD move  |  P pause", True, TEXT_DIM), (x, y)); y += 16
        screen.blit(font_tiny.render("M mute  |  Esc menu", True, TEXT_DIM), (x, y)); y += 16
        mute_state = "muted" if self.sounds.muted else f"{round(self.sounds.master_volume * 100)}%"
        screen.blit(font_tiny.render(f"Volume: {mute_state}", True, TEXT_DIM), (x, y)); y += 20

        legend = [
            (self.food_color(FOOD_NORMAL), "Food"),
            (self.food_color(FOOD_GOLDEN), "Golden (+50)"),
            (self.food_color(FOOD_CURSE), "Curse (reversed!)"),
            (self.food_color(FOOD_BOMB), "Bomb (danger!)"),
        ]
        for color, label in legend:
            pygame.draw.circle(screen, color, (x + 6, y + 6), 5)
            screen.blit(font_tiny.render(label, True, TEXT_DIM), (x + 18, y - 4))
            y += 15

        ty = 10
        for title, subtitle, life in self.toast_queue[:3]:
            alpha_t = min(1.0, life)
            s = pygame.Surface((220, 46), pygame.SRCALPHA)
            pygame.draw.rect(s, (30, 30, 45, int(220 * alpha_t)), s.get_rect(), border_radius=8)
            pygame.draw.rect(s, (*GOLD, int(255 * alpha_t)), s.get_rect(), width=2, border_radius=8)
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
            pygame.draw.circle(screen, color, (int(x), int(y)), 6)

    def draw_menu(self) -> None:
        screen.fill(BG)
        self.draw_menu_snake(SCREEN_H - 16)
        title = font_big.render("M E G A   S N A K E", True, ACCENT)
        screen.blit(title, (SCREEN_W // 2 - title.get_width() // 2, 34))
        sub = font_small.render(f"snake, but with way too many features  (v{GAME_VERSION})", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 78))

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
        start_y = 110
        line_h = 24
        for i, item in enumerate(items):
            selected = i == self.menu_index
            color = ACCENT if selected else TEXT
            prefix = "> " if selected else "  "
            text = font_small.render(prefix + item, True, color)
            screen.blit(text, (SCREEN_W // 2 - 180, start_y + i * line_h))

        desc = MODE_DESC[self.mode_name()]
        desc_r = font_tiny.render(desc, True, TEXT_DIM)
        screen.blit(desc_r, (SCREEN_W // 2 - desc_r.get_width() // 2, start_y + len(items) * line_h + 8))

        skin_name = SKIN_NAMES[self.skin_idx]
        skin_colors = SNAKE_SKINS[skin_name]
        py = start_y + len(items) * line_h + 28
        for i in range(6):
            color = skin_colors[0] if i == 0 else skin_colors[1]
            r = pygame.Rect(SCREEN_W // 2 - 60 + i * 22, py, 16, 16)
            pygame.draw.rect(screen, color, r, border_radius=5)

        foot = font_tiny.render("Up/Down select   Left/Right change   Enter confirm", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_paused(self) -> None:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        screen.blit(overlay, (0, 0))

        if self.lan_role == "client":
            t = font_big.render("HOST PAUSED", True, TEXT)
            screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, SCREEN_H // 2 - 60))
            sub = font_small.render("Waiting for the host to resume...", True, TEXT_DIM)
            screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, SCREEN_H // 2 - 10))
            s = font_tiny.render("Esc: leave game", True, TEXT_DIM)
            screen.blit(s, (SCREEN_W // 2 - s.get_width() // 2, SCREEN_H // 2 + 40))
            return

        t = font_big.render("PAUSED", True, TEXT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, SCREEN_H // 2 - 130))

        items = self._pause_items()
        for i, item in enumerate(items):
            selected = i == self.pause_index
            color = ACCENT if selected else TEXT
            prefix = "> " if selected else "  "
            text = font_mid.render(prefix + item, True, color)
            screen.blit(text, (SCREEN_W // 2 - 100, SCREEN_H // 2 - 50 + i * 40))

        if self.lan_role == "host":
            note = font_tiny.render("Your friend also sees PAUSED while you're here.", True, TEXT_DIM)
            screen.blit(note, (SCREEN_W // 2 - note.get_width() // 2, SCREEN_H // 2 - 50 + len(items) * 40 + 6))

        s = font_tiny.render("Up/Down select   Enter confirm   P resume   Esc menu", True, TEXT_DIM)
        screen.blit(s, (SCREEN_W // 2 - s.get_width() // 2, SCREEN_H // 2 + 130))

    def draw_game_over(self) -> None:
        screen.fill(BG)
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

        foot = font_small.render("Enter: play again    Esc: main menu", True, ACCENT)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 60))

    def draw_leaderboard(self) -> None:
        screen.fill(BG)
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
        foot = font_small.render("Esc: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def draw_enter_initials(self) -> None:
        screen.fill(BG)
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
            pygame.draw.rect(screen, (30, 32, 42), rect, border_radius=8)
            pygame.draw.rect(screen, color, rect, width=3, border_radius=8)
            letter_r = font_big.render(letter, True, TEXT)
            screen.blit(letter_r, (x + box_w // 2 - letter_r.get_width() // 2, y + box_w // 2 - letter_r.get_height() // 2))

        foot = font_small.render("Up/Down: letter   Left/Right: move   Enter: confirm", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, y + box_w + 40))

    def draw_achievements(self) -> None:
        screen.fill(BG)
        t = font_big.render("ACHIEVEMENTS", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 30))
        unlocked = self.tracker.unlocked
        stat_bests = self.data.get("stat_bests", {})
        cols = 2
        col_w = SCREEN_W // cols
        for i, ach in enumerate(ACHIEVEMENTS):
            col = i % cols
            row = i // cols
            x = 40 + col * col_w
            y = 90 + row * 52
            got = ach.id in unlocked
            color = GREEN if got else TEXT_DIM
            mark = "[x]" if got else "[ ]"
            name = font_small.render(f"{mark} {ach.name}", True, color)
            screen.blit(name, (x, y))
            desc = font_tiny.render(ach.description, True, TEXT_DIM)
            screen.blit(desc, (x + 14, y + 19))

            if ach.stat_key and ach.target:
                bar_w, bar_h = col_w - 60, 6
                bar_x, bar_y = x + 14, y + 36
                progress = min(1.0, stat_bests.get(ach.stat_key, 0) / ach.target)
                pygame.draw.rect(screen, (40, 42, 54), (bar_x, bar_y, bar_w, bar_h), border_radius=3)
                if progress > 0:
                    fill_color = GOLD if got else ACCENT
                    pygame.draw.rect(screen, fill_color, (bar_x, bar_y, int(bar_w * progress), bar_h), border_radius=3)
                best_val = stat_bests.get(ach.stat_key, 0)
                val_str = f"{int(best_val)}/{int(ach.target)}" if float(best_val).is_integer() else f"{best_val:.0f}/{int(ach.target)}"
                val_r = font_tiny.render(val_str, True, TEXT_DIM)
                screen.blit(val_r, (bar_x + bar_w + 8, bar_y - 5))

        pct = int(100 * len(unlocked) / len(ACHIEVEMENTS))
        foot = font_small.render(f"{len(unlocked)}/{len(ACHIEVEMENTS)} unlocked ({pct}%)   Esc: back", True, ACCENT)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_shop(self) -> None:
        screen.fill(BG)
        t = font_big.render("SHOP", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 40))
        wallet_r = font_mid.render(f"Wallet: {self.wallet} coins", True, GOLD)
        screen.blit(wallet_r, (SCREEN_W // 2 - wallet_r.get_width() // 2, 90))

        items = TRAIL_NAMES + ["Back"]
        y = 150
        for i, name in enumerate(items):
            selected = i == self.shop_index
            prefix = "> " if selected else "  "
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
                pygame.draw.circle(screen, (int(r * 255), int(g * 255), int(b * 255)), (cx, y + 12), 9)
            elif spec["color"] is not None:
                pygame.draw.circle(screen, spec["color"], (cx, y + 12), 9)
            else:
                pygame.draw.circle(screen, (90, 90, 100), (cx, y + 12), 9, width=2)

            status_r = font_tiny.render(status, True, status_color)
            screen.blit(status_r, (SCREEN_W // 2 + 90, y + 6))
            y += 44

        foot = font_tiny.render("Up/Down select   Enter buy/equip   Esc back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_lan_menu(self) -> None:
        screen.fill(BG)
        t = font_big.render("LAN MULTIPLAYER", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 60))
        sub = [
            "No internet or cloud server needed.",
            "One player hosts on the local network; the other joins by IP.",
        ]
        y = 110
        for line in sub:
            r = font_small.render(line, True, TEXT_DIM)
            screen.blit(r, (SCREEN_W // 2 - r.get_width() // 2, y))
            y += 22

        y = 200
        for i, item in enumerate(LAN_MENU_ITEMS):
            selected = i == self.lan_menu_index
            color = ACCENT if selected else TEXT
            prefix = "> " if selected else "  "
            text = font_mid.render(prefix + item, True, color)
            screen.blit(text, (SCREEN_W // 2 - 120, y))
            y += 44

        if self.local_ip:
            ip_r = font_small.render(f"Your LAN IP: {self.local_ip}", True, TEXT_DIM)
            screen.blit(ip_r, (SCREEN_W // 2 - ip_r.get_width() // 2, SCREEN_H - 60))

        foot = font_tiny.render("Up/Down select   Enter confirm   Esc back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_lan_host_wait(self) -> None:
        screen.fill(BG)
        t = font_big.render("HOSTING", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 100))

        ip_r = font_mid.render(f"IP: {self.local_ip}   Port: {network.DEFAULT_PORT}", True, GOLD)
        screen.blit(ip_r, (SCREEN_W // 2 - ip_r.get_width() // 2, 170))
        share_r = font_small.render("Share this with the other player on your network.", True, TEXT_DIM)
        screen.blit(share_r, (SCREEN_W // 2 - share_r.get_width() // 2, 210))

        dots = "." * (1 + int(pygame.time.get_ticks() / 400) % 3)
        waiting_r = font_mid.render(f"Waiting for player to join{dots}", True, TEXT)
        screen.blit(waiting_r, (SCREEN_W // 2 - waiting_r.get_width() // 2, 280))

        foot = font_small.render("Esc: cancel", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def draw_lan_join_ip(self) -> None:
        screen.fill(BG)
        t = font_big.render("JOIN GAME", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 100))
        sub = font_small.render("Enter the host's LAN IP address:", True, TEXT_DIM)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 170))

        cursor = "_" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
        box_w = 280
        rect = pygame.Rect(SCREEN_W // 2 - box_w // 2, 220, box_w, 50)
        pygame.draw.rect(screen, (30, 32, 42), rect, border_radius=8)
        pygame.draw.rect(screen, ACCENT, rect, width=2, border_radius=8)
        ip_r = font_mid.render(self.lan_ip_input + cursor, True, TEXT)
        screen.blit(ip_r, (rect.x + 14, rect.y + 12))

        foot = font_tiny.render("Type IP   Enter connect   Backspace delete   Esc cancel", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_lan_connecting(self) -> None:
        screen.fill(BG)
        t = font_big.render("CONNECTING", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 140))
        ip = self.lan_client.ip if self.lan_client else ""
        dots = "." * (1 + int(pygame.time.get_ticks() / 400) % 3)
        sub = font_mid.render(f"Connecting to {ip}{dots}", True, TEXT)
        screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 210))
        foot = font_small.render("Esc: cancel", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def draw_lan_error(self) -> None:
        screen.fill(BG)
        t = font_big.render("CONNECTION ERROR", True, DANGER)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 160))
        msg_r = font_small.render(str(self.lan_error_msg), True, TEXT)
        screen.blit(msg_r, (SCREEN_W // 2 - msg_r.get_width() // 2, 220))
        foot = font_small.render("Enter / Esc: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 40))

    def draw_settings(self) -> None:
        screen.fill(BG)
        t = font_big.render("SETTINGS", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 60))

        vol_label = "Muted" if self.sounds.muted else f"{round(self.sounds.master_volume * 100)}%"
        values = [
            f"< {vol_label} >",
            f"< {self.difficulty} >",
            f"< {'On' if self.screen_shake_enabled else 'Off'} >",
            f"< {'Muted' if self.sounds.muted else 'Unmuted'} >",
            f"< {'On' if self.colorblind else 'Off'} >",
            "",
        ]
        y = 150
        for i, label in enumerate(SETTINGS_ITEMS):
            selected = i == self.settings_index
            color = ACCENT if selected else TEXT
            prefix = "> " if selected else "  "
            line = f"{prefix}{label}"
            if values[i]:
                line += "  " + values[i]
            text = font_mid.render(line, True, color)
            screen.blit(text, (SCREEN_W // 2 - 160, y))
            y += 44

        foot = font_tiny.render("Left/Right change   Enter on Back / Esc to return", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_stats(self) -> None:
        screen.fill(BG)
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

        foot = font_small.render("Esc: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def _draw_run_history_chart(self, x: int, y: int, w: int, h: int) -> None:
        """Single-series bar chart of the last 20 runs, oldest to newest."""
        screen.blit(font_small.render("LAST 20 RUNS", True, ACCENT), (x, y))
        history = self.data.get("run_history", [])[-20:]
        plot_top = y + 34
        plot_h = h - 34 - 22
        baseline = plot_top + plot_h
        pygame.draw.line(screen, (48, 52, 66), (x, baseline), (x + w, baseline), 1)

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
                pygame.draw.rect(screen, bar_color, rect,
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
        screen.fill(BG)
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
        foot = font_small.render("Esc: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def _draw_food_icon(self, kind: str, cx: int, cy: int) -> None:
        radius = 7
        pygame.draw.circle(screen, self.food_color(kind), (cx, cy), radius)
        if kind == FOOD_BOMB:
            pygame.draw.circle(screen, DANGER, (cx, cy), radius, 2)
        elif kind == FOOD_CURSE:
            pygame.draw.line(screen, (255, 255, 255), (cx - 3, cy - 3), (cx + 3, cy + 3), 2)
            pygame.draw.line(screen, (255, 255, 255), (cx - 3, cy + 3), (cx + 3, cy - 3), 2)

    def draw_howto(self) -> None:
        screen.fill(BG)
        t = font_big.render("HOW TO PLAY", True, ACCENT)
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 24))

        left_x, right_x = 60, 540
        y = 84
        screen.blit(font_small.render("CONTROLS", True, ACCENT), (left_x, y)); y += 24
        for line in [
            "Arrows / WASD   move",
            "P   pause      M   mute      Esc   menu",
            "Coop: P1 = Arrows, P2 = WASD",
        ]:
            screen.blit(font_tiny.render(line, True, TEXT), (left_x, y)); y += 18

        y += 14
        screen.blit(font_small.render("FOOD", True, ACCENT), (left_x, y)); y += 24
        foods = [
            (FOOD_NORMAL, "Food: +10 x combo, grow 1"),
            (FOOD_GOLDEN, "Golden: +50, grow 1"),
            (FOOD_SPEED, "Speed: +10, 4s speed boost"),
            (FOOD_SHRINK, "Shrink: lose 2 length, -5"),
            (FOOD_CURSE, "Curse (X): controls reversed 4.5s"),
            (FOOD_BOMB, "Bomb (ring): instant death unless shielded"),
        ]
        for kind, desc in foods:
            self._draw_food_icon(kind, left_x + 8, y + 8)
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
        ]
        for kind, desc in powerups:
            rect = pygame.Rect(right_x + 1, y + 1, 14, 14)
            pygame.draw.rect(screen, self.powerup_color(kind), rect, width=2, border_radius=4)
            screen.blit(font_tiny.render(desc, True, TEXT), (right_x + 24, y + 1))
            y += 22

        y += 14
        screen.blit(font_small.render("MODES", True, ACCENT), (right_x, y)); y += 24
        for mode in MODES:
            screen.blit(font_tiny.render(f"{mode:<9} {MODE_DESC[mode]}", True, TEXT_DIM), (right_x, y)); y += 18

        foot = font_small.render("Esc: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    def draw_quests(self) -> None:
        screen.fill(BG)
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
            pygame.draw.rect(screen, (26, 29, 40), rect, border_radius=10)
            pygame.draw.rect(screen, GREEN if done else (48, 52, 66), rect, width=2, border_radius=10)
            screen.blit(font_mid.render(quest.description, True, TEXT if not done else TEXT_DIM), (x + 20, y + 14))
            status = font_small.render("DONE" if done else f"+{quest.reward} coins", True, GREEN if done else GOLD)
            screen.blit(status, (x + card_w - status.get_width() - 20, y + 42))
            y += card_h + 16

        note = font_tiny.render("Quests are checked when a run ends. Each pays out once per day.", True, TEXT_DIM)
        screen.blit(note, (SCREEN_W // 2 - note.get_width() // 2, y + 6))

        foot = font_small.render("Esc: back", True, TEXT_DIM)
        screen.blit(foot, (SCREEN_W // 2 - foot.get_width() // 2, SCREEN_H - 30))

    # ---------- input ----------

    def handle_menu_key(self, key) -> None:
        n = len(MENU_ITEMS)
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
                self.reset_run()
                self.state = STATE_PLAYING
            elif choice == "LAN Multiplayer":
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
            elif choice == "Quit":
                pygame.quit()
                sys.exit(0)

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
            if choice == "Host Game":
                try:
                    self.lan_host = network.Host()
                    self.state = STATE_LAN_HOST_WAIT
                except OSError as e:
                    self.lan_error_msg = f"Could not start hosting: {e}"
                    self.state = STATE_LAN_ERROR
            elif choice == "Join Game":
                self.lan_ip_input = ""
                self.state = STATE_LAN_JOIN_IP
            elif choice == "Back":
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
        if self.lan_role == "client":
            d = None
            if key in (pygame.K_UP, pygame.K_w):
                d = (0, -1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                d = (0, 1)
            elif key in (pygame.K_LEFT, pygame.K_a):
                d = (-1, 0)
            elif key in (pygame.K_RIGHT, pygame.K_d):
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
            return

        cfg = self.mode_cfg()
        is_lan_host = self.lan_role == "host"
        if cfg["coop"]:
            if key == pygame.K_UP:
                self.player.set_direction((0, -1))
            elif key == pygame.K_DOWN:
                self.player.set_direction((0, 1))
            elif key == pygame.K_LEFT:
                self.player.set_direction((-1, 0))
            elif key == pygame.K_RIGHT:
                self.player.set_direction((1, 0))
            elif not is_lan_host and key == pygame.K_w and self.player2:
                self.player2.set_direction((0, -1))
            elif not is_lan_host and key == pygame.K_s and self.player2:
                self.player2.set_direction((0, 1))
            elif not is_lan_host and key == pygame.K_a and self.player2:
                self.player2.set_direction((-1, 0))
            elif not is_lan_host and key == pygame.K_d and self.player2:
                self.player2.set_direction((1, 0))
        else:
            if key in (pygame.K_UP, pygame.K_w):
                self.player.set_direction((0, -1))
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.player.set_direction((0, 1))
            elif key in (pygame.K_LEFT, pygame.K_a):
                self.player.set_direction((-1, 0))
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.player.set_direction((1, 0))

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

    def handle_settings_key(self, key) -> None:
        n = len(SETTINGS_ITEMS)
        if key in (pygame.K_UP, pygame.K_w):
            self.settings_index = (self.settings_index - 1) % n
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.settings_index = (self.settings_index + 1) % n
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            direction = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
            if self.settings_index == 0:
                vol = round(self.sounds.master_volume * 100)
                vol = max(0, min(100, vol + direction * 10))
                self.sounds.master_volume = vol / 100
                self.save_settings()
            elif self.settings_index == 1:
                idx = DIFFICULTIES.index(self.difficulty)
                self.difficulty = DIFFICULTIES[(idx + direction) % len(DIFFICULTIES)]
                self.save_settings()
            elif self.settings_index == 2:
                self.screen_shake_enabled = not self.screen_shake_enabled
                self.save_settings()
            elif self.settings_index == 3:
                self.sounds.muted = not self.sounds.muted
                self.save_settings()
            elif self.settings_index == 4:
                self.colorblind = not self.colorblind
                self.save_settings()
        elif key == pygame.K_RETURN:
            choice = SETTINGS_ITEMS[self.settings_index]
            if choice == "Mute":
                self.sounds.muted = not self.sounds.muted
                self.save_settings()
            elif choice == "Color Blind Mode":
                self.colorblind = not self.colorblind
                self.save_settings()
            elif choice == "Back":
                self.state = self.prev_state
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

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        key = event.key

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
        elif self.state == STATE_LAN_HOST_WAIT:
            if key == pygame.K_ESCAPE:
                if self.lan_host:
                    self.lan_host.close()
                self.lan_host = None
                self.state = STATE_LAN_MENU
        elif self.state == STATE_LAN_JOIN_IP:
            self.handle_lan_join_ip_key(key)
        elif self.state == STATE_LAN_CONNECTING:
            if key == pygame.K_ESCAPE:
                self.lan_client = None
                self.state = STATE_LAN_JOIN_IP
        elif self.state == STATE_LAN_ERROR:
            if key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self._lan_teardown()
                self.state = STATE_LAN_MENU
        elif self.state in (STATE_LEADERBOARD, STATE_ACHIEVEMENTS, STATE_STATS, STATE_CHANGELOG,
                            STATE_HOWTO, STATE_QUESTS):
            if key == pygame.K_ESCAPE:
                self.state = STATE_MENU

    # ---------- main loop ----------

    def run(self) -> None:
        while True:
            dt = clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                self.handle_event(event)

            if self.state == STATE_LAN_HOST_WAIT:
                self._lan_host_poll()
            elif self.state == STATE_LAN_CONNECTING:
                self._lan_connecting_poll()
            elif self.state == STATE_PAUSED and self.lan_role == "host":
                self._lan_host_pause_poll()
            elif self.state == STATE_PAUSED and self.lan_role == "client":
                self._lan_client_poll(dt)

            if self.state == STATE_PLAYING:
                if self.lan_role == "client":
                    self._lan_client_poll(dt)
                else:
                    self.update_playing(dt)
                if self.state == STATE_PLAYING:
                    alpha = 1.0 if self.lan_role else min(1.0, self.move_accum / self.move_interval())
                    self.draw_playing(alpha)
                    self.draw_sidebar()
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
            elif self.state == STATE_LAN_HOST_WAIT:
                self.draw_lan_host_wait()
            elif self.state == STATE_LAN_JOIN_IP:
                self.draw_lan_join_ip()
            elif self.state == STATE_LAN_CONNECTING:
                self.draw_lan_connecting()
            elif self.state == STATE_LAN_ERROR:
                self.draw_lan_error()
            elif self.state == STATE_HOWTO:
                self.draw_howto()
            elif self.state == STATE_QUESTS:
                self.draw_quests()

            pygame.display.flip()


if __name__ == "__main__":
    Game().run()
