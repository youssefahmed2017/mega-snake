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
