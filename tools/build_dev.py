# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Build the DEV executable: the normal game plus the cheat console (devconsole.py, press ` or F10).

    python tools/build_dev.py            # -> dist/MegaSnakeDEV[.exe]

It flips build_info.DEV to True just for the PyInstaller run and puts the file back afterwards, so a dev build
can never be made by accident from a normal commit. The dev build keeps its save in ~/.megasnake-dev and never
auto-updates. For quick tests from source you don't need a build at all: `MEGASNAKE_DEV=1 python main.py`.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INFO = ROOT / "build_info.py"


def main() -> None:
    original = INFO.read_text()
    if "DEV = False" not in original:
        sys.exit("build_info.py doesn't contain 'DEV = False'; refusing to guess.")
    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--windowed", "--collect-data", "certifi",
        "--add-data", f"assets/fonts{sep}assets/fonts", "--add-data", f"assets/art{sep}assets/art",
        "--hidden-import", "devconsole", "--name", "MegaSnakeDEV", "main.py",
    ]
    INFO.write_text(original.replace("DEV = False", "DEV = True", 1))
    try:
        subprocess.run(cmd, cwd=ROOT, check=True)
    finally:
        INFO.write_text(original)  # never leave the flag flipped in the working tree
    print("built dist/MegaSnakeDEV")


if __name__ == "__main__":
    main()
