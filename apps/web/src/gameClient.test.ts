import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actionId } from "./gameClient";

it('keeps player and spectator reconnect identities separate', async () => {
  const data = new Map<string, string>();
  vi.stubGlobal('localStorage', {getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => data.set(key, value), removeItem: (key: string) => data.delete(key)});
  try {
    const {saveSession, loadSession, clearSession} = await import('./gameClient');
    saveSession({roomId: 'TEST', playerId: 'player', playerName: 'A', reconnectToken: 'player-token'});
    saveSession({roomId: 'TEST', playerId: 'watcher', playerName: 'A', reconnectToken: 'watcher-token', role: 'spectator'});
    expect(loadSession('TEST')?.playerId).toBe('player');
    expect(loadSession('TEST', 'spectator')?.playerId).toBe('watcher');
    expect(loadSession('OTHER', 'spectator')).toBeNull();
    clearSession('spectator');
    expect(loadSession('TEST', 'spectator')).toBeNull();
    expect(loadSession('TEST')?.playerId).toBe('player');
  } finally { vi.unstubAllGlobals(); }
});

it("generates unique UUIDs on HTTP without crypto.randomUUID", () => {
  vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto) });
  try {
    const ids = Array.from({ length: 100 }, actionId);
    expect(new Set(ids).size).toBe(100);
    for (const id of ids) expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  } finally {
    vi.unstubAllGlobals();
  }
});

describe("room routing", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: {
        hash: "#/room/aBcD",
        origin: "https://xeonliu.github.io",
        protocol: "https:",
      },
    });
  });

  it("reads room IDs from the Pages hash route", async () => {
    const { roomFromPath } = await import("./gameClient");
    expect(roomFromPath()).toBe("ABCD");
  });
});

it("ignores socket events after cancelling or replacing a connection", async () => {
  const sockets: MockSocket[] = [];
  class MockSocket extends EventTarget {
    static OPEN = 1;
    readyState = 1;
    send = vi.fn();
    close = vi.fn();
    constructor(_url: string) { super(); sockets.push(this); }
  }
  vi.stubGlobal("WebSocket", MockSocket);
  const { GameClient } = await import("./gameClient");
  const client = new GameClient();
  const message = vi.fn();
  const status = vi.fn();
  const intent = { type: "JOIN_ROOM" as const, roomId: "ABCD", playerName: "Alice" };
  try {
    client.connect(intent, message, status);
    client.close();
    sockets[0].dispatchEvent(new Event("open"));
    sockets[0].dispatchEvent(new MessageEvent("message", { data: '{"type":"ROOM_LEFT"}' }));
    expect(sockets[0].send).not.toHaveBeenCalled();
    expect(message).not.toHaveBeenCalled();
    client.connect(intent, message, status);
    sockets[1].dispatchEvent(new Event("open"));
    sockets[0].dispatchEvent(new Event("close"));
    expect(status).toHaveBeenLastCalledWith("connecting");
    expect(sockets[1].send).toHaveBeenCalledWith(JSON.stringify(intent));
  } finally {
    client.close();
    vi.unstubAllGlobals();
  }
});

describe("joining a room over an unreliable connection", () => {
  class MockSocket extends EventTarget {
    static OPEN = 1;
    readyState = 0;
    send = vi.fn();
    close = vi.fn();
    constructor(_url: string) { super(); sockets.push(this); }
    open() { this.readyState = 1; this.dispatchEvent(new Event("open")); }
    receive(message: object) { this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(message) })); }
  }
  const sockets: MockSocket[] = [];
  const intent = { type: "JOIN_ROOM" as const, roomId: "ABCD", playerName: "Alice" };
  let client: import("./gameClient").GameClient;
  const message = vi.fn();
  const status = vi.fn();

  beforeEach(async () => {
    vi.useFakeTimers();
    sockets.length = 0;
    message.mockClear(); status.mockClear();
    vi.stubGlobal("window", {location: {origin: "http://localhost:5173", protocol: "http:"}});
    vi.stubGlobal("WebSocket", MockSocket);
    const { GameClient } = await import("./gameClient");
    client = new GameClient();
  });
  afterEach(() => { client.close(); vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("allows retry when the transport handshake never completes", () => {
    client.connect(intent, message, status);
    vi.advanceTimersByTime(15000);
    expect(status).toHaveBeenLastCalledWith("disconnected");
    expect(message).toHaveBeenCalledWith(expect.objectContaining({type:"ERROR", code:"CONNECTION_TIMEOUT"}));
    expect(sockets[0].close).toHaveBeenCalledTimes(1);
    sockets[0].open();
    expect(sockets[0].send).not.toHaveBeenCalled();
  });

  it("also times out an open socket that never receives the room welcome", () => {
    client.connect(intent, message, status);
    sockets[0].open();
    expect(status).toHaveBeenLastCalledWith("connecting");
    vi.advanceTimersByTime(15000);
    expect(message).toHaveBeenCalledWith(expect.objectContaining({code:"CONNECTION_TIMEOUT"}));
    expect(status).toHaveBeenLastCalledWith("disconnected");
  });

  it("stops the timeout only after the welcome and leaves an active room connected", () => {
    client.connect(intent, message, status);
    sockets[0].open();
    vi.advanceTimersByTime(14900);
    sockets[0].receive({type:"WELCOME"});
    vi.advanceTimersByTime(60000);
    expect(status).toHaveBeenLastCalledWith("connected");
    expect(message).toHaveBeenCalledTimes(1);
    expect(sockets[0].close).not.toHaveBeenCalled();
    sockets[0].dispatchEvent(new Event("close"));
    expect(status).toHaveBeenLastCalledWith("disconnected");
    expect(message).toHaveBeenCalledTimes(1);
  });

  it("keeps the server's reason when joining is rejected", () => {
    client.connect(intent, message, status);
    sockets[0].open();
    const rejection = {type:"ERROR", code:"ROOM_NOT_FOUND", message:"Room not found"};
    sockets[0].receive(rejection);
    sockets[0].dispatchEvent(new Event("close"));
    vi.advanceTimersByTime(16000);
    expect(message).toHaveBeenCalledTimes(1);
    expect(message).toHaveBeenCalledWith(rejection);
    expect(status).toHaveBeenLastCalledWith("disconnected");
  });

  it("reports a socket failure once and allows a new connection", () => {
    client.connect(intent, message, status);
    sockets[0].dispatchEvent(new Event("error"));
    sockets[0].dispatchEvent(new Event("close"));
    expect(message).toHaveBeenCalledTimes(1);
    expect(message).toHaveBeenCalledWith(expect.objectContaining({code:"CONNECTION_FAILED"}));
    client.connect(intent, message, status);
    sockets[1].open(); sockets[1].receive({type:"WELCOME"});
    expect(status).toHaveBeenLastCalledWith("connected");
  });

  it("silently cancels old deadlines and ignores late replies after replacement", () => {
    client.connect(intent, message, status);
    vi.advanceTimersByTime(5000);
    client.connect(intent, message, status);
    sockets[1].open(); sockets[1].receive({type:"WELCOME"});
    sockets[0].receive({type:"WELCOME"});
    sockets[0].dispatchEvent(new Event("error"));
    vi.advanceTimersByTime(30000);
    expect(message).toHaveBeenCalledTimes(1);
    expect(status).toHaveBeenLastCalledWith("connected");
    client.close();
    sockets[1].dispatchEvent(new Event("close"));
    expect(message).toHaveBeenCalledTimes(1);
  });

  it("recovers when the browser refuses to construct a socket", () => {
    vi.stubGlobal("WebSocket", class { constructor() { throw new Error("Blocked connection"); } });
    expect(() => client.connect(intent, message, status)).not.toThrow();
    expect(status).toHaveBeenLastCalledWith("disconnected");
    expect(message).toHaveBeenCalledWith(expect.objectContaining({code:"CONNECTION_FAILED"}));
  });
});
