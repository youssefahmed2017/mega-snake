"""Achievement definitions and a tracker that checks stats against them each frame."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class Achievement:
    id: str
    name: str
    description: str
    check: Callable[[dict], bool]
    # For achievements that map to a single numeric stat, these let the UI draw a
    # progress bar (e.g. "12/15") even before it's unlocked. Leave stat_key=None
    # for binary/event-style achievements (no meaningful "progress").
    stat_key: Optional[str] = None
    target: Optional[float] = None
    # Hidden achievements show as "???" until unlocked. Ones whose check never
    # passes (lambda s: False) are unlocked directly by game events instead.
    hidden: bool = False


ACHIEVEMENTS: List[Achievement] = [
    Achievement("first_blood", "First Blood", "Eat your first food", lambda s: s["food_eaten"] >= 1),
    Achievement("gourmand", "Gourmand", "Eat 50 food in one run", lambda s: s["food_eaten"] >= 50, "food_eaten", 50),
    Achievement("combo_5", "Combo Starter", "Reach a 5x combo", lambda s: s["combo"] >= 5, "combo", 5),
    Achievement("combo_15", "Combo Master", "Reach a 15x combo", lambda s: s["combo"] >= 15, "combo", 15),
    Achievement("golden_touch", "Golden Touch", "Eat a golden apple", lambda s: s["golden_eaten"] >= 1),
    Achievement("bomb_defused", "Bomb Defused", "Survive a bomb with a shield", lambda s: s["bombs_survived"] >= 1),
    Achievement("long_boi", "Long Boi", "Reach length 30", lambda s: s["length"] >= 30, "length", 30),
    Achievement("century", "Century", "Score 100 points", lambda s: s["score"] >= 100, "score", 100),
    Achievement("half_k", "High Roller", "Score 500 points", lambda s: s["score"] >= 500, "score", 500),
    Achievement("speed_demon", "Speed Demon", "Reach max speed tier", lambda s: s["speed_tier"] >= 5, "speed_tier", 5),
    Achievement("ghost_walker", "Ghost Walker", "Pass through a wall using Ghost mode", lambda s: s["wall_phases"] >= 1),
    Achievement("survivor", "Survivor", "Survive 3 minutes in one run", lambda s: s["time_alive"] >= 180, "time_alive", 180),
    Achievement("trespasser", "Trespasser", "Found a place you weren't supposed to be", lambda s: False, hidden=True),

    # --- skill & per-run feats ---
    Achievement("close_call", "Close Call", "Scrape past a wall or tail and live", lambda s: s.get("near_misses", 0) >= 1),
    Achievement("edge_lord", "Edge Lord", "Get 10 near misses in one run", lambda s: s.get("near_misses", 0) >= 10, "near_misses", 10),
    Achievement("golden_trio", "Golden Trio", "Eat 3 golden apples in one run", lambda s: s["golden_eaten"] >= 3, "golden_eaten", 3),
    Achievement("fully_charged", "Fully Charged", "Pick up 5 power-ups in one run", lambda s: s["powerups_collected"] >= 5, "powerups_collected", 5),
    Achievement("portal_hopper", "Portal Hopper", "Travel through 3 portals in one run", lambda s: s["portals_used"] >= 3, "portals_used", 3),
    Achievement("bomb_squad", "Bomb Squad", "Survive 3 bombs in one run", lambda s: s["bombs_survived"] >= 3, "bombs_survived", 3),
    Achievement("poltergeist", "Poltergeist", "Phase through walls 5 times in one run", lambda s: s["wall_phases"] >= 5, "wall_phases", 5),
    Achievement("maxed_out", "Maxed Out", "Reach a 20x combo", lambda s: s["combo"] >= 20, "combo", 20),
    Achievement("longer_boi", "Longer Boi", "Reach length 50", lambda s: s["length"] >= 50, "length", 50),
    Achievement("legend", "Legend", "Score 1000 points", lambda s: s["score"] >= 1000, "score", 1000),
    Achievement("marathon", "Marathon", "Survive 5 minutes in one run", lambda s: s["time_alive"] >= 300, "time_alive", 300),

    # --- mode specialists ---
    Achievement("maze_runner", "Maze Runner", "Score 100 in Maze mode", lambda s: s.get("mode") == "Maze" and s["score"] >= 100),
    Achievement("wall_crawler", "Wall Crawler", "Score 100 in Walls mode", lambda s: s.get("mode") == "Walls" and s["score"] >= 100),
    Achievement("battle_hardened", "Battle Hardened", "Score 80 in Battle mode", lambda s: s.get("mode") == "Battle" and s["score"] >= 80),
    Achievement("beat_the_clock", "Beat the Clock", "Score 150 in Timed mode", lambda s: s.get("mode") == "Timed" and s["score"] >= 150),
    Achievement("hardcore_100", "No Safety Net", "Score 100 in Hardcore mode", lambda s: s.get("mode") == "Hardcore" and s["score"] >= 100),
    Achievement("daily_driver", "Daily Driver", "Score 50 in a Daily run", lambda s: s.get("mode") == "Daily" and s["score"] >= 50),
    Achievement("chaos_survivor", "Chaos Survivor", "Live through 3 chaos events in one run",
                lambda s: s.get("events_survived", 0) >= 3),
    Achievement("fully_loaded", "Fully Loaded", "Pick 5 perks in one Roguelite run",
                lambda s: s.get("perks_picked", 0) >= 5),
    Achievement("meteor_dodger", "Duck and Cover", "Dodge 8 meteors in one Hardcore run",
                lambda s: s.get("meteors_dodged", 0) >= 8),
    Achievement("roguelite_150", "Build Master", "Score 150 in Roguelite mode",
                lambda s: s.get("mode") == "Roguelite" and s["score"] >= 150),

    # --- long-term progress ---
    Achievement("regular", "Regular", "Play 10 games", lambda s: s.get("lifetime_games", 0) >= 10, "lifetime_games", 10),
    Achievement("veteran", "Veteran", "Play 50 games", lambda s: s.get("lifetime_games", 0) >= 50, "lifetime_games", 50),
    Achievement("food_hoarder", "Food Hoarder", "Eat 250 food in total", lambda s: s.get("lifetime_food", 0) >= 250, "lifetime_food", 250),
    Achievement("bottomless", "Bottomless Pit", "Eat 1000 food in total", lambda s: s.get("lifetime_food", 0) >= 1000, "lifetime_food", 1000),
    Achievement("on_a_roll", "On a Roll", "Play 3 days in a row", lambda s: s.get("streak", 0) >= 3, "streak", 3),
    Achievement("dedicated", "Dedicated", "Play 7 days in a row", lambda s: s.get("streak", 0) >= 7, "streak", 7),
    Achievement("quest_clear", "Quest Clear", "Finish all daily quests in one day", lambda s: s.get("quests_today", 0) >= 3, "quests_today", 3),

    # --- shop & settings (unlocked directly by game events) ---
    Achievement("tinkerer", "Tinkerer", "Change a setting", lambda s: False),
    Achievement("fashionista", "Fashionista", "Buy a trail in the shop", lambda s: False),
    Achievement("collector", "Collector", "Own every shop trail", lambda s: False),
    Achievement("record_breaker", "Record Breaker", "Beat your personal best in any mode", lambda s: False),
]

ACHIEVEMENTS_BY_ID: Dict[str, Achievement] = {a.id: a for a in ACHIEVEMENTS}


class AchievementTracker:
    def __init__(self, unlocked_ids: List[str]) -> None:
        self.unlocked = set(unlocked_ids)
        self.pending_popups: List[Achievement] = []

    def check(self, stats: dict) -> List[Achievement]:
        newly = []
        for ach in ACHIEVEMENTS:
            if ach.id in self.unlocked:
                continue
            if ach.check(stats):
                self.unlocked.add(ach.id)
                newly.append(ach)
                self.pending_popups.append(ach)
        return newly
