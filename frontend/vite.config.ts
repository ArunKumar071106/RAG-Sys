/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Without VITE_API_BASE_URL the app calls /api on this server; forward it to the backend.
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_PROXY ?? "http://127.0.0.1:8000",
        // Backend not listening yet (still starting): answer like the API does while it starts.
        configure: (proxy) => {
          proxy.on("error", (_err, _req, res) => {
            if (!("writeHead" in res) || res.headersSent) return;
            res.writeHead(503, { "Content-Type": "application/json", "Retry-After": "30" });
            res.end(JSON.stringify({ detail: "The backend is not reachable yet - is it running?" }));
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: true,
  },
});
