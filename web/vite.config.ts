import { defineConfig } from "vite";

// FALLOUTCAST_API_URL lets the built app point at a deployed API; local dev
// defaults to the uvicorn dev server's default port.
export default defineConfig({
  define: {
    __API_URL__: JSON.stringify(process.env.FALLOUTCAST_API_URL ?? "http://localhost:8010"),
  },
  server: {
    port: 5173,
  },
});
