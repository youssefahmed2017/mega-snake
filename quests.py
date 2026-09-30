"""Daily quests: three objectives picked deterministically from today's date, each
paying coins once per day when a finished run satisfies it."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, List


@dataclass
class Quest:
    id: str
    description: str
    reward: int
    check: Callable[[dict, str], bool]  # (final run stats, mode name) -> done?


QUEST_POOL: List[Quest] = [
    Quest("eat_15", "Eat 15 food in one run", 25, lambda s, m: s["food_eaten"] >= 15),
    Quest("eat_30", "Eat 30 food in one run", 45, lambda s, m: s["food_eaten"] >= 30),
    Quest("combo_6", "Reach a 6x combo", 30, lambda s, m: s["combo_peak"] >= 6),
    Quest("combo_10", "Reach a 10x combo", 50, lambda s, m: s["combo_peak"] >= 10),
    Quest("golden_1", "Eat a golden apple", 20, lambda s, m: s["golden_eaten"] >= 1),
    Quest("golden_3", "Eat 3 golden apples in one run", 45, lambda s, m: s["golden_eaten"] >= 3),
    Quest("score_150", "Score 150 in one run", 30, lambda s, m: s["score"] >= 150),
    Quest("score_300", "Score 300 in one run", 55, lambda s, m: s["score"] >= 300),
    Quest("survive_60", "Survive 60 seconds", 25, lambda s, m: s["time_alive"] >= 60),
    Quest("survive_120", "Survive 2 minutes", 45, lambda s, m: s["time_alive"] >= 120),
    Quest("length_20", "Reach length 20", 35, lambda s, m: s["length"] >= 20),
    Quest("powerups_3", "Pick up 3 power-ups in one run", 30, lambda s, m: s["powerups_collected"] >= 3),
    Quest("maze_100", "Score 100 in Maze mode", 40, lambda s, m: m == "Maze" and s["score"] >= 100),
    Quest("walls_100", "Score 100 in Walls mode", 35, lambda s, m: m == "Walls" and s["score"] >= 100),
    Quest("battle_80", "Score 80 in Battle mode", 40, lambda s, m: m == "Battle" and s["score"] >= 80),
    Quest("portal_1", "Travel through a portal", 20, lambda s, m: s["portals_used"] >= 1),
]

QUESTS_BY_ID = {q.id: q for q in QUEST_POOL}
QUESTS_PER_DAY = 3


def quests_for_date(date_iso: str) -> List[Quest]:
    rng = random.Random("megasnake-quests-" + date_iso)
    return rng.sample(QUEST_POOL, QUESTS_PER_DAY)
