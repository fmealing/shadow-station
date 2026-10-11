import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run dev` serves the UI with hot reload on :5173 and passes the
// WebSocket through to the station, which must be running (on :8765).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/ws": { target: "ws://127.0.0.1:8765", ws: true } },
  },
});
