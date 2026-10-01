"""Multiplayer transports: LAN (direct TCP) and Online (WebSocket relay).

No external/cloud server is involved: one player's game instance opens a plain
TCP socket and listens on the local network (the "host"); the other player's
game instance connects directly to that machine's LAN IP (the "client"). Both
are just this same game.py process - "hosting" only means "temporarily acting
as the authoritative simulation for this one match," not running a dedicated
server. Everything here is Python stdlib (socket/threading/json).

Wire format: newline-delimited JSON objects, one per line, on a plain TCP
stream. Reader threads keep recv() off the caller's render thread so pygame's
event loop never blocks on the network.

Online mode (OnlineHost / OnlineClient) keeps exactly the same roles and
messages, but both players connect out to a small relay (server/ in this
repo, a Cloudflare Worker) that pairs them by room code and forwards
messages. OnlineLink has the same send/poll/connected/error/close surface as
LineSocket, so the game code drives both transports identically.
"""
from __future__ import annotations

import json
import queue
import socket
import threading
import time
import urllib.parse
from typing import List, Optional

from tls import ssl_context

DEFAULT_PORT = 51999


def get_local_ip() -> str:
    """Best-effort LAN IP for display ("share this with your friend"). Opens a
    UDP socket and 'connects' it (UDP connect() doesn't send any packets, it
    just asks the OS to pick a route) to see which local interface would be
    used to reach the internet, then reads that socket's own address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class LineSocket:
    """Wraps a connected TCP socket. A background thread reads it and pushes
    decoded JSON objects into a thread-safe queue; send() writes straight
    through (fine for small, infrequent messages)."""

    # A direct LAN link has no relay in between, so the other player is
    # always "present" while connected, and per-frame snapshots are cheap.
    peer_present = True
    reconnecting = False
    snapshot_min_gap = 0.0

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.inbox: "queue.Queue[dict]" = queue.Queue()
        self.connected = True
        self.error: Optional[str] = None
        self._buf = b""
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                self._buf += chunk
                while b"\n" in self._buf:
                    line, self._buf = self._buf.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        self.inbox.put(json.loads(line.decode("utf-8")))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass
        except OSError as e:
            self.error = self.error or str(e)
        finally:
            self.connected = False

    def send(self, obj: dict) -> bool:
        try:
            self.sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
            return True
        except OSError as e:
            self.error = self.error or str(e)
            self.connected = False
            return False

    def poll(self) -> List[dict]:
        items = []
        while True:
            try:
                items.append(self.inbox.get_nowait())
            except queue.Empty:
                break
        return items

    def close(self) -> None:
        self.connected = False
        try:
            self.sock.close()
        except OSError:
            pass


class Host:
    """Listens for exactly one player. Call poll_new_connection() every frame
    (non-blocking) until it returns a LineSocket."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", port))
        self._server.listen(1)
        self._server.setblocking(False)
        self.link: Optional[LineSocket] = None

    def poll_new_connection(self) -> Optional[LineSocket]:
        if self.link is not None:
            return self.link
        try:
            conn, _addr = self._server.accept()
            conn.setblocking(True)
            self.link = LineSocket(conn)
            return self.link
        except BlockingIOError:
            return None
        except OSError:
            return None

    def failure(self) -> Optional[str]:
        return None  # a bound LAN listener can't fail after construction

    def close(self) -> None:
        try:
            self._server.close()
        except OSError:
            pass
        if self.link:
            self.link.close()


class Client:
    """Connects to a Host at ip:port. The connection attempt runs on a
    background thread; poll_connect_result() each frame until it stops
    returning None."""

    def __init__(self, ip: str, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self.ip = ip
        self.label = ip
        self.port = port
        self.link: Optional[LineSocket] = None
        self.error: Optional[str] = None
        self._done = False
        self._thread = threading.Thread(target=self._connect, args=(timeout,), daemon=True)
        self._thread.start()

    def _connect(self, timeout: float) -> None:
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=timeout)
            self.link = LineSocket(sock)
        except OSError as e:
            self.error = str(e)
        finally:
            self._done = True

    def poll_connect_result(self) -> Optional[bool]:
        """True once connected, False once failed, None while still connecting."""
        if not self._done:
            return None
        return self.link is not None

    def close(self) -> None:
        if self.link:
            self.link.close()


# ---------------------------------------------------------------------------
# Online (relay) transport
# ---------------------------------------------------------------------------

# How long a dropped link keeps trying to reclaim its seat. The relay holds
# the seat for 20s, so give up a little before that.
ONLINE_RECONNECT_SECONDS = 15.0
ROOM_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_CODE_LEN = 5


def normalize_room_code(text: str) -> str:
    """Uppercase and map the lookalikes the relay never generates (0/O, 1/I)."""
    return text.strip().upper().replace("0", "O").replace("1", "I")


class OnlineLink:
    """One player's WebSocket to the relay. Same surface as LineSocket, plus:

    - peer_present: False while the other player's connection has dropped and
      the relay is holding their seat (the host freezes the match meanwhile).
    - reconnecting: True while *this* side lost its connection and is trying
      to reclaim its seat. `connected` stays True during that window, so the
      game only ends the match if reconnecting finally fails.
    """

    # Snapshots go through the relay, so don't send one every frame: one per
    # snake tick (the game forces those) plus this as a floor for timers.
    snapshot_min_gap = 0.25

    def __init__(self, server_url: str, path: str, version: str, role: str):
        self.server_url = server_url.rstrip("/")
        self.version = version
        self.role = role  # "host" | "guest"
        self.inbox: "queue.Queue[dict]" = queue.Queue()
        self.connected = False  # True once the relay accepted us
        self.done = False  # True once the first handshake resolved either way
        self.error: Optional[str] = None
        self.code: Optional[str] = None
        self.token: Optional[str] = None
        self.peer_joined = False
        self.peer_present = role == "guest"
        self.reconnecting = False
        self._final = False  # the relay ended this session; don't reconnect
        self._closing = False
        self._ws = None
        self._thread = threading.Thread(target=self._run, args=(path,), daemon=True)
        self._thread.start()

    def _open(self, path: str):
        # Imported lazily so LAN-only use never needs the websockets package.
        from websockets.sync.client import connect

        sep = "&" if "?" in path else "?"
        url = f"{self.server_url}{path}{sep}v={urllib.parse.quote(self.version)}"
        return connect(
            url,
            ssl=ssl_context() if url.startswith("wss://") else None,
            open_timeout=8,
            ping_interval=10,
            ping_timeout=10,
            close_timeout=2,
            compression=None,
            user_agent_header=f"MegaSnake/{self.version}",
        )

    def _run(self, path: str) -> None:
        try:
            self._ws = self._open(path)
        except Exception as e:  # DNS, TLS, refused, timeout, bad status...
            self.error = f"Can't reach the online server ({type(e).__name__})."
            self.done = True
            return

        while not self._closing:
            try:
                for raw in self._ws:
                    self._handle(raw)
            except Exception:
                pass  # ConnectionClosed / network error - decided below
            if self._closing or self._final or not self.connected:
                break
            if not self._reconnect():
                break

        if not self._closing and not self.error:
            self.error = "Lost connection to the online server."
        self.connected = False
        self.done = True

    def _handle(self, raw) -> None:
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(msg, dict):
            return
        mtype = msg.get("type", "")
        if mtype == "_room":
            self.code, self.token = msg.get("code"), msg.get("token")
            self.connected = self.done = True
        elif mtype == "_joined":
            self.token = msg.get("token")
            self.peer_present = bool(msg.get("peer", True))
            self.connected = self.done = True
        elif mtype == "_peer_joined":
            self.peer_joined = self.peer_present = True
        elif mtype == "_peer_lost":
            self.peer_present = False
        elif mtype == "_peer_back":
            self.peer_present = True
        elif mtype == "_peer_gone":
            self.error = "The other player's connection timed out."
            self._final = True
            self.connected = False
        elif mtype == "_error":
            self.error = str(msg.get("msg") or "The online server refused the request.")
            self._final = True
            self.connected = False
            self.done = True
        elif not mtype.startswith("_"):
            self.inbox.put(msg)

    def _reconnect(self) -> bool:
        if not (self.code and self.token):
            return False
        self.reconnecting = True
        deadline = time.monotonic() + ONLINE_RECONNECT_SECONDS
        delay = 0.5
        try:
            while not self._closing and time.monotonic() < deadline:
                try:
                    query = urllib.parse.urlencode({"role": self.role, "token": self.token})
                    ws = self._open(f"/rejoin/{self.code}?{query}")
                except Exception:
                    time.sleep(delay)
                    delay = min(delay * 2, 3.0)
                    continue
                try:
                    first = json.loads(ws.recv(timeout=8))
                except Exception:
                    ws.close()
                    continue
                if first.get("type") == "_rejoined":
                    self.peer_present = bool(first.get("peer", True))
                    self._ws = ws
                    return True
                self.error = str(first.get("msg") or "That game has ended.")
                ws.close()
                return False
            return False
        finally:
            self.reconnecting = False

    def send(self, obj: dict) -> bool:
        ws = self._ws
        if ws is None or not self.connected or self.reconnecting:
            return False  # dropped on purpose; snapshots are idempotent anyway
        try:
            ws.send(json.dumps(obj))
            return True
        except Exception:
            return False  # the reader thread notices the drop and reconnects

    def poll(self) -> List[dict]:
        items = []
        while True:
            try:
                items.append(self.inbox.get_nowait())
            except queue.Empty:
                break
        return items

    def close(self) -> None:
        self._closing = True
        self.connected = False
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


class OnlineHost:
    """Creates a room on the relay. Same polling surface as Host; read .code
    once it's set to show the room code."""

    def __init__(self, server_url: str, version: str):
        self.link = OnlineLink(server_url, "/host", version, role="host")

    @property
    def code(self) -> Optional[str]:
        return self.link.code

    def failure(self) -> Optional[str]:
        if self.link.done and not self.link.connected:
            return self.link.error or "Could not create a room."
        return None

    def poll_new_connection(self) -> Optional[OnlineLink]:
        if self.link.connected and self.link.peer_joined:
            return self.link
        return None

    def close(self) -> None:
        self.link.close()


class OnlineClient:
    """Joins a room by code. Same polling surface as Client."""

    def __init__(self, server_url: str, code: str, version: str):
        self.code = normalize_room_code(code)
        self.label = f"room {self.code}"
        self._pending = OnlineLink(server_url, f"/join/{self.code}", version, role="guest")
        self._pending.code = self.code
        self.link: Optional[OnlineLink] = None
        self.error: Optional[str] = None

    def poll_connect_result(self) -> Optional[bool]:
        if not self._pending.done:
            return None
        if self._pending.connected:
            self.link = self._pending
            return True
        self.error = self._pending.error or "Could not join the room."
        return False

    def close(self) -> None:
        if self.link is None:
            self._pending.close()
