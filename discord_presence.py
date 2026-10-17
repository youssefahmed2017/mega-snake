# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Discord Rich Presence - the "Playing MEGA SNAKE" card on the player's Discord profile.

Talks to the local Discord client directly over its IPC socket (a Unix socket on
Linux/macOS, a named pipe on Windows), so there's no extra pip dependency. Every
connect / send / read happens on one background daemon thread: the game just calls
`set(...)` once a frame with what it's doing and never blocks. If Discord isn't
running (or isn't installed) the thread quietly retries every RETRY seconds and the
game never notices.

Discord rate-limits SET_ACTIVITY (about 5 per 20s), so only a *changed* activity is
sent, and never more often than MIN_INTERVAL. The last one wins: a score that ticks
up ten times in four seconds costs one update. When the process exits, Discord
clears the card on its own as soon as the pipe closes.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import time
import uuid
from typing import Optional

OP_HANDSHAKE, OP_FRAME, OP_CLOSE = 0, 1, 2
RETRY = 15.0          # seconds between connection attempts while Discord isn't reachable
MIN_INTERVAL = 4.0    # seconds between activity updates (Discord's limit is ~5 per 20s)


def _ipc_paths():
    if sys.platform == "win32":
        for i in range(10):
            yield rf"\\?\pipe\discord-ipc-{i}"
        return
    bases = [os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")] + ["/tmp"]
    # Plain install, then the Flatpak and Snap sandboxes, which put the socket in a subfolder.
    subdirs = ["", "app/com.discordapp.Discord", ".flatpak/com.discordapp.Discord/xdg-run", "snap.discord"]
    for base in dict.fromkeys(b for b in bases if b):
        for sub in subdirs:
            for i in range(10):
                yield os.path.join(base, sub, f"discord-ipc-{i}")


class _Pipe:
    """One open connection to the Discord client, framed as <op:u32><len:u32><json>."""

    def __init__(self) -> None:
        self._sock: Optional[socket.socket] = None
        self._file = None
        for path in _ipc_paths():
            try:
                if sys.platform == "win32":
                    self._file = open(path, "r+b", buffering=0)
                else:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(5.0)
                    try:
                        s.connect(path)
                    except OSError:
                        s.close()
                        raise
                    self._sock = s
                return
            except OSError:
                continue
        raise OSError("Discord isn't running")

    def send(self, op: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self._write(struct.pack("<II", op, len(data)) + data)

    def recv(self) -> dict:
        op, length = struct.unpack("<II", self._read(8))
        reply = json.loads(self._read(length).decode("utf-8"))
        if op == OP_CLOSE:
            raise OSError(f"Discord closed the connection: {reply.get('message', reply)}")
        return reply

    def _write(self, data: bytes) -> None:
        if self._sock:
            self._sock.sendall(data)
        else:
            self._file.write(data)

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf)) if self._sock else self._file.read(n - len(buf))
            if not chunk:
                raise OSError("Discord closed the connection")
            buf += chunk
        return buf

    def close(self) -> None:
        for handle in (self._sock, self._file):
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass


class DiscordPresence:
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        self.enabled = True
        self._wanted: Optional[dict] = None   # the activity the game currently asks for
        self._sent: Optional[dict] = None     # the activity Discord last accepted
        self._lock = threading.Lock()
        self._wake = threading.Event()
        threading.Thread(target=self._loop, name="discord-presence", daemon=True).start()

    def set(self, details: str, state: Optional[str] = None, start: Optional[int] = None,
            large_text: Optional[str] = None, buttons: Optional[list] = None) -> None:
        """Describe what the player is doing now. Cheap to call every frame; it only queues."""
        activity: dict = {"details": details[:128], "assets": {"large_image": "logo"}}
        if state:
            activity["state"] = state[:128]
        if start:
            activity["timestamps"] = {"start": start}
        if large_text:
            activity["assets"]["large_text"] = large_text[:128]
        if buttons:
            activity["buttons"] = buttons[:2]
        with self._lock:
            if activity != self._wanted:
                self._wanted = activity
                self._wake.set()

    def set_enabled(self, on: bool) -> None:
        """Off clears the card from the profile (the connection stays open, idle)."""
        with self._lock:
            self.enabled = on
            self._wake.set()

    def _loop(self) -> None:
        pipe: Optional[_Pipe] = None
        last_send = 0.0
        next_attempt = 0.0
        while True:
            if pipe is None:
                # set() wakes this thread on every change, so the retry spacing is kept by
                # the clock, not by the wait - otherwise a rising score would rescan for
                # Discord's socket every few frames while Discord is closed.
                if time.monotonic() < next_attempt:
                    self._wake.wait(next_attempt - time.monotonic())
                    self._wake.clear()
                    continue
                next_attempt = time.monotonic() + RETRY
                try:
                    pipe = _Pipe()
                    pipe.send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
                    pipe.recv()  # READY
                    self._sent = None
                except (OSError, ValueError, struct.error):
                    if pipe:
                        pipe.close()
                    pipe = None
                    continue

            with self._lock:
                target = self._wanted if self.enabled else None
            if target == self._sent:
                self._wake.wait()
                self._wake.clear()
                continue
            wait = MIN_INTERVAL - (time.monotonic() - last_send)
            if wait > 0:
                time.sleep(wait)
                continue  # pick up whatever is wanted *now*, not what was wanted before the nap

            try:
                pipe.send(OP_FRAME, {"cmd": "SET_ACTIVITY", "nonce": str(uuid.uuid4()),
                                     "args": {"pid": os.getpid(), "activity": target}})
                pipe.recv()
                self._sent = target
                last_send = time.monotonic()
            except (OSError, ValueError, struct.error):
                pipe.close()
                pipe = None  # Discord quit or restarted; reconnect and resend
