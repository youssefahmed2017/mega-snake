# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MEGA SNAKE: a single-file-per-system pygame-ce snake game with LAN and online (Cloudflare Worker relay)
multiplayer for up to 4 players, an in-game auto-updater, achievements/quests/persistence, and a
PyInstaller-based cross-platform release pipeline. The game ships as standalone executables (Windows/macOS/
Linux) built and released via GitHub Actions, not as a pip package.

## Commands

```bash
pip install -r requirements.txt   # pygame-ce, numpy, certifi, websockets
python main.py                    # run the game
```

No test suite, linter, or formatter is currently configured in this repo — there are no `test_*.py` files,
`pytest.ini`, or lint config. Don't assume one exists; if asked to add tests, check whether the user wants
`pytest` added from scratch.

Relay server (Cloudflare Worker + Durable Objects, in `server/`):
```bash
cd server
npm install
npm run dev      # wrangler dev --port 8787, for local LAN-style testing of the online relay
npm run deploy    # wrangler deploy
```

Building a release binary locally (matches `.github/workflows/build.yml`):
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --collect-data certifi --add-data "assets/fonts:assets/fonts" --add-data "assets/art:assets/art" --name MegaSnake main.py   # use ';' not ':' on Windows
```

## Architecture

### Core game loop — `main.py`
Everything client-side funnels through the single `Game` class in `main.py` (~4200 lines): state machine
(menu/playing/paused/game-over/shop/settings), rendering, input, and all three multiplayer transports. Other
modules (`snake.py`, `food.py`, `enemy.py`, `particles.py`, `achievements.py`, `quests.py`, `persistence.py`,
`audio.py`, `celebrate.py`, `constants.py`, `tls.py`, `updater.py`) are plain support modules imported by
`main.py` — there's no separate engine/view split.

`GAME_VERSION` in `constants.py` is the single source of truth for compatibility checks (LAN handshake,
online relay `?v=` query param, and the auto-updater's release comparison). Bump it whenever the wire protocol
with `network.py` or `server/src/index.js` changes, and keep all three in sync — a version mismatch is a hard
disconnect, by design (see `network.py`'s `hello`/version check and the relay's `_error` on mismatch).

### Rendering and resolution — `gfx.py`
All layout code is in *logical* units (the 1028x528 canvas); never use raw `pygame.draw`, `pygame.Surface(...)`,
`pygame.font.Font` or `pygame.mouse.get_pos()` in game/UI code. Use `gfx.draw.*`, `gfx.surface()`, `gfx.Font`
and `gfx.mouse_pos()` (and `event.pos` -> `gfx.to_logical`), which scale to the real pixel resolution picked in
Settings > Display (144p..4K, `RESOLUTIONS` in `main.py`; `apply_display()` rebuilds window, canvas and fonts).
`main.screen` is the logical canvas; `_frame` blits it centered onto `main.display` (letterboxed). Rendered
text is cached per (text, color) and shared — `.copy()` before `set_alpha`. Fonts live in `assets/fonts`
(Lilita One headings, Varela Round body, both OFL) and must be bundled with `--add-data` in builds.
The canvas is 1028x578 (16:9) so a 1920x1080 display is filled exactly; the 528px board is drawn at `BOARD_Y`.

### Art — `art.py`, `tools/prepare_art.py`, `assets/`
Raw ChatGPT images live in `assets/source/` (not bundled). `python tools/prepare_art.py` (needs numpy + scipy,
dev-only) keys out the magenta backgrounds, splits the sheets, cleans up the wall tile and sidebar, and writes
game-ready PNGs to `assets/art/` (bundled; add `--add-data "assets/art:assets/art"` like the fonts). Prompts and
art direction: `assets/ART_PROMPTS.md`. At runtime `art.get(name, w=/h=/fit=, rot=, flip=, tint=, alpha=)` returns
a cached HSurface, or None if the file is missing; every call site (`_sprite_icon`, `_draw_snake_sprites`,
`_draw_obstacle`, `_draw_backdrop`, sidebar) falls back to the old vector drawing then, and colour-blind mode
deliberately uses the recoloured vector icons. The snake sprites are green and are recoloured per skin by hue
shift (`art.recolor`). The snake is drawn as head / straight / corner / tail beads: connectivity comes from the
grid cells, position from the interpolated render position. Themed map obstacles (`shape != "block"`) stay vector.

### Mouse layer and settings — `ui.py`, `settings_defs.py`
Menus are still keyboard state machines (`handle_*_key` + an index attribute per screen); the mouse sits on
top of them rather than replacing them. Every `draw_*` registers `Hot` regions (`Game._hot`, `_list_row`,
`_button`, `_arrow_hots`) while it draws; `run()`/`_frame()` clears `self.hotspots` right before drawing, and
`_handle_mouse` routes hover/click/wheel/drag to the topmost one. A click points the screen's index at the
row and replays the same key via `_press(K_RETURN/K_LEFT/...)`, so keyboard and mouse can't drift apart —
when adding a screen, draw its rows through those helpers instead of writing a new click handler. Right-click
is Esc everywhere except Playing/Paused, where it pauses/resumes (Esc there would abandon the run).
The window uses `pygame.SCALED | RESIZABLE`, so mouse coords are already in logical 1028x528 space.

User settings are declared once in `settings_defs.SETTING_DEFS` (the Settings screen, tabs, and
`persistence` defaults are generated from it). Read/write them via `Game.setting_get/setting_set`: five
legacy ones (volume, muted, difficulty, screen_shake, colorblind) live as attributes elsewhere in the game,
the rest in `self.settings`. The snake is deliberately keyboard-only: `_handle_mouse` ignores everything while
`STATE_PLAYING`, and the mouse is for menus/settings only. Don't add mouse steering.

Achievements: stat-based ones are checked every frame against `Game._achievement_stats()` (run stats plus
mode/lifetime totals) and again in `_finalize_game_over`; event-based ones (`lambda s: False`) are granted
with `Game._unlock(id)`. Lambdas for new achievements should use `s.get(...)` since not every key exists in
every check. Progress bars read `stat_bests`, so a new `stat_key` must also reach `update_stat_bests`.

### Multiplayer — authoritative host, dumb clients
In both LAN and Online modes, **the host's `Game` instance is the only authoritative simulation**; every
other connected player is a pure renderer that sends inputs upstream and applies snapshots sent back down.
This is why `main.py` has `_build_snapshot` / `apply_snapshot` methods and why guest-side code paths are
thin: a guest's job is "send my input, draw whatever the host just told me." Keep new multiplayer state host-
authoritative rather than letting guests simulate independently.

- `network.py` — transport layer only, no game logic. Four implementations: `Host`/`Client` (raw TCP sockets,
  LAN), and `OnlineHost`/`OnlineClient` (built on `OnlineLink`, a websocket client) for the Cloudflare relay.
  Both expose the same `poll()`/`send()`/`close()` shape to `main.py` so it doesn't need to care which
  transport is active. `OnlineLink` also handles reconnect-with-token on drop.
- `server/src/index.js` — the Cloudflare Worker + one Durable Object (`Room`) per room code. **It never runs
  game logic** — it's a pure relay: pairs a host with up to 3 guest slots (`p2`/`p3`/`p4`) by a 5-character
  room code, broadcasts each message to everyone else in the room tagged with the sender's slot, and holds a
  dropped player's seat for `GRACE_MS` (20s) before giving it up for good. Control messages are prefixed `_`
  (`_room`, `_joined`, `_roster`, `_peer_lost`, `_peer_back`, `_peer_gone`, `_error`); game messages (moves,
  chat, snapshots) never start with `_`. Read the file header comment before touching routing/reconnect logic
  — it documents the full message contract.
- Max player count is `MAX_PLAYERS` in `constants.py` (4); guest slot labels/colors are in
  `PLAYER_LABELS`/`PLAYER_COLORS`, keyed in the same order as the relay's `GUEST_SLOTS`.

### Auto-updater — `updater.py`
Checks GitHub Releases (`REPO = "youssefahmed2017/mega-snake"`) for versions newer than `GAME_VERSION`,
downloads the asset for the current OS, and — only for a frozen/packaged build — replaces the running
executable via a detached, platform-specific helper script spawned just before `os._exit(0)` (you can't
overwrite a memory-mapped running Windows exe from inside itself). All network/disk work runs on a background
thread; `main.py` polls the checker/downloader's plain attributes once per frame rather than blocking.

### Release pipeline — `.github/workflows/build.yml`
Every push to `main` and every `v*` tag builds Windows/macOS/Linux binaries via PyInstaller. Only a `v*` tag
additionally runs the `release` job, which publishes a GitHub Release with the three binaries as stable,
non-expiring download URLs — this is deliberate: the updater needs permanent URLs, and workflow-run artifacts
expire and require auth, so they can't serve that role. When cutting a release, tag `vX.Y.Z` after bumping
`GAME_VERSION` in `constants.py`.

## Related: `snake-site/`

A separate, ungitted static site (Vercel-deployed, `index.html` + `.vercel/`) one directory up from this repo
— the project's landing page. Not part of this repository.
cl