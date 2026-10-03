import i18n from "./i18n";
import type { ClientIntent, ServerMessage } from "./protocol";
import { websocketUrl } from "./runtimeConfig";

export interface SessionIdentity {
  roomId: string;
  playerId: string;
  reconnectToken: string;
  playerName: string;
  role?: "player" | "spectator";
}

const storageKey = "magical-athlete-session";

export function loadSession(roomId: string, role: "player" | "spectator" = "player"): SessionIdentity | null {
  const value = localStorage.getItem(role === "spectator" ? `${storageKey}-spectator` : storageKey);
  if (!value) return null;
  try {
    const session = JSON.parse(value) as SessionIdentity;
    return session.roomId === roomId && (session.role ?? "player") === role ? session : null;
  } catch {
    return null;
  }
}

export function saveSession(session: SessionIdentity): void {
  localStorage.setItem(session.role === "spectator" ? `${storageKey}-spectator` : storageKey, JSON.stringify(session));
}

export function clearSession(role: "player" | "spectator" = "player"): void {
  localStorage.removeItem(role === "spectator" ? `${storageKey}-spectator` : storageKey);
}

export function roomFromPath(): string {
  const match = window.location.hash.match(/^#\/room\/([A-Za-z]{4,8})\/?$/);
  return match?.[1]?.toUpperCase() ?? "";
}

export function actionId(): string {
  // randomUUID is restricted to secure contexts; getRandomValues also works over HTTP.
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export class GameClient {
  private socket: WebSocket | null = null;
  private joinTimeout: ReturnType<typeof setTimeout> | null = null;

  connect(
    intent: Extract<ClientIntent, { type: "JOIN_ROOM" }>,
    onMessage: (message: ServerMessage) => void,
    onStatus: (status: "connecting" | "connected" | "disconnected") => void,
  ): void {
    this.close();
    onStatus("connecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(websocketUrl(intent.roomId));
    } catch {
      onStatus("disconnected");
      onMessage({ type: "ERROR", code: "CONNECTION_FAILED", message: i18n.t("errors.network") });
      return;
    }
    this.socket = socket;
    let welcomed = false;
    const fail = (code: "CONNECTION_FAILED" | "CONNECTION_TIMEOUT") => {
      if (this.socket !== socket) return;
      this.close();
      onStatus("disconnected");
      onMessage({ type: "ERROR", code, message: i18n.t(code === "CONNECTION_TIMEOUT" ? "errors.connectionTimeout" : "errors.network") });
    };
    // A successful transport handshake still needs the room's WELCOME reply.
    this.joinTimeout = setTimeout(() => fail("CONNECTION_TIMEOUT"), 15000);
    socket.addEventListener("open", () => {
      if (this.socket !== socket) return;
      this.send(intent);
    });
    socket.addEventListener("message", (event) => {
      if (this.socket !== socket) return;
      const message = JSON.parse(event.data) as ServerMessage;
      if (message.type === "WELCOME") {
        welcomed = true;
        this.clearJoinTimeout();
        onStatus("connected");
      } else if (!welcomed && message.type === "ERROR") {
        this.close();
        onStatus("disconnected");
      }
      onMessage(message);
    });
    socket.addEventListener("error", () => fail("CONNECTION_FAILED"));
    socket.addEventListener("close", () => {
      if (this.socket !== socket) return;
      if (!welcomed) return fail("CONNECTION_FAILED");
      this.close();
      onStatus("disconnected");
    });
  }

  send(intent: ClientIntent): void {
    if (this.socket?.readyState !== WebSocket.OPEN) {
      throw new Error(i18n.t("app:errors.notConnected"));
    }
    this.socket.send(JSON.stringify(intent));
  }

  close(): void {
    this.clearJoinTimeout();
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  }

  private clearJoinTimeout(): void {
    if (this.joinTimeout !== null) clearTimeout(this.joinTimeout);
    this.joinTimeout = null;
  }
}
