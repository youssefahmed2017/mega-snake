# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Save/load progress to a JSON file in the user's home dir: high scores, achievements,
the coin wallet & owned cosmetics, daily streak, and run history."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from constants import SAVE_DIR_NAME
from settings_defs import SETTING_DEFAULTS

SAVE_DIR = Path.home() / SAVE_DIR_NAME
SAVE_FILE = SAVE_DIR / "save.json"
# Ghost trails live in their own compact file: thousands of [x, y, score]
# entries per mode would make the indented, human-readable save.json huge.
GHOST_FILE = SAVE_DIR / "ghosts.json"

DEFAULT_DATA = {
    "high_scores": [],  # list of {"score": int, "mode": str, "date": str, "initials": str}
    "run_history": [],  # list of {"score": int, "mode": str, "date": str} - last 20 runs, any rank
    "achievements": [],  # list of achievement ids unlocked
    "secret_shop_found": False,
    "pending_update": None,  # {"from", "to"} while an update relaunch is in flight  # once true, the menu easter egg skips its warnings
    "stat_bests": {},  # stat_key -> best value ever reached, for achievement progress bars
    "games_played": 0,
    "total_food_eaten": 0,
    "wallet": 0,
    "owned_trails": ["None"],
    "equipped_trail": "None",
    "streak": {"count": 0, "last_played": None},
    "quests": {"date": None, "completed": []},  # today's completed quest ids
    "settings": dict(SETTING_DEFAULTS),
}


def load() -> Dict[str, Any]:
    if not SAVE_FILE.exists():
        return json.loads(json.dumps(DEFAULT_DATA))
    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = json.loads(json.dumps(DEFAULT_DATA))
        merged.update(data)
        merged_settings = dict(DEFAULT_DATA["settings"])
        merged_settings.update(data.get("settings", {}))
        merged["settings"] = merged_settings
        merged_streak = dict(DEFAULT_DATA["streak"])
        merged_streak.update(data.get("streak", {}))
        merged["streak"] = merged_streak
        merged_quests = dict(DEFAULT_DATA["quests"])
        merged_quests.update(data.get("quests", {}))
        merged["quests"] = merged_quests
        if "None" not in merged.get("owned_trails", []):
            merged.setdefault("owned_trails", []).append("None")
        return merged
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_DATA))


def save(data: Dict[str, Any]) -> None:
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def add_high_score(data: Dict[str, Any], score: int, mode: str, date: str, initials: str = "---") -> List[Dict[str, Any]]:
    scores: List[Dict[str, Any]] = data.setdefault("high_scores", [])
    scores.append({"score": score, "mode": mode, "date": date, "initials": initials})
    scores.sort(key=lambda s: s["score"], reverse=True)
    del scores[10:]
    return scores


def would_qualify_for_leaderboard(data: Dict[str, Any], score: int) -> bool:
    scores = data.get("high_scores", [])
    if score <= 0:
        return False
    if len(scores) < 10:
        return True
    return score > min(s["score"] for s in scores)


def add_run_history(data: Dict[str, Any], score: int, mode: str, date: str) -> None:
    history: List[Dict[str, Any]] = data.setdefault("run_history", [])
    history.append({"score": score, "mode": mode, "date": date})
    del history[:-20]


def update_stat_bests(data: Dict[str, Any], stats: Dict[str, float]) -> None:
    bests: Dict[str, float] = data.setdefault("stat_bests", {})
    for key, value in stats.items():
        if key not in bests or value > bests[key]:
            bests[key] = value


def quest_state_for_today(data: Dict[str, Any], today_iso: str) -> Dict[str, Any]:
    """Returns today's quest record, clearing yesterday's completions on a new day."""
    q = data.setdefault("quests", {"date": None, "completed": []})
    if q.get("date") != today_iso:
        q["date"] = today_iso
        q["completed"] = []
    return q


def load_ghosts() -> Dict[str, Any]:
    if not GHOST_FILE.exists():
        return {}
    try:
        with open(GHOST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_ghost_if_better(ghosts: Dict[str, Any], mode: str, score: int, trail: List[List[int]]) -> bool:
    current = ghosts.get(mode)
    if not trail or (current is not None and score <= current.get("score", 0)):
        return False
    ghosts[mode] = {"score": score, "trail": trail}
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        with open(GHOST_FILE, "w", encoding="utf-8") as f:
            json.dump(ghosts, f, separators=(",", ":"))
    except OSError:
        pass
    return True


def apply_daily_streak(data: Dict[str, Any], today_iso: str, yesterday_iso: str) -> Optional[int]:
    """Advance the streak at most once per calendar day. Returns a coin bonus if the
    streak advanced (new day played), or None if today was already counted."""
    streak = data.setdefault("streak", {"count": 0, "last_played": None})
    if streak["last_played"] == today_iso:
        return None
    if streak["last_played"] == yesterday_iso:
        streak["count"] += 1
    else:
        streak["count"] = 1
    streak["last_played"] = today_iso
    return min(50, 10 * streak["count"])
