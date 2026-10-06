"""All tunable constants live here."""

CELL_SIZE = 24
GRID_W, GRID_H = 32, 22
SIDEBAR_W = 260
SCREEN_W = GRID_W * CELL_SIZE + SIDEBAR_W
# 16:9, so a 1920x1080 display is filled exactly (no letterbox bars). The 528px board sits
# vertically centred in it; BOARD_Y is how far down.
SCREEN_H = 578
BOARD_Y = (SCREEN_H - GRID_H * CELL_SIZE) // 2
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
P3_COLOR = [(120, 200, 255), (70, 140, 210)]
P4_COLOR = [(230, 120, 255), (170, 70, 210)]
PLAYER_COLORS = [None, P2_COLOR, P3_COLOR, P4_COLOR]  # index 0 (host) uses its chosen skin instead
PLAYER_LABELS = ["P1", "P2", "P3", "P4"]
MAX_PLAYERS = 4

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

FOOD_WEIGHTS = {
    FOOD_NORMAL: 56,
    FOOD_GOLDEN: 10,
    FOOD_SPEED: 10,
    FOOD_SHRINK: 8,
}

FOOD_COLORS = {
    FOOD_NORMAL: (255, 90, 90),
    FOOD_GOLDEN: GOLD,
    FOOD_SPEED: (90, 200, 255),
    FOOD_SHRINK: PURPLE,
}

# "Downerups": hazard pickups that spawn and get collected like power-ups
# (rare, timed, their own on-field cap) instead of being mixed into the
# common food pool - so they read as a deliberate risk you can choose to
# dodge, not as 1-in-6 nutrition that occasionally kills you.
DOWNERUP_BOMB = "bomb"
DOWNERUP_CURSE = "curse"

DOWNERUP_TYPES = [DOWNERUP_BOMB, DOWNERUP_CURSE]

DOWNERUP_COLORS = {
    DOWNERUP_BOMB: (30, 30, 30),
    DOWNERUP_CURSE: CURSE_COLOR,
}

# Downerups spawn independently of (and rarer than) power-ups, and only one
# is ever on the field at a time - see maybe_spawn_downerup() in food.py.
DOWNERUP_SPAWN_CHANCE = 0.006
DOWNERUP_TTL = 10.0

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
}

COLORBLIND_DOWNERUP_COLORS = {
    DOWNERUP_BOMB: (30, 30, 30),
    DOWNERUP_CURSE: (0, 114, 178),
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
    ("Developer's Coffee", "1M coins", "+0% to everything. Tastes bitter."),
    ("Fourth Wall", "NOT FOR SALE", "Already broken, see above."),
    ("Your Sanity", "Already spent", "Refunds not available."),
    ("Achievement: Curious", "Locked forever", "You'll never unlock this."),
    ("A Second Snake", "Priceless", "It's just staring at you."),
]

GAME_VERSION = "3.1.0"

# Oldest version that may play multiplayer with this one. Different versions inside the
# range play together; anything older is turned away. Raise it only when the network
# protocol changes in a way old builds can't follow, and mirror it in server/src/index.js.
MIN_MULTIPLAYER_VERSION = "1.9.2"

# Online multiplayer relay (server/ in this repo, a Cloudflare Worker),
# deployed 2026-10-01 to a free *.workers.dev subdomain. The MEGASNAKE_SERVER
# env var overrides it, e.g. ws://127.0.0.1:8787 for a local `wrangler dev`.
ONLINE_SERVER_URL = "wss://megasnake-online.megasnake-online.workers.dev"

GHOST_MAX_TICKS = 5000

CHANGELOG = [
    ("2.0.0", [
        "A pass on how the game FEELS to play, not just what it can do:",
        "- Eating pops a floating +10/-5 at the tile, and chained eats climb",
        "  an ascending scale instead of repeating the same blip",
        "- Growth: the new tail segment scales in instead of just appearing",
        "- The snake blinks, flicks its tongue, and squashes/stretches its",
        "  head on sharp turns - idle personality, not just a moving rect",
        "- Near misses (survive next to a wall/obstacle/your own tail) now",
        "  get their own whoosh + screen-edge flash + a tiny hitstop beat,",
        "  instead of skill only ever being rewarded by not dying",
        "- Death now eases into a slow-motion beat on the fatal frame instead",
        "  of just freezing, before cutting to Game Over",
    ]),
    ("1.9.4", [
        "Removed the outline ring/square drawn behind every food, power-up,",
        "and downerup icon - they looked like a dot in a frame; the icons",
        "stand on their own now",
    ]),
    ("1.9.3", [
        "Redesigned food/power-up/downerup art - they're actual little icons",
        "now (apple, star, bolt, potion, bomb, skull, ghost, magnet, shield,",
        "clock, snowflake, heart...) instead of plain circles and squares",
    ]),
    ("1.9.2", [
        "Fixed Curse sometimes killing you instantly - it reversed controls",
        "correctly now instead of also reversing 'no key pressed'",
        "Bomb and Curse are now their own 'downerup' pickups, not food - a",
        "Magnet or Teleport power-up can no longer drag/warp you into one",
        "Reduced multiplayer bandwidth further: match info (mode/map/skin) is",
        "sent once per session instead of on every snapshot",
    ]),
    ("1.9.1", [
        "LAN and Online multiplayer now support up to four players",
        "Reduced multiplayer bandwidth with capped state snapshots and smoother remote rendering",
    ]),
    ("1.9.0", [
        "Online Multiplayer is live! Host or Join Online Game from Multiplayer",
        "- no port forwarding, works over the internet, just a 5-letter room code",
    ]),
    ("1.8.14", [
        "Chat is plain ASCII only for now (emoji/Unicode temporarily dropped)",
        "to rule out font rendering as the cause of chat being broken on Mac",
    ]),
    ("1.8.13", [
        "Fixed chat being completely invisible on macOS (not even the cursor)",
        "- the emoji font it picked there had no glyphs for plain text at all",
    ]),
    ("1.8.12", [
        "Fixed a LAN/Online match disconnecting right after a new high score",
        "(the host got stuck on a solo-only screen the other player couldn't",
        "see, with no traffic flowing, until the connection actually died)",
    ]),
    ("1.8.11", [
        "LAN Multiplayer now checks both players are on the same version",
        "when connecting, and says so clearly instead of silently breaking",
        "(T-pause-chat and other newer features need BOTH sides updated)",
    ]),
    ("1.8.10", [
        "Fixed false 'disconnected' errors during a long pause/chat",
        "(the connection stays alive now with a small idle heartbeat)",
        "Fixed a crash from a rare malformed character some emoji pickers send",
    ]),
    ("1.8.9", [
        "T now pauses AND opens chat in one press during LAN/Online play",
        "(works for both host and the joining player)",
        "Added hjkl as vim-style movement controls alongside arrows/WASD",
    ]),
    ("1.8.8", [
        "The game's font now auto-detects the best monospace font installed",
        "(fixes it silently falling back to a generic font on macOS/Linux,",
        "since the old hardcoded font was Windows-only)",
        "Fixed chat's spam cooldown sometimes blocking your very first message",
    ]),
    ("1.8.7", [
        "Added in-match chat for LAN and Online multiplayer",
        "Open it from the Pause screen with T - the match stays paused while",
        "either of you is typing, so nobody's snake moves mid-sentence",
        "Supports full Unicode text and most emoji",
    ]),
    ("1.8.6", [
        "Fixed an endless update loop on macOS when the app was opened from Downloads",
        "If an update ever fails to install, the game now says so instead of retrying forever",
    ]),
    ("1.8.5", [
        "Shop trails are real now: a glowing streak follows your snake all run",
        "(before, they only tinted a faint head glow while you were sped up)",
        "Rainbow trail cycles colors along its length",
    ]),
    ("1.8.4", [
        "Screen shake actually shakes now (it was too weak to notice before)",
        "Dying pauses on the board for a moment so you see the crash before Game Over",
        "LAN Multiplayer is now just 'Multiplayer' (online play is coming soon)",
    ]),
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
