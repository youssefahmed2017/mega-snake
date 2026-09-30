"""Local-network (LAN) multiplayer transport.

No external/cloud server is involved: one player's game instance opens a plain
TCP socket and listens on the local network (the "host"); the other player's
game instance connects directly to that machine's LAN IP (the "client"). Both
are just this same game.py process - "hosting" only means "temporarily acting
as the authoritative simulation for this one match," not running a dedicated
server. Everything here is Python stdlib (socket/threading/json).

Wire format: newline-delimited JSON objects, one per line, on a plain TCP
stream. Reader threads keep recv() off the caller's render thread so pygame's
event loop never blocks on the network.
"""
from __future__ import annotations

import json
import queue
import socket
import threading
from typing import List, Optional

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
