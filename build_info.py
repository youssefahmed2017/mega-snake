# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Which storefront this build ships through. The itch.io workflow overwrites this file at build time.

"github": the in-game auto-updater is on (it reads GitHub Releases).
anything else (e.g. "itch"): the updater is off, because the store updates the game itself.
"""
STORE = "github"
