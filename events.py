"""Chaos events and roguelite perks. Pure logic, no pygame: main.py applies the effects.

An EventDirector walks one run through idle -> warning -> active -> idle. Every random
draw (which event, how long to wait) comes from the rng it is given, never from elapsed
time, so two directors built from the same seed produce the same schedule - that is what
makes Daily's events identical for everyone.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

Color = Tuple[int, int, int]

EVENT_FRENZY = "frenzy"
EVENT_GOLD_RUSH = "gold_rush"
EVENT_BLACKOUT = "blackout"
EVENT_MIRROR = "mirror"
EVENT_HUNTER = "hunter"
EVENT_QUAKE = "quake"


@dataclass(frozen=True)
class EventDef:
    id: str
    name: str
    color: Color
    duration: float
    desc: str


EVENTS: Dict[str, EventDef] = {e.id: e for e in (
    EventDef(EVENT_FRENZY, "FOOD FRENZY", (255, 170, 60), 10.0, "Food everywhere. Eat, eat, eat!"),
    EventDef(EVENT_GOLD_RUSH, "GOLD RUSH", (255, 215, 0), 12.0, "All food is golden and worth double."),
    EventDef(EVENT_BLACKOUT, "BLACKOUT", (130, 145, 210), 12.0, "The lights are out. Trust your head."),
    EventDef(EVENT_MIRROR, "MIRROR MODE", (190, 120, 255), 8.0, "Controls reversed!"),
    EventDef(EVENT_HUNTER, "HUNTER", (255, 70, 70), 14.0, "A hunter snake is after you."),
    EventDef(EVENT_QUAKE, "EARTHQUAKE", (210, 150, 100), 9.0, "The ground cracks. Rubble drops!"),
)}
EVENT_IDS = list(EVENTS)

# Events are meant to be rare surprises: ~one every 1.5-2 minutes, active about 10% of the time.
FIRST_EVENT_DELAY = 75.0
EVENT_GAP = (75.0, 120.0)  # quiet time between the end of one event and the warning for the next
EVENT_WARNING = 3.0


def featured_event(date_iso: str) -> str:
    """Today's Daily 'mutator': the event that comes round three times as often."""
    return random.Random("featured" + date_iso).choice(EVENT_IDS)


class EventDirector:
    def __init__(self, rng: random.Random, featured: Optional[str] = None,
                 first_delay: float = FIRST_EVENT_DELAY, gap: Tuple[float, float] = EVENT_GAP,
                 warning: float = EVENT_WARNING) -> None:
        self.rng = rng
        self.weights = {eid: (3 if eid == featured else 1) for eid in EVENT_IDS}
        self.gap = gap
        self.warning = warning
        self.active: Optional[str] = None
        self.remaining = 0.0
        self.incoming: Optional[str] = None  # set during the warning window
        self.countdown = first_delay          # seconds until the next phase change
        self._next = self._pick(None)
        self.started = 0

    def _pick(self, last: Optional[str]) -> str:
        ids = [e for e in EVENT_IDS if e != last]
        return self.rng.choices(ids, weights=[self.weights[e] for e in ids], k=1)[0]

    def update(self, dt: float) -> List[Tuple[str, str]]:
        """Advance by dt; returns the ("warn" | "start" | "end", event_id) changes, in order."""
        out: List[Tuple[str, str]] = []
        if self.active:
            self.remaining -= dt
            if self.remaining <= 0:
                out.append(("end", self.active))
                last = self.active
                self.active = None
                self._next = self._pick(last)
                self.countdown = self.rng.uniform(*self.gap)
            return out
        self.countdown -= dt
        if self.incoming is None and self.countdown <= self.warning:
            self.incoming = self._next
            out.append(("warn", self.incoming))
        if self.countdown <= 0:
            self.active = self.incoming or self._next
            self.incoming = None
            self.remaining = EVENTS[self.active].duration
            self.started += 1
            out.append(("start", self.active))
        return out

    @property
    def warn_left(self) -> float:
        return max(0.0, self.countdown) if self.incoming else 0.0


# ---------------------------------------------------------------- perks (Roguelite)

PERK_EVERY_FOODS = 8


@dataclass(frozen=True)
class PerkDef:
    id: str
    name: str
    desc: str
    color: Color
    max_stack: int = 3


PERKS: Dict[str, PerkDef] = {p.id: p for p in (
    PerkDef("second_wind", "Second Wind", "Survive one fatal crash.", (120, 255, 190)),
    PerkDef("magnet_field", "Magnet Field", "Food within a few cells drifts into you.", (255, 120, 120)),
    PerkDef("gourmet", "Gourmet", "+25% score from every food.", (255, 215, 0)),
    PerkDef("midas", "Midas Touch", "+50% coins at the end of the run.", (255, 190, 60)),
    PerkDef("featherweight", "Featherweight", "The snake moves 8% slower.", (150, 210, 255)),
    PerkDef("lucky_charm", "Lucky Charm", "Power-ups show up far more often.", (150, 255, 120)),
    PerkDef("combo_keeper", "Combo Keeper", "Combos last 1s longer.", (255, 150, 220)),
    PerkDef("dash", "Phase Dash", "Space / A: phase through everything for 1.2s (10s cooldown).",
            (190, 140, 255), max_stack=1),
)}


def roll_perk_choices(rng: random.Random, owned: Dict[str, int], k: int = 3) -> List[str]:
    pool = [p.id for p in PERKS.values() if owned.get(p.id, 0) < p.max_stack]
    rng.shuffle(pool)
    return pool[:k]
