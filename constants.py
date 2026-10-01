"""All tunable constants live here."""

CELL_SIZE = 24
GRID_W, GRID_H = 32, 22
SIDEBAR_W = 260
SCREEN_W = GRID_W * CELL_SIZE + SIDEBAR_W
SCREEN_H = GRID_H * CELL_SIZE
FPS = 60

BASE_MOVE_INTERVAL = 0.12  # seconds per grid step at speed 1.0

# Colors
BG = (14, 16, 22)
GRID_LINE = (22, 25, 33)
SIDEBAR_BG = (20, 22, 30)
TEXT = (235, 235, 245)
TEXT_DIM = (140, 145, 160)
ACCENT = (90, 200, 255)
DANGER = (255, 90, 90)
GOLD = (255, 210, 80)
GREEN = (110, 230, 140)
PURPLE = (190, 120, 255)
CURSE_COLOR = (170, 0, 110)
PORTAL_A = (80, 200, 255)
PORTAL_B = (255, 120, 220)
P2_COLOR = [(255, 170, 80), (210, 120, 40)]

SNAKE_SKINS = {
    "Classic": [(110, 230, 140), (70, 180, 110)],
    "Inferno": [(255, 160, 60), (200, 60, 30)],
    "Void": [(190, 120, 255), (90, 40, 150)],
    "Ice": [(140, 220, 255), (60, 140, 220)],
    "Gold": [(255, 220, 100), (200, 160, 40)],
}

# Skin -> achievement id required to unlock it. None = always unlocked.
SKIN_UNLOCK_REQUIREMENT = {
    "Classic": None,
    "Inferno": "century",
    "Void": "combo_15",
    "Ice": "survivor",
    "Gold": "half_k",
}

FOOD_NORMAL = "normal"
FOOD_GOLDEN = "golden"
FOOD_SPEED = "speed"
FOOD_SHRINK = "shrink"
FOOD_BOMB = "bomb"
FOOD_CURSE = "curse"

FOOD_WEIGHTS = {
    FOOD_NORMAL: 56,
    FOOD_GOLDEN: 10,
    FOOD_SPEED: 10,
    FOOD_SHRINK: 8,
    FOOD_BOMB: 9,
    FOOD_CURSE: 7,
}

FOOD_COLORS = {
    FOOD_NORMAL: (255, 90, 90),
    FOOD_GOLDEN: GOLD,
    FOOD_SPEED: (90, 200, 255),
    FOOD_SHRINK: PURPLE,
    FOOD_BOMB: (30, 30, 30),
    FOOD_CURSE: CURSE_COLOR,
}

POWERUP_GHOST = "ghost"
POWERUP_MAGNET = "magnet"
POWERUP_SHIELD = "shield"
POWERUP_SLOWMO = "slowmo"
POWERUP_MULT = "mult2x"
POWERUP_FREEZE = "freeze"
POWERUP_TELEPORT = "teleport"
POWERUP_REVIVE = "revive"  # coop/LAN only - spawns only while a teammate is down

POWERUP_COLORS = {
    POWERUP_GHOST: (200, 220, 255),
    POWERUP_MAGNET: (255, 140, 200),
    POWERUP_SHIELD: (120, 255, 190),
    POWERUP_SLOWMO: (150, 150, 255),
    POWERUP_MULT: GOLD,
    POWERUP_FREEZE: (140, 220, 255),
    POWERUP_TELEPORT: (255, 255, 255),
    POWERUP_REVIVE: (255, 80, 130),
}

# Okabe-Ito palette: distinguishable under the common forms of color-vision
# deficiency. Bomb and curse keep their shape markers (ring / X) as well.
COLORBLIND_FOOD_COLORS = {
    FOOD_NORMAL: (213, 94, 0),
    FOOD_GOLDEN: (240, 228, 66),
    FOOD_SPEED: (86, 180, 233),
    FOOD_SHRINK: (204, 121, 167),
    FOOD_BOMB: (30, 30, 30),
    FOOD_CURSE: (0, 114, 178),
}

COLORBLIND_POWERUP_COLORS = {
    POWERUP_GHOST: (230, 230, 230),
    POWERUP_MAGNET: (204, 121, 167),
    POWERUP_SHIELD: (0, 158, 115),
    POWERUP_SLOWMO: (0, 114, 178),
    POWERUP_MULT: (240, 228, 66),
    POWERUP_FREEZE: (86, 180, 233),
    POWERUP_TELEPORT: (230, 159, 0),
    POWERUP_REVIVE: (213, 94, 0),
}

# Durations in seconds. Instant-effect power-ups (teleport) aren't in here.
POWERUP_DURATIONS = {
    POWERUP_GHOST: 6.0,
    POWERUP_MAGNET: 8.0,
    POWERUP_SHIELD: 12.0,
    POWERUP_SLOWMO: 5.0,
    POWERUP_MULT: 10.0,
    POWERUP_FREEZE: 6.0,
}

CURSE_DURATION = 4.5

MODES = ["Classic", "Walls", "Maze", "Battle", "Timed", "Hardcore", "Coop", "Daily"]

# wrap: edges wrap instead of killing. powerups: power-ups spawn. obstacles: maze-style
# growth. rivals: number of AI rival snakes. timer: seconds for a countdown mode (or None).
# coop: local two-player. seeded: today's date seeds the initial layout.
MODE_CONFIG = {
    "Classic": dict(wrap=True, powerups=True, obstacles=False, rivals=0, timer=None, coop=False, seeded=False, speed_mult=1.0),
    "Walls": dict(wrap=False, powerups=True, obstacles=False, rivals=0, timer=None, coop=False, seeded=False, speed_mult=1.0),
    "Maze": dict(wrap=False, powerups=True, obstacles=True, rivals=0, timer=None, coop=False, seeded=False, speed_mult=1.0),
    "Battle": dict(wrap=False, powerups=True, obstacles=False, rivals=2, timer=None, coop=False, seeded=False, speed_mult=1.0),
    "Timed": dict(wrap=True, powerups=True, obstacles=False, rivals=0, timer=60, coop=False, seeded=False, speed_mult=1.0),
    "Hardcore": dict(wrap=False, powerups=False, obstacles=True, rivals=0, timer=None, coop=False, seeded=False, speed_mult=1.35),
    "Coop": dict(wrap=False, powerups=True, obstacles=False, rivals=0, timer=None, coop=True, seeded=False, speed_mult=1.0),
    "Daily": dict(wrap=False, powerups=True, obstacles=True, rivals=0, timer=None, coop=False, seeded=True, speed_mult=1.0),
}

MODE_DESC = {
    "Classic": "Wrap around edges. Pure snake.",
    "Walls": "Edges kill you. No mercy.",
    "Maze": "Walls + obstacles that grow over time.",
    "Battle": "Walls + two AI rivals want your food.",
    "Timed": "60 second score attack. Wraps around.",
    "Hardcore": "No power-ups. Faster ramp. One life.",
    "Coop": "Local 2-player. Arrows + WASD, shared board.",
    "Daily": "Same seeded layout for everyone, today only.",
}

# LAN match setup: the host picks a ruleset (wrap/obstacle behavior) and a map
# (a fixed obstacle layout, independent of the ruleset's own procedural growth)
# before opening the socket. Both apply on top of the shared Coop rules (2
# snakes, shared score) - they don't change who can join or how.
LAN_RULESETS = {
    "Classic": {"wrap": True, "obstacles": False, "desc": "Wrap around edges."},
    "Walls": {"wrap": False, "obstacles": False, "desc": "Edges kill you."},
    "Maze": {"wrap": False, "obstacles": True, "desc": "Obstacles grow over time."},
}
LAN_RULESET_NAMES = list(LAN_RULESETS.keys())


def _ring(margin: int) -> set:
    pts = set()
    for x in range(margin, GRID_W - margin):
        pts.add((x, margin))
        pts.add((x, GRID_H - 1 - margin))
    for y in range(margin, GRID_H - margin):
        pts.add((margin, y))
        pts.add((GRID_W - 1 - margin, y))
    return pts


def _arena_map() -> set:
    ring = _ring(3)
    cx, cy = GRID_W // 2, GRID_H // 2
    gaps = set()
    for d in (-1, 0, 1):
        gaps.add((cx + d, 3))
        gaps.add((cx + d, GRID_H - 1 - 3))
        gaps.add((3, cy + d))
        gaps.add((GRID_W - 1 - 3, cy + d))
    return ring - gaps


def _cross_map() -> set:
    pts = set()
    cx, cy = GRID_W // 2, GRID_H // 2
    for x in range(6, GRID_W - 6):
        if abs(x - cx) > 3:
            pts.add((x, cy - 6))
            pts.add((x, cy + 6))
    for y in range(4, GRID_H - 4):
        if abs(y - cy) > 3:
            pts.add((cx - 10, y))
            pts.add((cx + 10, y))
    return pts


def _pillars_map() -> set:
    pts = set()
    for x in (6, 16, 26):
        for y in (4, 11, 18):
            if (x, y) != (16, 11):
                pts.add((x, y))
    return pts


def _volcano_map() -> set:
    # A crater ring tucked in the upper-right, plus scattered lava rock.
    pts = set()
    ring_offsets = [(-3, 0), (-2, -2), (0, -3), (2, -2), (3, 0), (2, 2), (0, 3), (-2, 2)]
    cx, cy = 24, 5
    for dx, dy in ring_offsets:
        pts.add((cx + dx, cy + dy))
    for x, y in [(22, 9), (26, 9), (20, 14), (28, 14), (24, 17)]:
        pts.add((x, y))
    return pts


def _everest_map() -> set:
    # A jagged mountain ridge silhouette across the lower-middle of the board.
    pts = set()
    for x in range(4, 28):
        offset = abs(((x - 4) % 10) - 5)  # zigzags 0..5
        y = 18 - offset
        pts.add((x, y))
        if offset >= 4:
            pts.add((x, y - 1))
    return pts


def _desert_map() -> set:
    # Sparse, asymmetric dunes.
    pts = set()
    for cx, cy in [(6, 16), (26, 16), (6, 6), (26, 6), (16, 19), (16, 3)]:
        for dx in (-1, 0, 1):
            pts.add((cx + dx, cy))
    return pts


def _glacier_map() -> set:
    # Loose grid of 2x2 ice blocks, center kept clear.
    pts = set()
    for bx in (5, 13, 21, 27):
        for by in (3, 10, 17):
            if (bx, by) == (13, 10):
                continue
            for ddx in (0, 1):
                for ddy in (0, 1):
                    x, y = bx + ddx, by + ddy
                    if x < GRID_W and y < GRID_H:
                        pts.add((x, y))
    return pts


# Shared by local Coop and LAN alike - both are the "2 human players" case.
MAPS = {
    "Open": set(),
    "Pillars": _pillars_map(),
    "Cross": _cross_map(),
    "Arena": _arena_map(),
    "Volcano": _volcano_map(),
    "Everest": _everest_map(),
    "Desert": _desert_map(),
    "Glacier": _glacier_map(),
}
MAP_NAMES = list(MAPS.keys())

# Per-map visual theme: obstacle color + shape, a background tint, a glow
# accent, and an ambient particle effect. Maps not listed (Open/Pillars/
# Cross/Arena, and every single-player mode's procedural obstacles) fall
# back to DEFAULT_THEME - plain gray blocks, no tint, no ambience.
DEFAULT_OBSTACLE_COLOR = (70, 70, 80)
DEFAULT_THEME = {
    "obstacle_color": DEFAULT_OBSTACLE_COLOR,
    "glow_color": None,
    "bg_tint": None,
    "shape": "block",
    "ambient": None,
}

MAP_THEMES = {
    "Volcano": {
        "obstacle_color": (90, 35, 20), "glow_color": (255, 110, 30),
        "bg_tint": (28, 12, 10), "shape": "rock", "ambient": "embers",
    },
    "Everest": {
        "obstacle_color": (205, 215, 230), "glow_color": (255, 255, 255),
        "bg_tint": (10, 16, 26), "shape": "peak", "ambient": "snow",
    },
    "Desert": {
        "obstacle_color": (190, 150, 90), "glow_color": (255, 220, 150),
        "bg_tint": (26, 20, 10), "shape": "dune", "ambient": "sand",
    },
    "Glacier": {
        "obstacle_color": (150, 205, 235), "glow_color": (215, 240, 255),
        "bg_tint": (8, 20, 30), "shape": "crystal", "ambient": "sparkle",
    },
}

DIFFICULTIES = ["Easy", "Normal", "Hard"]
DIFFICULTY_SPEED_MULT = {"Easy": 0.85, "Normal": 1.0, "Hard": 1.25}

# Purchasable cosmetic trails (coin shop). color=None means no glow override
# (uses the skin's own color); "rainbow" cycles hue over time.
TRAIL_EFFECTS = {
    "None":   {"cost": 0,   "color": None},
    "Ember":  {"cost": 40,  "color": (255, 120, 40)},
    "Frost":  {"cost": 40,  "color": (140, 220, 255)},
    "Toxic":  {"cost": 60,  "color": (140, 255, 90)},
    "Royal":  {"cost": 80,  "color": (190, 120, 255)},
    "Rainbow": {"cost": 150, "color": "rainbow"},
}
TRAIL_NAMES = list(TRAIL_EFFECTS.keys())

SAVE_DIR_NAME = ".megasnake"

# Easter egg: keep pressing Down on the main menu past the last item. A
# streak needs (presses to reach the last item from where it started) +
# EASTER_EXTRA_PRESSES; any other key resets it. That triggers the first
# warning; Down on each warning escalates, and past the last one opens the
# (purely cosmetic) secret shop. Any other key on a warning bails out. Once
# the shop has been found, later streaks skip the warnings.
EASTER_EXTRA_PRESSES = 10

EASTER_WARNINGS = [
    {
        "title": "...",
        "lines": ["What are you doing?", "Get out. You're not supposed to be here."],
        "color": (235, 235, 245),
        "shake": 0,
    },
    {
        "title": "I SAID GO BACK",
        "lines": ["Seriously. Stop pressing down.", "This is your only other warning."],
        "color": (255, 170, 60),
        "shake": 3,
    },
    {
        "title": "LAST WARNING",
        "lines": ["This is it. Turn back now.", "You will not be warned again."],
        "color": (255, 70, 70),
        "shake": 6,
    },
]

SECRET_SHOP_ITEMS = [
    ("The Void", "???", "A skin made of pure nothing."),
    ("Developer's Coffee", "1,000,000 coins", "+0% to everything. Tastes bitter."),
    ("Fourth Wall", "NOT FOR SALE", "Already broken, see above."),
    ("Your Sanity", "Already spent", "Refunds not available."),
    ("Achievement: Curious", "Locked forever", "You'll never unlock this."),
    ("A Second Snake", "Priceless", "It's just staring at you."),
]

GAME_VERSION = "1.8.3"

GHOST_MAX_TICKS = 5000

CHANGELOG = [
    ("1.8.3", [
        "Fixed 'Check for Updates' failing on macOS with an SSL certificate error",
    ]),
    ("1.8.2", [
        "Fixed a few things you probably haven't found yet.",
        "(One new achievement. Good luck.)",
    ]),
    ("1.8.1", [
        "Fixed the auto-updater on Windows: the updated game now actually relaunches",
        "(it used to fail with 'Failed to load Python DLL' or hang in the background)",
    ]),
    ("1.8.0", [
        "Minor polish and bugfixes.",
        "(No, that's not the whole changelog. Figure it out.)",
    ]),
    ("1.7.0", [
        "Auto-updater: checks GitHub Releases on launch, offers to download",
        "and install new versions automatically (with your confirmation)",
        "Maps now apply to every mode, not just Coop/LAN (Daily stays seeded-only)",
        "Fixed food blending into a themed map's palette (every food item now",
        "has a visible outline, not just bomb/curse)",
    ]),
    ("1.6.0", [
        "Maps now work in local Coop too, not just LAN - pick one before you start",
        "4 new themed maps: Volcano, Everest, Desert, Glacier (each with tinted obstacles)",
    ]),
    ("1.5.0", [
        "LAN hosts now pick a ruleset (Classic/Walls/Maze) and a map before starting",
        "4 maps: Open, Pillars, Cross, Arena",
        "Revive power-up: spawns in Coop/LAN when your teammate is down, brings them back",
    ]),
    ("1.4.0", [
        "Ghost replay: race a translucent replay of your best run in each mode",
        "Daily quests: 3 new objectives every day with coin rewards",
        "How to Play screen with controls, food & power-up reference",
        "Color-blind mode (Okabe-Ito palette) in Settings",
        "Announcer callouts, red wall-proximity warning, run-history chart in Stats",
    ]),
    ("1.3.0", [
        "LAN multiplayer: host a match on your local network, no server needed",
        "The other player joins by typing your LAN IP shown on the Host screen",
        "Reuses Coop rules over the network - 2 snakes, shared board and score",
        "Graceful disconnect handling on both the host and client side",
    ]),
    ("1.2.0", [
        "Coin economy: earn coins per run, spend them in the new Shop on trail effects",
        "Daily play streaks with bonus coins for playing consecutive days",
        "Arcade-style 3-letter initials entry when you land a high score",
        "Achievement screen now shows live progress bars, not just checkmarks",
        "Real-time 'New Personal Best!' banner mid-run when you beat your own record",
    ]),
    ("1.1.0", [
        "Added modes: Timed, Hardcore, Co-op, Daily Challenge",
        "Battle mode now has 2 rival snakes",
        "Added portals, Curse food, Freeze & Teleport power-ups",
        "Settings screen: volume, difficulty, screen shake toggle",
        "Stats & Changelog screens, itemized post-game score breakdown",
        "Skins now unlock via achievements",
        "Visual polish: pulsing body, speed trail glow, zoom punch, sequential death",
    ]),
    ("1.0.0", [
        "Initial release: Classic/Walls/Maze/Battle, power-ups, combos, achievements",
    ]),
]
