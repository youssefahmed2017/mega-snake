"""Multiplayer transports: LAN (direct TCP) and Online (WebSocket relay).

Up to 4 players total: one host (the authoritative simulation - "hosting"
just means "temporarily running the game everyone else renders", not a
dedicated server) plus up to 3 guests, each a pure renderer sending input.
Guest slots are "p2", "p3", "p4" - assigned in join order, never reused
within a match.

Both transports expose the SAME interface to the host's game code, so
main.py drives LAN and Online hosting identically:
    .poll() -> list[dict]      new messages, each tagged "from": <slot>
    .send(obj)                 broadcast obj to every connected guest
    .roster: dict[slot, bool]  which slots are in the match; True=connected,
                                False=dropped but might still reconnect
                                (Online only - LAN has no reconnect window)
    .peer_present               True iff every slot in .roster is connected
    .connected                  the host's own channel is still viable
    .failure() -> str | None    why hosting couldn't start, if it couldn't

A slot that falls out of .roster entirely (not just False) means that
player left the match for good; the game treats it exactly like their snake
dying, so the rest of the match continues without them. Only losing the
HOST ends the match for everyone - there's no simulation without one.

A guest's own channel (LAN LineSocket, or OnlineLink as a guest) is simpler
and basically unchanged from the 2-player design: one connection to the
host/relay, poll()/send() to it, reconnect-with-grace for Online only.
"""
from __future__ import annotations

import json
import queue
import socket
import threading
import time
import urllib.parse
from typing import Dict, List, Optional

from tls import ssl_context

DEFAULT_PORT = 51999
GUEST_SLOTS = ["p2", "p3", "p4"]
ALL_SLOTS = ["host"] + GUEST_SLOTS


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
        return self.send_raw((json.dumps(obj) + "\n").encode("utf-8"))

    def send_raw(self, line: bytes) -> bool:
        try:
            self.sock.sendall(line)
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


class GuestLink(LineSocket):
    """A guest's connection to a LAN host. Same as LineSocket, plus the
    constant fields OnlineLink-as-guest also has, so main.py's client-side
    code (which only ever has ONE connection, to whoever's authoritative)
    doesn't need to know whether it's LAN or Online."""

    peer_present = True  # no relay in between; "the host" is just "connected"
    reconnecting = False  # LAN has no reconnect-with-grace
    my_slot = "p2"  # set by Client after a slot assignment arrives (LAN: always p2, it's 1:1)


class Host:
    """Listens for up to 3 guests (slots p2/p3/p4, assigned in join order).
    Call poll() every frame - it accepts any pending connections, merges
    every guest's incoming messages (tagged "from": <slot>), and notices
    drops, all in one pass. send() broadcasts to every connected guest.
    Implements the same surface as OnlineLink-as-host (see module docstring)
    so main.py drives LAN and Online hosting identically."""
    reconnecting = False  # LAN has no reconnect-with-grace; a drop is final
    reconnecting = False  # LAN has no reconnect-with-grace; a drop is final
    connected = True  # the listener itself; doesn't track individual guests
    error: Optional[str] = None

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", port))
        self._server.listen(len(GUEST_SLOTS))
        self._server.setblocking(False)
        self.links: Dict[str, LineSocket] = {}
        self.roster: Dict[str, bool] = {"host": True}

    def _free_slot(self) -> Optional[str]:
        for slot in GUEST_SLOTS:
            if slot not in self.links:
                return slot
        return None

    def _accept_pending(self) -> None:
        while True:
            try:
                conn, _addr = self._server.accept()
            except (BlockingIOError, OSError):
                return
            slot = self._free_slot()
            if slot is None:
                try:
                    conn.close()  # room already full
                except OSError:
                    pass
                continue
            conn.setblocking(True)
            self.links[slot] = LineSocket(conn)
            self.roster[slot] = True

    def poll(self) -> List[dict]:
        self._accept_pending()
        items: List[dict] = []
        for slot, link in list(self.links.items()):
            for msg in link.poll():
                if isinstance(msg, dict):
                    msg["from"] = slot
                    items.append(msg)
            if not link.connected:
                # Final, not a grace period - LAN can't reconnect a dropped
                # TCP socket. The rest of the match continues without them.
                del self.links[slot]
                self.roster.pop(slot, None)
        return items

    def send(self, obj: dict) -> bool:
        # Snapshots go out to all 1-3 guests every ~100ms; encode once instead
        # of re-serializing the same (sometimes sizeable) payload per guest.
        line = (json.dumps(obj) + "\n").encode("utf-8")
        ok = True
        for link in self.links.values():
            ok = link.send_raw(line) and ok
        return ok

    def close_slot(self, slot: str) -> None:
        """Disconnects just one guest (e.g. it's on the wrong game version),
        freeing that slot for someone else without affecting anyone else."""
        link = self.links.pop(slot, None)
        if link:
            link.close()
        self.roster.pop(slot, None)

    @property
    def peer_present(self) -> bool:
        return all(self.roster.values())

    def failure(self) -> Optional[str]:
        return None  # a bound LAN listener can't fail after construction

    def close(self) -> None:
        try:
            self._server.close()
        except OSError:
            pass
        for link in self.links.values():
            link.close()


class Client:
    """Connects to a Host at ip:port as a guest. The connection attempt runs
    on a background thread; poll_connect_result() each frame until it stops
    returning None."""

    def __init__(self, ip: str, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self.ip = ip
        self.label = ip
        self.port = port
        self.link: Optional[GuestLink] = None
        self.error: Optional[str] = None
        self._done = False
        self._thread = threading.Thread(target=self._connect, args=(timeout,), daemon=True)
        self._thread.start()

    def _connect(self, timeout: float) -> None:
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=timeout)
            self.link = GuestLink(sock)
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
    """One player's WebSocket to the relay - serves as either the host's
    single channel to everyone (the relay fans in/out for us, so the host
    needs only one connection regardless of guest count) or one guest's
    single channel to the host. Same send/poll/connected/error/close surface
    as LineSocket/Host, plus:

    - my_slot: "host", or whichever of p2/p3/p4 the relay assigned us.
    - roster: dict[slot, bool] of who's in the match and currently connected
      (see module docstring). Meaningful for both roles, but it's the host's
      copy that main.py actually reads to run the match.
    - peer_present: True iff every slot in .roster is connected right now.
    - reconnecting: True while *this* side lost its connection and is trying
      to reclaim its seat. `connected` stays True during that window, so the
      game only ends the match if reconnecting finally fails.
    """

    def __init__(self, server_url: str, path: str, version: str, role: str):
        self.server_url = server_url.rstrip("/")
        self.version = version
        self.role = role  # "host" or "guest" (what we're REQUESTING to be)
        self.inbox: "queue.Queue[dict]" = queue.Queue()
        self.connected = False  # True once the relay accepted us
        self.done = False  # True once the first handshake resolved either way
        self.error: Optional[str] = None
        self.code: Optional[str] = None
        self.token: Optional[str] = None
        self.my_slot: Optional[str] = "host" if role == "host" else None
        self.roster: Dict[str, bool] = {}
        self.reconnecting = False
        self._final = False  # the relay ended this session; don't reconnect
        self._closing = False
        self._ws = None
        self._thread = threading.Thread(target=self._run, args=(path,), daemon=True)
        self._thread.start()

    @property
    def peer_present(self) -> bool:
        return all(self.roster.values())

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
            self.roster = {"host": True}
            self.connected = self.done = True
        elif mtype == "_joined":
            self.token = msg.get("token")
            self.my_slot = msg.get("slot") or self.my_slot
            self.roster = {s: True for s in (msg.get("roster") or {})}
            self.connected = self.done = True
        elif mtype == "_rejoined":
            self.roster = {s: True for s in (msg.get("roster") or {})}
            self.connected = self.done = True
        elif mtype == "_roster":
            # A slot already marked dropped (False) stays dropped until its
            # own _peer_back/_peer_gone - a roster snapshot from some OTHER
            # join shouldn't optimistically mark it connected again.
            was_down = {s for s, up in self.roster.items() if not up}
            self.roster = {s: (s not in was_down) for s in (msg.get("slots") or {})}
        elif mtype == "_peer_lost":
            slot = msg.get("slot")
            if slot:
                self.roster[slot] = False
        elif mtype == "_peer_back":
            slot = msg.get("slot")
            if slot:
                self.roster[slot] = True
        elif mtype == "_peer_gone":
            slot = msg.get("slot")
            if slot == "host":
                self.error = "The host's connection timed out."
                self._final = True
                self.connected = False
            else:
                self.roster.pop(slot, None)  # that player left for good; match continues
                self.inbox.put({"type": "_slot_gone", "slot": slot})
        elif mtype == "_error":
            self.error = str(msg.get("msg") or "The online server refused the request.")
            self._final = True
            self.connected = False
            self.done = True
        elif not mtype.startswith("_"):
            self.inbox.put(msg)

    def _reconnect(self) -> bool:
        if not (self.code and self.token and self.my_slot):
            return False
        self.reconnecting = True
        deadline = time.monotonic() + ONLINE_RECONNECT_SECONDS
        delay = 0.5
        try:
            while not self._closing and time.monotonic() < deadline:
                try:
                    query = urllib.parse.urlencode({"role": self.my_slot, "token": self.token})
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
                    self.roster = {s: True for s in (first.get("roster") or {})}
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
    once it's set to show the room code, .link.roster for who's joined."""

    def __init__(self, server_url: str, version: str):
        self.link = OnlineLink(server_url, "/host", version, role="host")

    @property
    def code(self) -> Optional[str]:
        return self.link.code

    def failure(self) -> Optional[str]:
        if self.link.done and not self.link.connected:
            return self.link.error or "Could not create a room."
        return None

    def close(self) -> None:
        self.link.close()


class OnlineClient:
    """Joins a room by code as a guest. Same polling surface as Client."""

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
