// MEGA SNAKE online relay - a Cloudflare Worker + one Durable Object per room.
//
// The relay never runs the game. Exactly like LAN mode, the host player's
// game is the authoritative simulation and the guest is a pure renderer; this
// just pipes their newline-free JSON messages to each other over WebSockets,
// pairs them up by a short room code, and holds a disconnected player's seat
// for a short grace period so a network blip doesn't end the match.
//
// Routes (all WebSocket upgrades; `v` = the game version, which must match):
//   /host?v=1.9.0                            create a room, become its host
//   /join/ABCDE?v=1.9.0                      join room ABCDE as the guest
//   /rejoin/ABCDE?role=host&token=...&v=...  reclaim your seat after a drop
//
// Control messages the relay sends (game messages never start with "_"):
//   _room {code, token}   host: room created        _joined {token, peer}  guest: joined
//   _rejoined {peer}      seat reclaimed            _peer_joined           host: guest arrived
//   _peer_lost            other side dropped        _peer_back             other side is back
//   _peer_gone            other side never came back - the match is over
//   _error {msg}          request refused (bad code, room full, version mismatch, ...)

import { DurableObject } from "cloudflare:workers";

const CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no 0/O or 1/I lookalikes
const CODE_LEN = 5;
const GRACE_MS = 20_000; // how long a dropped player's seat is held
const SWEEP_MS = 6 * 60 * 60 * 1000; // safety net for rooms that never closed cleanly
const MAX_MESSAGE_BYTES = 64 * 1024;

function newCode() {
  const bytes = crypto.getRandomValues(new Uint8Array(CODE_LEN));
  return Array.from(bytes, (b) => CODE_CHARS[b % CODE_CHARS.length]).join("");
}

function otherRole(role) {
  return role === "host" ? "guest" : "host";
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.headers.get("Upgrade") !== "websocket") {
      if (url.pathname === "/") {
        return new Response("MEGA SNAKE online relay is running.\n");
      }
      return new Response("Expected a WebSocket upgrade.\n", { status: 426 });
    }

    const v = url.searchParams.get("v") || "";
    const forward = (code, params) => {
      const target = new URL("https://room/connect");
      target.searchParams.set("code", code);
      target.searchParams.set("v", v);
      for (const [k, val] of Object.entries(params)) target.searchParams.set(k, val);
      const stub = env.ROOMS.get(env.ROOMS.idFromName(code));
      return stub.fetch(new Request(target, request));
    };

    if (url.pathname === "/host") {
      // A fresh random code is almost always free; retry on the rare collision.
      for (let i = 0; i < 8; i++) {
        const resp = await forward(newCode(), { action: "host" });
        if (resp.status !== 409) return resp;
      }
      return new Response("Could not allocate a room, try again.\n", { status: 503 });
    }

    const join = url.pathname.match(/^\/join\/([A-Z0-9]{5})$/);
    if (join) return forward(join[1], { action: "join" });

    const rejoin = url.pathname.match(/^\/rejoin\/([A-Z0-9]{5})$/);
    if (rejoin) {
      return forward(rejoin[1], {
        action: "rejoin",
        role: url.searchParams.get("role") || "",
        token: url.searchParams.get("token") || "",
      });
    }

    return new Response("Not found.\n", { status: 404 });
  },
};

export class Room extends DurableObject {
  // Everything that must survive hibernation lives in storage ("room") or in
  // each socket's tag (its role); nothing important is kept in memory.

  async fetch(request) {
    const url = new URL(request.url);
    const action = url.searchParams.get("action");
    const code = url.searchParams.get("code");
    const v = url.searchParams.get("v");
    let room = await this.ctx.storage.get("room");

    if (action === "host") {
      if (room) return new Response("Code taken.", { status: 409 });
      room = { code, version: v, tokens: { host: crypto.randomUUID(), guest: null }, lost: {} };
      await this.ctx.storage.put("room", room);
      await this.ctx.storage.setAlarm(Date.now() + SWEEP_MS);
      return this.accept("host", { type: "_room", code, token: room.tokens.host });
    }

    if (action === "join") {
      if (!room) return this.reject("Room not found. Check the code and try again.");
      if (room.version !== v) {
        return this.reject(`Version mismatch: host has v${room.version}, you have v${v}. Update to the same version.`);
      }
      if (room.tokens.guest) return this.reject("That room is already full.");
      room.tokens.guest = crypto.randomUUID();
      await this.ctx.storage.put("room", room);
      const resp = this.accept("guest", { type: "_joined", token: room.tokens.guest, peer: !room.lost.host });
      this.sendTo("host", { type: "_peer_joined" });
      return resp;
    }

    if (action === "rejoin") {
      const role = url.searchParams.get("role");
      const token = url.searchParams.get("token");
      if (!room || (role !== "host" && role !== "guest") || !token || room.tokens[role] !== token) {
        return this.reject("That game has ended.");
      }
      for (const old of this.ctx.getWebSockets(role)) {
        try { old.close(4001, "replaced"); } catch { /* already closing */ }
      }
      delete room.lost[role];
      await this.ctx.storage.put("room", room);
      const other = otherRole(role);
      const peer = this.ctx.getWebSockets(other).length > 0 && !room.lost[other];
      const resp = this.accept(role, { type: "_rejoined", peer });
      this.sendTo(other, { type: "_peer_back" });
      return resp;
    }

    return new Response("Bad request.", { status: 400 });
  }

  accept(role, firstMessage) {
    const [client, server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server, [role]);
    server.send(JSON.stringify(firstMessage));
    return new Response(null, { status: 101, webSocket: client });
  }

  reject(msg) {
    // Accept-then-close instead of an HTTP error status, so the game gets a
    // readable reason instead of a bare "server rejected WebSocket" error.
    const [client, server] = Object.values(new WebSocketPair());
    server.accept();
    server.send(JSON.stringify({ type: "_error", msg }));
    server.close(4000, "rejected");
    return new Response(null, { status: 101, webSocket: client });
  }

  sendTo(role, obj) {
    const text = typeof obj === "string" ? obj : JSON.stringify(obj);
    for (const ws of this.ctx.getWebSockets(role)) {
      try { ws.send(text); } catch { /* socket closing; its close handler deals with it */ }
    }
  }

  roleOf(ws) {
    const tags = this.ctx.getTags(ws);
    return tags.includes("host") ? "host" : tags.includes("guest") ? "guest" : null;
  }

  async webSocketMessage(ws, message) {
    const role = this.roleOf(ws);
    if (!role) return;
    const size = typeof message === "string" ? message.length : message.byteLength;
    if (size > MAX_MESSAGE_BYTES) return;
    this.sendTo(otherRole(role), message);
  }

  async webSocketClose(ws, code) {
    try { ws.close(1000, "bye"); } catch { /* already closed */ }
    await this.handleDrop(ws);
  }

  async webSocketError(ws) {
    await this.handleDrop(ws);
  }

  async handleDrop(ws) {
    const role = this.roleOf(ws);
    if (!role) return;
    // A rejoin replaces the old socket; its late close event isn't a drop.
    if (this.ctx.getWebSockets(role).some((s) => s !== ws)) return;
    const room = await this.ctx.storage.get("room");
    if (!room || room.lost[role]) return;
    room.lost[role] = Date.now();
    await this.ctx.storage.put("room", room);
    this.sendTo(otherRole(role), { type: "_peer_lost" });
    await this.ctx.storage.setAlarm(Date.now() + GRACE_MS);
  }

  async alarm() {
    const room = await this.ctx.storage.get("room");
    if (!room) return;
    const now = Date.now();

    for (const role of ["host", "guest"]) {
      const lostAt = room.lost[role];
      if (lostAt && now - lostAt >= GRACE_MS - 100) {
        // Never came back: end the match for whoever is left and drop the room.
        const other = otherRole(role);
        this.sendTo(other, { type: "_peer_gone" });
        for (const s of this.ctx.getWebSockets(other)) {
          try { s.close(1000, "peer gone"); } catch { /* already closed */ }
        }
        await this.ctx.storage.deleteAll();
        return;
      }
    }

    if (this.ctx.getWebSockets().length === 0) {
      await this.ctx.storage.deleteAll();
      return;
    }
    const pending = Object.values(room.lost);
    const next = pending.length ? Math.min(...pending) + GRACE_MS : now + SWEEP_MS;
    await this.ctx.storage.setAlarm(next);
  }
}
