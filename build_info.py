# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Which storefront this build ships through. The itch.io workflow overwrites this file at build time.

"github": the in-game auto-updater is on (it reads GitHub Releases).
anything else (e.g. "itch"): the updater is off, because the store updates the game itself.
"""
import os
import sys

STORE = "github"

# Dev builds (tools/build_dev.py) flip this to True: it turns on the cheat console (devconsole.py, ` or F10),
# turns the auto-updater off and keeps its save data in its own folder, away from the real game's. From
# source (not a packaged build) it can also be switched on with MEGASNAKE_DEV=1.
DEV = False
if not getattr(sys, "frozen", False) and os.environ.get("MEGASNAKE_DEV") == "1":
    DEV = True
