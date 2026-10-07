# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""In-game auto-updater.

Checks GitHub Releases for versions newer than this build, downloads the
right asset for the current OS, and - for a packaged (frozen) build only -
replaces the running executable and relaunches it. All network and disk work
runs on a background thread so the pygame UI never blocks; the UI polls the
checker/downloader objects' plain attributes once per frame.

Self-replacing a running executable is inherently platform-specific (you
can't overwrite a file Windows has memory-mapped as the running image, for
instance), so each OS gets its own small helper script that waits for this
process to exit, swaps the file/bundle into place, and relaunches - spawned
detached, right before this process calls os._exit(0).
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tls import ssl_context

REPO = "youssefahmed2017/mega-snake"
API_RELEASES = f"https://api.github.com/repos/{REPO}/releases"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
USER_AGENT = "MegaSnake-Updater"

ASSET_BY_PLATFORM = {
    "Windows": "MegaSnake-Windows.exe",
    "Darwin": "MegaSnake-macOS.zip",
    "Linux": "MegaSnake-Linux",
}


def current_platform() -> str:
    return platform.system()  # "Windows" | "Darwin" | "Linux"


def parse_version(tag: str) -> Tuple[int, int, int]:
    s = tag.lstrip("vV")
    parts = s.split("-")[0].split(".")
    nums = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])  # type: ignore[return-value]


class Release:
    def __init__(self, tag: str, assets: Dict[str, dict]):
        self.tag = tag
        self.version = parse_version(tag)
        self.assets = assets  # asset filename -> {"url", "size"}

    def asset_for_this_platform(self) -> Optional[dict]:
        name = ASSET_BY_PLATFORM.get(current_platform())
        return self.assets.get(name) if name else None


def fetch_releases(timeout: float = 4.0) -> List[Release]:
    req = urllib.request.Request(
        API_RELEASES,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    releases = []
    for item in data:
        if item.get("draft") or item.get("prerelease"):
            continue
        tag = item.get("tag_name", "")
        if not tag:
            continue
        assets = {
            a["name"]: {"url": a["browser_download_url"], "size": a["size"]}
            for a in item.get("assets", [])
        }
        if assets:
            releases.append(Release(tag, assets))
    return releases


def find_updates(current_version: Tuple[int, int, int]) -> List[Release]:
    """Releases strictly newer than current_version, oldest first."""
    releases = fetch_releases()
    newer = [r for r in releases if r.version > current_version]
    newer.sort(key=lambda r: r.version)
    return newer


class UpdateChecker:
    """Background-thread GitHub Releases check. Poll .done each frame."""

    def __init__(self, current_version_str: str):
        self.current_version = parse_version(current_version_str)
        self.done = False
        self.error: Optional[str] = None
        self.updates: List[Release] = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self.updates = find_updates(self.current_version)
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
            self.error = str(e)
        finally:
            self.done = True


class Downloader:
    """Background-thread download of one release asset, with progress."""

    def __init__(self, url: str, dest_path: Path):
        self.url = url
        self.dest_path = dest_path
        self.total = 0
        self.received = 0
        self.done = False
        self.error: Optional[str] = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def progress(self) -> float:
        return (self.received / self.total) if self.total else 0.0

    def _run(self) -> None:
        tmp = self.dest_path.with_name(self.dest_path.name + ".part")
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20, context=ssl_context()) as resp:
                self.total = int(resp.headers.get("Content-Length", 0))
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        self.received += len(chunk)
            tmp.replace(self.dest_path)
        except (urllib.error.URLError, OSError) as e:
            self.error = str(e)
            tmp.unlink(missing_ok=True)
        finally:
            self.done = True


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _fresh_child_env() -> Dict[str, str]:
    """Environment for relaunching a *different* PyInstaller build.

    A frozen app's bootloader sets _PYI_* variables (notably
    _PYI_APPLICATION_HOME_DIR, pointing at its own _MEIxxxx temp dir). A
    child PyInstaller exe that inherits them assumes it's a sub-process of
    that same app and loads python3xx.dll from the parent's temp dir - which
    is deleted the moment the parent exits, giving "Failed to load Python
    DLL". PYINSTALLER_RESET_ENVIRONMENT=1 tells the child bootloader to start
    fresh instead."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI_")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _find_app_bundle(executable_path: Path) -> Optional[Path]:
    for p in [executable_path, *executable_path.parents]:
        if p.suffix == ".app":
            return p
    return None


MAC_MOVE_TO_APPLICATIONS = (
    "macOS is running MegaSnake from a temporary read-only copy. Drag MegaSnake.app "
    "into your Applications folder, open it from there, then update again."
)


def is_translocated(app_path: Path) -> bool:
    """Gatekeeper "App Translocation": a quarantined app opened straight from
    its download location actually runs from a randomized read-only mount, so
    the bundle at sys.executable can't be replaced - an in-place update there
    silently fails and relaunches the same old version."""
    return "AppTranslocation" in Path(app_path).parts


def _untranslocated_path(app_path: Path) -> Optional[Path]:
    """Where the translocated app really lives, via the Security framework's
    SecTranslocateCreateOriginalPathForURL. None if that can't be resolved."""
    try:
        import ctypes
        import ctypes.util

        cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        sec = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Security"))
        cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
        cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
        cf.CFURLGetFileSystemRepresentation.restype = ctypes.c_bool
        cf.CFURLGetFileSystemRepresentation.argtypes = [
            ctypes.c_void_p, ctypes.c_bool, ctypes.c_char_p, ctypes.c_long]
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        sec.SecTranslocateCreateOriginalPathForURL.restype = ctypes.c_void_p
        sec.SecTranslocateCreateOriginalPathForURL.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        raw = str(app_path).encode("utf-8")
        url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), True)
        if not url:
            return None
        original = sec.SecTranslocateCreateOriginalPathForURL(url, None)
        cf.CFRelease(url)
        if not original:
            return None
        buf = ctypes.create_string_buffer(4096)
        ok = cf.CFURLGetFileSystemRepresentation(original, True, buf, len(buf))
        cf.CFRelease(original)
        if not ok:
            return None
        path = Path(buf.value.decode("utf-8"))
        return path if path.suffix == ".app" and not is_translocated(path) else None
    except Exception:
        return None


def preflight_error() -> Optional[str]:
    """A reason an update can't possibly be applied, checked before downloading."""
    if is_frozen() and current_platform() == "Darwin":
        app_path = _find_app_bundle(Path(sys.executable).resolve())
        if app_path and is_translocated(app_path) and _untranslocated_path(app_path) is None:
            return MAC_MOVE_TO_APPLICATIONS
    return None


def update_failed_message(target_tag: str) -> str:
    if current_platform() == "Darwin":
        return (f"The update to {target_tag} didn't install. Drag MegaSnake.app into your "
                "Applications folder, open it from there, then update again.")
    return (f"The update to {target_tag} didn't install. Download it manually instead "
            "(details in ~/.megasnake/update.log).")


def _update_log_path() -> Path:
    log_dir = Path.home() / ".megasnake"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "update.log"


def apply_update_and_relaunch(downloaded_path: Path) -> Optional[str]:
    """Replaces the running build with the downloaded one and relaunches it.

    On success this never returns - the process exits via os._exit() so the
    helper script can safely swap the now-closed file/bundle into place.
    On failure (e.g. not a packaged build) it returns an error string and
    the caller is expected to show it and keep running normally."""
    if not is_frozen():
        return "This is a dev build, not a packaged one - use 'git pull' instead."

    system = current_platform()
    pid = os.getpid()

    if system == "Windows":
        exe_path = Path(sys.executable).resolve()
        backup = exe_path.with_suffix(".exe.bak")
        bat_path = Path(tempfile.gettempdir()) / "megasnake_update.bat"
        # No "goto" inside a parenthesized if-block: cmd.exe can get stuck re-reading it.
        bat_path.write_text(f'''@echo off
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if errorlevel 1 goto afterwait
timeout /t 1 /nobreak >nul
goto wait
:afterwait
if exist "{backup}" del /f /q "{backup}"
if exist "{exe_path}" move /y "{exe_path}" "{backup}" >nul
move /y "{downloaded_path}" "{exe_path}" >nul
start "" "{exe_path}"
del "%~f0"
''', encoding="utf-8")
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            # Not DETACHED_PROCESS: with no console at all, the tasklist|find wait never exits.
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
            env=_fresh_child_env(),
        )
        os._exit(0)

    elif system == "Darwin":
        exe_path = Path(sys.executable).resolve()
        app_path = _find_app_bundle(exe_path)
        if app_path is None:
            return "Could not locate the running .app bundle to replace."
        if is_translocated(app_path):
            app_path = _untranslocated_path(app_path)
            if app_path is None:
                return MAC_MOVE_TO_APPLICATIONS
        extract_dir = Path(tempfile.mkdtemp(prefix="megasnake_update_"))
        script_path = Path(tempfile.gettempdir()) / "megasnake_update.sh"
        # Only relaunch the new bundle if every step of the swap worked; on any
        # failure, put the old one back. The new bundle is downloaded by us,
        # not a browser, so it has no quarantine flag and won't be translocated.
        script_path.write_text(f'''#!/bin/bash
exec >>"{_update_log_path()}" 2>&1
echo "=== $(date) updating {app_path}"
while kill -0 {pid} 2>/dev/null; do sleep 0.3; done
if ditto -x -k "{downloaded_path}" "{extract_dir}" \\
   && [ -d "{extract_dir}/MegaSnake.app" ] \\
   && rm -rf "{app_path}.bak" \\
   && mv "{app_path}" "{app_path}.bak" \\
   && mv "{extract_dir}/MegaSnake.app" "{app_path}"; then
  xattr -dr com.apple.quarantine "{app_path}" 2>/dev/null
  echo "swap ok"
else
  echo "swap FAILED"
  [ -d "{app_path}" ] || mv "{app_path}.bak" "{app_path}"
fi
open "{app_path}"
rm -rf "{extract_dir}"
rm -f "$0"
''', encoding="utf-8")
        script_path.chmod(0o755)
        subprocess.Popen(["/bin/bash", str(script_path)], start_new_session=True, env=_fresh_child_env())
        os._exit(0)

    else:  # Linux
        exe_path = Path(sys.executable).resolve()
        script_path = Path(tempfile.gettempdir()) / "megasnake_update.sh"
        script_path.write_text(f'''#!/bin/bash
exec >>"{_update_log_path()}" 2>&1
echo "=== $(date) updating {exe_path}"
while kill -0 {pid} 2>/dev/null; do sleep 0.3; done
if cp "{exe_path}" "{exe_path}.bak" && mv "{downloaded_path}" "{exe_path}"; then
  echo "swap ok"
else
  echo "swap FAILED"
fi
chmod +x "{exe_path}"
"{exe_path}" &
rm -f "$0"
''', encoding="utf-8")
        script_path.chmod(0o755)
        subprocess.Popen(["/bin/bash", str(script_path)], start_new_session=True, env=_fresh_child_env())
        os._exit(0)

    return None  # unreachable except on an unknown platform() value
