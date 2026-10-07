# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Declarative list of user settings. The Settings screen is generated from this, and
persistence takes its defaults from it, so adding a setting is one line here plus
whatever code reads it (via `Game.setting_get`)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

SETTING_TABS = ["Audio", "Gameplay", "Display", "Controller"]


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    tab: str
    kind: str                       # "toggle" | "slider" | "choice"
    default: Any
    options: Tuple[str, ...] = ()   # choice only
    lo: int = 0                     # slider only
    hi: int = 100
    step: int = 5
    unit: str = "%"
    hint: str = ""


SETTING_DEFS: List[SettingDef] = [
    # Audio
    SettingDef("volume", "Master Volume", "Audio", "slider", 100, lo=0, hi=100, step=5,
               hint="Drag the slider, or scroll the mouse wheel over it."),
    SettingDef("muted", "Mute", "Audio", "toggle", False, hint="Also on the M key and the sidebar speaker button."),
    SettingDef("ui_sounds", "Menu Sounds", "Audio", "toggle", True, hint="The blips when you move around menus."),
    # Gameplay
    SettingDef("difficulty", "Difficulty", "Gameplay", "choice", "Normal", options=("Easy", "Normal", "Hard"),
               hint="Changes how fast the snake moves."),
    SettingDef("auto_pause", "Pause When Unfocused", "Gameplay", "toggle", True,
               hint="Solo runs pause when you switch to another window."),
    SettingDef("callouts", "On-Screen Callouts", "Gameplay", "toggle", True,
               hint="The COMBO x5! / NEW PERSONAL BEST banners."),
    SettingDef("near_miss_slowmo", "Near-Miss Slow-Mo", "Gameplay", "toggle", True,
               hint="Brief slowdown when you scrape past a wall or tail."),
    SettingDef("show_ghost", "Ghost Replay", "Gameplay", "toggle", True,
               hint="Show your best run for this mode as a faint ghost."),
    # Display
    SettingDef("resolution", "Resolution", "Display", "choice", "1080p",
               options=("144p", "360p", "480p", "720p", "1080p", "4K"),
               hint="Render resolution. Lower is faster on weak machines; 4K is very demanding."),
    SettingDef("fullscreen", "Fullscreen", "Display", "toggle", True, hint="Also on F11. The game starts fullscreen."),
    SettingDef("transitions", "Screen Fades", "Display", "toggle", True,
               hint="Crossfade between screens instead of cutting."),
    SettingDef("screen_shake", "Screen Shake", "Display", "toggle", True),
    SettingDef("shake_strength", "Shake Strength", "Display", "slider", 100, lo=25, hi=150, step=25,
               hint="How hard the screen shakes when Screen Shake is on."),
    SettingDef("particles", "Particles", "Display", "choice", "Full", options=("Off", "Low", "Full"),
               hint="Lower this if the game stutters on your machine."),
    SettingDef("grid_lines", "Grid Lines", "Display", "toggle", False, hint="Faint cell lines over the checkered floor."),
    SettingDef("colorblind", "Color Blind Mode", "Display", "toggle", False),
    SettingDef("show_fps", "Show FPS", "Display", "toggle", False),
    # Controller
    SettingDef("controller_enabled", "Controller Input", "Controller", "toggle", True,
               hint="Turn off to ignore gamepads completely."),
    SettingDef("stick_sensitivity", "Stick Sensitivity", "Controller", "choice", "Normal",
               options=("Low", "Normal", "High"), hint="How far you push the left stick before it counts as a turn."),
    SettingDef("rumble", "Vibration", "Controller", "toggle", True,
               hint="Buzz when you eat and when you die. Only while playing with the pad."),
    SettingDef("rumble_strength", "Vibration Strength", "Controller", "slider", 100, lo=25, hi=100, step=25),
]

SETTING_BY_KEY: Dict[str, SettingDef] = {d.key: d for d in SETTING_DEFS}
SETTING_DEFAULTS: Dict[str, Any] = {d.key: d.default for d in SETTING_DEFS}
STICK_ENGAGE = {"Low": 24000, "Normal": 18000, "High": 12000}  # axis value (of 32767) that registers a turn
PARTICLE_DENSITY = {"Off": 0.0, "Low": 0.45, "Full": 1.0}
