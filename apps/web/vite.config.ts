import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  if (mode === "production") {
    const origin = env.VITE_API_ORIGIN;
    let parsed: URL;
    try {
      parsed = new URL(origin);
    } catch {
      throw new Error("VITE_API_ORIGIN is required and must be an absolute URL for production builds");
    }
    if (parsed.protocol !== "https:" || parsed.origin !== origin) {
      throw new Error("VITE_API_ORIGIN must be an HTTPS origin without a path");
    }
  }
  return {
    base: "/MagicalAthleteOL/",
    plugins: [react(), {
      name: "room-preview-socket-errors",
      configureServer(server) {
        // Attach before HMR/proxy upgrade handlers: a phone can reset its socket
        // while the handshake is pending, before either handler owns the socket.
        server.httpServer?.prependListener("upgrade", (_request, socket) => {
          socket.on("error", () => socket.destroy());
        });
      },
    }],
    server: {
      proxy: {
        "/api": "http://localhost:8000",
        "/ws": {
          target: "ws://localhost:8000",
          ws: true,
        },
      },
    },
  };
});
