# Copyright (C) 2026 Youssef Ahmed - MEGA SNAKE (see LICENSE)
# SPDX-License-Identifier: GPL-3.0-only
"""Dev-only: measure how smooth multiplayer looks, with no sockets and no window.

Runs a real host `Game` and a real guest `Game` in one process, joined by a fake network with a
chosen latency and jitter, steps both at 60 FPS, and reports what the guest would see:

  speed CV   how uneven the snake's on-screen speed is (0 = perfectly smooth)
  stalls     share of frames where a moving snake does not move at all
  max jump   biggest single-frame move, as a multiple of the normal per-frame move
  path err   how far the drawn head strays from the line of cells it actually travelled
             (corner cutting on turns shows up here)
  edge jump  biggest single-frame move while crossing a screen edge (wrap-around pop)
  lag        how far behind the host the guest's picture is, in ms
  traffic    snapshots per second and kilobytes per second sent by the host

The first four are measured away from the screen edges; wrap-around is reported on its own.

    python tools/mp_sim.py            # a few network conditions
    python tools/mp_sim.py --seconds 40
"""
import argparse
import json
import math
import os
import random
import statistics
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_info  # noqa: E402

build_info.STORE = "sim"  # no auto-updater thread
import persistence  # noqa: E402

persistence.save = lambda data: None  # never touch the real save file
import main  # noqa: E402
from main import Game, STATE_PLAYING, POWERUP_GHOST, GRID_W, GRID_H  # noqa: E402
from constants import MODES, LAN_RULESETS  # noqa: E402

FPS = 60
DT = 1.0 / FPS

# Keep every measured frame a living, un-teleported snake: no bombs (ghost mode doesn't stop those) and no portals.
main.maybe_spawn_downerup = lambda *a, **k: None
main.maybe_spawn_portal_pair = lambda *a, **k: None


class Network:
    """One-way host -> guest pipe with latency, jitter and TCP-style in-order delivery."""

    def __init__(self, rng, latency, jitter):
        self.rng, self.latency, self.jitter = rng, latency, jitter
        self.now = 0.0
        self.pending = []  # (arrival_time, message)
        self.last_arrival = 0.0
        self.sent = 0
        self.bytes = 0

    def send(self, obj):
        raw = json.dumps(obj)
        self.sent += 1
        self.bytes += len(raw) + 1
        arrival = max(self.now + self.latency + self.rng.uniform(0, self.jitter), self.last_arrival)
        self.last_arrival = arrival
        self.pending.append((arrival, json.loads(raw)))

    def deliver(self):
        ready = [m for t, m in self.pending if t <= self.now]
        self.pending = [(t, m) for t, m in self.pending if t > self.now]
        return ready


class HostLink:
    connected = True
    reconnecting = False
    peer_present = True
    roster = {"host": True, "p2": True}

    def __init__(self, net):
        self.net = net

    def poll(self):
        return []

    def send(self, obj):
        self.net.send(obj)
        return True


class GuestLink:
    connected = True
    reconnecting = False
    peer_present = True
    roster = {"host": True, "p2": True}

    def __init__(self, net):
        self.net = net

    def poll(self):
        return self.net.deliver()

    def send(self, obj):
        return True


def make_game(role, link, ruleset="Classic"):
    g = Game()
    g.settings["transitions"] = False
    g.lan_role = role
    g.lan_link = link
    g.lan_online = False
    g.mode_idx = MODES.index("Coop")
    g.lan_ruleset_name = ruleset
    g.lan_cfg_override = dict(LAN_RULESETS[ruleset])
    g.lan_known_slots = {"host", "p2"} if role == "host" else set()
    g.snapshot_seq = 0
    g.last_snapshot_seq = -1
    g.match_meta_sent = False
    g.reset_run(match_size=2)
    g.state = STATE_PLAYING
    g.active_powerups[POWERUP_GHOST] = 1e9  # nobody dies, so the run never ends
    return g


def guest_alpha(g):
    fn = getattr(g, "_client_alpha", None)
    if fn:
        return fn()
    return min(1.0, g.snapshot_age / main.NETWORK_SNAPSHOT_INTERVAL)


def host_alpha(h):
    fn = getattr(h, "_host_alpha", None)
    if fn:
        return fn()
    return 1.0 if h.lan_role else min(1.0, h.move_accum / h.move_interval())


def wdist(a, b):
    dx = abs(a[0] - b[0]); dy = abs(a[1] - b[1])
    return math.hypot(min(dx, GRID_W - dx), min(dy, GRID_H - dy))


def seg_dist(p, a, b):
    """Distance from p to the segment a-b, trying the screen-edge wrap-around copies of p too."""
    ax, ay = a; bx, by = b
    vx, vy = bx - ax, by - ay
    best = 1e9
    for ox in (0, GRID_W, -GRID_W):
        for oy in (0, GRID_H, -GRID_H):
            px, py = p[0] + ox, p[1] + oy
            t = 0.0 if vx == vy == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
            best = min(best, math.hypot(px - (ax + t * vx), py - (ay + t * vy)))
    return best


def run(seconds, latency, jitter, seed=1, score=0, view="guest"):
    """view='guest' measures the guest's picture; view='host' measures the host's own screen."""
    rng = random.Random(seed)
    random.seed(seed)  # the game itself uses the global generator (food and power-up spawns)
    net = Network(rng, latency, jitter)
    h = make_game("host", HostLink(net))
    g = make_game("client", GuestLink(net))
    g._net_now = lambda: net.now  # the guest's clock is the simulated one
    h.score = score
    snake_idx = 0
    samples = []          # per frame: guest-rendered head, host truth head
    cells = []            # the cells the host head actually visited, with the time it entered each
    last_head = None
    turn_every = 7
    ticks = 0
    for frame in range(int(seconds * FPS)):
        net.now = frame * DT
        h.update_playing(DT)
        h.score = max(h.score, score)  # keep the speed tier fixed for the run
        head = h.players[0].head
        if head != last_head:
            cells.append((net.now, head))
            last_head = head
            ticks += 1
            if ticks % turn_every == 0:  # steer in a way that turns at random
                d = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
                h._p1_set_direction(d)
                h.players[1].set_direction(rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)]))
        if view == "guest":
            g._lan_client_poll(DT)
            if g.players[snake_idx] is not None and len(g.players[snake_idx].body) and g.last_snapshot_seq >= 0:
                shown = g.players[snake_idx].render_positions(guest_alpha(g))[0]
            else:
                continue
        else:
            shown = h.players[snake_idx].render_positions(host_alpha(h))[0]
        truth = h.players[0].render_positions(min(1.0, h.move_accum / h.move_interval()))[0]
        samples.append((net.now, shown, truth, h.move_interval()))

    warm = int(1.5 * FPS)
    samples = samples[warm:]
    speeds, ideal, path_err, edge_speeds = [], [], [], []
    stalls = 0
    near_edge = lambda p: p[0] < 1.2 or p[0] > GRID_W - 2.2 or p[1] < 1.2 or p[1] > GRID_H - 2.2
    for i in range(1, len(samples)):
        t, p, _, iv = samples[i]
        q = samples[i - 1][1]
        d = wdist(p, q)
        if near_edge(p) or near_edge(q):
            edge_speeds.append(d / DT / (1.0 / iv))
            continue
        v = d / DT
        speeds.append(v)
        ideal.append(1.0 / iv)
        if v < 0.05 * (1.0 / iv):
            stalls += 1
    # path error: distance to the polyline through the visited cells (centre-to-centre), over the last ~2s of travel
    for t, p, _, _ in samples:
        if near_edge(p):
            continue
        recent = [c for tm, c in cells if tm <= t + 0.3][-30:]
        if len(recent) < 2:
            continue
        best = min((seg_dist(p, a, b) for a, b in zip(recent, recent[1:]) if wdist(a, b) <= 1.01), default=0.0)
        path_err.append(best)
    # lag: shift the host truth back in time until it matches what is shown
    best_lag, best_err = 0.0, 1e9
    by_t = [(t, tr) for t, _, tr, _ in samples]
    for lag_ms in range(0, 601, 20):
        lag = lag_ms / 1000.0
        errs = []
        for k, (t, p, _, _) in enumerate(samples):
            j = k - int(round(lag * FPS))
            if j >= 0:
                errs.append(wdist(p, by_t[j][1]))
        e = statistics.fmean(errs) if errs else 1e9
        if e < best_err:
            best_err, best_lag = e, lag_ms
    mean_ideal = statistics.fmean(ideal) if ideal else 1.0
    return {
        "speed_cv": statistics.pstdev(speeds) / statistics.fmean(speeds) if speeds and statistics.fmean(speeds) else 0.0,
        "stalls": stalls / max(1, len(speeds)),
        "max_jump": max(speeds) / mean_ideal if speeds else 0.0,
        "edge_jump": max(edge_speeds) if edge_speeds else 0.0,
        "path_err": statistics.fmean(path_err) if path_err else 0.0,
        "path_err_max": max(path_err) if path_err else 0.0,
        "lag_ms": best_lag,
        "snaps_per_s": net.sent / seconds,
        "kb_per_s": net.bytes / seconds / 1024.0,
    }


SCENARIOS = [
    ("LAN (5ms, steady)", 0.005, 0.002),
    ("Good Wi-Fi (15ms +-10)", 0.015, 0.010),
    ("Bad Wi-Fi / online (60ms +-40)", 0.060, 0.040),
]
SPEEDS = [("start speed", 0), ("fast (score 300)", 300)]


def report(seconds):
    print(f"{'condition':34} {'speed':>16} {'spd CV':>7} {'stalls':>7} {'max x':>6} {'path err':>10} {'edge x':>7} {'lag ms':>7} {'snap/s':>7} {'KB/s':>6}")
    for view in ("guest", "host"):
        print(f"--- {view}'s own screen ---")
        for name, lat, jit in (SCENARIOS if view == "guest" else SCENARIOS[:1]):
            for sname, score in SPEEDS:
                r = run(seconds, lat, jit, score=score, view=view)
                print(f"{name:34} {sname:>16} {r['speed_cv']:7.2f} {r['stalls'] * 100:6.1f}% {r['max_jump']:6.1f} "
                      f"{r['path_err']:5.2f}/{r['path_err_max']:.2f} {r['edge_jump']:7.1f} {r['lag_ms']:7.0f} {r['snaps_per_s']:7.1f} {r['kb_per_s']:6.1f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30.0)
    report(ap.parse_args().seconds)
