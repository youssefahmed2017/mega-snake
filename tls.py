# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Shared SSL context for every HTTPS / WSS connection the game makes.

A PyInstaller build carries its own OpenSSL, which on macOS (and some Linux
distros) can't find the system's trusted root certificates - every HTTPS
request then fails with CERTIFICATE_VERIFY_FAILED. Bundling certifi's CA
list and pointing OpenSSL at it explicitly makes verification work the same
everywhere. Falls back to the platform default if certifi is missing (e.g. a
bare dev checkout), which is fine on Windows and most dev machines.
"""
from __future__ import annotations

import ssl
from typing import Optional

_context: Optional[ssl.SSLContext] = None


def ssl_context() -> ssl.SSLContext:
    global _context
    if _context is None:
        try:
            import certifi
            _context = ssl.create_default_context(cafile=certifi.where())
        except (ImportError, OSError):
            _context = ssl.create_default_context()
    return _context
