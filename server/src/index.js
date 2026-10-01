// MEGA SNAKE online relay - a Cloudflare Worker + one Durable Object per room.
//
// The relay never runs the game. The host player's game is the single
// authoritative simulation; every guest is a pure renderer. This just pairs
// up to MAX_GUESTS guests with a host by a short room code and relays their
// messages - "relays" meaning: broadcast to everyone else in the room,
// stamped with who sent it. The host uses that stamp to know which guest's
// snake an "input" message is for (the relay decides this from the
// connection itself, not anything the client claims, so a guest can't spoof
// being a different player); chat needs it too so everyone sees who said
// what. A guest doesn't need to know who else is in the room to do its job,
// so it just ignores the stamp on messages that don't need one.
//
// Routes (all WebSocket upgrades; `v` = the game version, which must match):
//   /host?v=1.9.0                            create a room, become its host
//   /join/ABCDE?v=1.9.0                      join room ABCDE as a guest
//   /rejoin/ABCDE?role=host|p2|p3|p4&token=...&v=...   reclaim your seat
//
// Control messages the relay sends (game messages never start with "_"):
//   _room {code, token}        host: room created
//   _joined {token, slot, roster}   guest: joined, which slot you are
//   _rejoined {roster}         seat reclaimed
//   _roster {slots}            everyone: who's connected now changed
//   _peer_lost {slot}          that slot's connection dropped
//   _peer_back {slot}          that slot reconnected
//   _peer_gone {slot}          that slot never came back - they're out for good
//   _error {msg}               request refused (bad code, room full, version mismatch, ...)

import { DurableObject } from "cloudflare:workers";

const CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no 0/O or 1/I lookalikes
const CODE_LEN = 5;
const GUEST_SLOTS = ["p2", "p3", "p4"]; // host is "host"; up to 4 players total
const GRACE_MS = 20_000; // how long a dropped player's seat is held
const SWEEP_MS = 6 * 60 * 60 * 1000; // safety net for rooms that never closed cleanly
const MAX_MESSAGE_BYTES = 64 * 1024;

function newCode() {
  const bytes = crypto.getRandomValues(new Uint8Array(CODE_LEN));
  return Array.from(bytes, (b) => CODE_CHARS[b % CODE_CHARS.length]).join("");
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
  // each socket's tag (its slot), not in memory.

  async fetch(request) {
    const url = new URL(request.url);
    const action = url.searchParams.get("action");
    const code = url.searchParams.get("code");
    const v = url.searchParams.get("v");
    let room = await this.ctx.storage.get("room");

    if (action === "host") {
      if (room) return new Response("Code taken.", { status: 409 });
      room = { code, version: v, tokens: { host: crypto.randomUUID() }, guests: {}, lost: {} };
      await this.ctx.storage.put("room", room);
      await this.ctx.storage.setAlarm(Date.now() + SWEEP_MS);
      return this.accept("host", { type: "_room", code, token: room.tokens.host });
    }

    if (action === "join") {
      if (!room) return this.reject("Room not found. Check the code and try again.");
      if (room.version !== v) {
        return this.reject(`Version mismatch: host has v${room.version}, you have v${v}. Update to the same version.`);
      }
      const slot = GUEST_SLOTS.find((s) => !room.guests[s]);
      if (!slot) return this.reject("That room is already full.");
      const token = crypto.randomUUID();
      room.guests[slot] = token;
      await this.ctx.storage.put("room", room);
      const resp = this.accept(slot, { type: "_joined", token, slot, roster: this.roster(room) });
      // Exclude the joiner itself - it already knows via the _joined reply
      // above; this is for everyone ALREADY in the room finding out.
      this.broadcast(slot, { type: "_roster", slots: this.roster(room) });
      return resp;
    }

    if (action === "rejoin") {
      const role = url.searchParams.get("role");
      const token = url.searchParams.get("token");
      const validRole = role === "host" || GUEST_SLOTS.includes(role);
      const knownToken = role === "host" ? room?.tokens.host : room?.guests[role];
      if (!room || !validRole || !token || knownToken !== token) {
        return this.reject("That game has ended.");
      }
      for (const old of this.ctx.getWebSockets(role)) {
        try { old.close(4001, "replaced"); } catch { /* already closing */ }
      }
      delete room.lost[role];
      await this.ctx.storage.put("room", room);
      const resp = this.accept(role, { type: "_rejoined", roster: this.roster(room) });
      this.broadcast(role, { type: "_peer_back", slot: role });
      return resp;
    }

    return new Response("Bad request.", { status: 400 });
  }

  // Which slots are currently filled (connected or just temporarily lost),
  // sent so a newly (re)joined client can show who's already in the room.
  roster(room) {
    const slots = { host: true };
    for (const s of GUEST_SLOTS) if (room.guests[s]) slots[s] = true;
    return slots;
  }

  accept(slot, firstMessage) {
    const [client, server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server, [slot]);
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

  allSlots() {
    return ["host", ...GUEST_SLOTS];
  }

  // Sends to every OTHER connected slot besides `fromSlot` (null = everyone).
  // This is the one fan-out rule the whole room runs on: the host needs
  // guests' input and chat, guests need the host's state and each other's
  // chat, and nobody needs to tell themselves anything - "broadcast to
  // everyone else" satisfies all of that without the relay needing to know
  // what a message means.
  broadcast(fromSlot, obj) {
    const text = JSON.stringify(obj);
    for (const slot of this.allSlots()) {
      if (slot === fromSlot) continue;
      for (const ws of this.ctx.getWebSockets(slot)) {
        try { ws.send(text); } catch { /* socket closing; its close handler deals with it */ }
      }
    }
  }

  slotOf(ws) {
    const tags = this.ctx.getTags(ws);
    return this.allSlots().find((s) => tags.includes(s)) || null;
  }

  async webSocketMessage(ws, message) {
    const slot = this.slotOf(ws);
    if (!slot) return;
    const size = typeof message === "string" ? message.length : message.byteLength;
    if (size > MAX_MESSAGE_BYTES) return;
    // Stamp the sender's identity server-side - a client can't fake being a
    // different slot, since this comes from which connection sent it, not
    // from anything in the message itself.
    let obj;
    try {
      obj = JSON.parse(message);
    } catch {
      return; // not JSON; a conforming client never sends this
    }
    if (obj && typeof obj === "object" && !Array.isArray(obj)) obj.from = slot;
    this.broadcast(slot, obj);
  }

  async webSocketClose(ws, code) {
    try { ws.close(1000, "bye"); } catch { /* already closed */ }
    await this.handleDrop(ws);
  }

  async webSocketError(ws) {
    await this.handleDrop(ws);
  }

  async handleDrop(ws) {
    const slot = this.slotOf(ws);
    if (!slot) return;
    // A rejoin replaces the old socket; its late close event isn't a drop.
    if (this.ctx.getWebSockets(slot).some((s) => s !== ws)) return;
    const room = await this.ctx.storage.get("room");
    if (!room || room.lost[slot]) return;
    room.lost[slot] = Date.now();
    await this.ctx.storage.put("room", room);
    this.broadcast(slot, { type: "_peer_lost", slot });
    await this.ctx.storage.setAlarm(Date.now() + GRACE_MS);
  }

  async alarm() {
    const room = await this.ctx.storage.get("room");
    if (!room) return;
    const now = Date.now();

    for (const slot of this.allSlots()) {
      const lostAt = room.lost[slot];
      if (lostAt && now - lostAt >= GRACE_MS - 100) {
        this.broadcast(slot, { type: "_peer_gone", slot });
        for (const s of this.ctx.getWebSockets(slot)) {
          try { s.close(1000, "peer gone"); } catch { /* already closed */ }
        }
        delete room.lost[slot];
        if (slot === "host") {
          // No host, no match - end it for everyone still here.
          for (const other of this.allSlots()) {
            if (other === "host") continue;
            for (const s of this.ctx.getWebSockets(other)) {
              try { s.close(1000, "host gone"); } catch { /* already closed */ }
            }
          }
          await this.ctx.storage.deleteAll();
          return;
        }
        delete room.guests[slot];
        await this.ctx.storage.put("room", room);
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
