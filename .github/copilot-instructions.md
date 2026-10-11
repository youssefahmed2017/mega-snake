# Repository instructions

MEGA SNAKE is a pygame-ce desktop game packaged as standalone Windows, macOS, and Linux builds. The game is not a pip package. `README.md` covers player-facing features; `CLAUDE.md` has deeper subsystem notes.

## Build, run, and verification

```bash
pip install -r requirements.txt
python main.py
```

There is no configured unit-test suite, single-test command, linter, or formatter. For multiplayer interpolation or snapshot changes, run the headless simulation:

```bash
python tools/mp_sim.py
python tools/mp_sim.py --seconds 40
```

It measures guest smoothness over a simulated network; it does not replace testing with a real loopback `network.Host`/`Client`.

Build the Linux executable locally (install PyInstaller first with `pip install pyinstaller`):

```bash
pyinstaller --onefile --add-data "assets/fonts:assets/fonts" --add-data "assets/art:assets/art" --collect-data certifi --name MegaSnake main.py
```

For Windows, use `;` rather than `:` in PyInstaller `--add-data` destinations and `assets/icon.ico`; macOS uses `assets/icon.icns` and the platform-specific packaging shown in `.github/workflows/build.yml`. The workflow is authoritative for release builds.

The online relay is a Cloudflare Worker in `server/`:

```bash
cd server
npm install
npm run dev
```

`npm run deploy` deploys to Cloudflare; use it only when a relay deployment is intended.

## Architecture

- `main.py` owns the `Game` state machine, update loop, rendering orchestration, input, and multiplayer game behavior. The smaller root Python modules are support systems; `network.py` handles transport, not game rules.
- `gfx.py` provides a 1028×578 logical canvas and scaling to the selected display resolution. UI/game drawing uses `gfx.draw`, `gfx.surface`, `gfx.Font`, and `gfx.mouse_pos` instead of raw pygame drawing, surfaces, fonts, or mouse coordinates. `main.screen` is the logical canvas; `_frame` presents it letterboxed.
- Menu navigation remains keyboard-driven. Mouse hotspots and gamepad controls select a row and replay the same key action, keeping all input paths aligned. `settings_defs.py` is the source of truth for declared settings; access values through `Game.setting_get/setting_set`.
- Multiplayer is host-authoritative: the host simulates the run and guests render host snapshots. LAN and online transports share the `poll`/`send`/`close` interface. `server/src/index.js` relays messages only; it does not simulate the game. Read its message-contract header before changing room, routing, or reconnect behavior.
- Chaos events in `events.py` are pure logic and use the supplied RNG; Daily mode relies on seeded deterministic schedules. The relay's `MIN_VERSION` must match `MIN_MULTIPLAYER_VERSION` in `constants.py`; raise both only for incompatible wire-protocol changes.
- `assets/source/` contains source artwork; runtime artwork and fonts are bundled from `assets/art/` and `assets/fonts/`. Keep the PyInstaller data-file settings in sync with any asset changes. Generated assets can be rebuilt with `python tools/prepare_art.py` (requires development dependencies including NumPy and SciPy).

## Repository-specific conventions

- Keep game layout in logical canvas coordinates. For new menu/settings rows, use the existing hotspot helpers and replay-key flow rather than adding independent mouse navigation. Gameplay remains keyboard/gamepad controlled; mouse input is ignored while playing.
- Preserve host authority for multiplayer state. Snapshot additions should remain compatible with older builds in the supported version range; keep player slot ordering aligned between `constants.py` and the relay's `GUEST_SLOTS`.
- Add settings through `settings_defs.SETTING_DEFS`; use `Game.setting_get/setting_set` so menu controls and persistence share the same definition. Route footer hints through `Game._hint()` for gamepad labels.
- New achievement predicates must tolerate missing stats with `s.get(...)`; add new progress-bar stats to `update_stat_bests` as well.
- Every new `.py` or `.js` source file needs the repository's copyright and `SPDX-License-Identifier: GPL-3.0-only` header. Preserve the separate SIL Open Font License terms and license files for bundled fonts.
