import { defineConfig } from "vite";

import pkg from "./package.json";

// FALLOUTCAST_API_URL lets the built app point at a deployed API; local dev
// defaults to the uvicorn dev server's default port.
export default defineConfig({
  define: {
    __API_URL__: JSON.stringify(process.env.FALLOUTCAST_API_URL ?? "http://localhost:8010"),
    // App version (from package.json) stamped into exported reports/metadata.
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    port: 5173,
  },
});
