/// <reference types="vitest" />
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
  // Unit tests run against the same `define`s as the app, so modules that read
  // __APP_VERSION__ / __API_URL__ (report.ts, api.ts) need no test-only shim.
  // Node environment on purpose: everything under test is pure or fetch-based,
  // so there's no jsdom dependency to carry. Anything DOM-bound stays in
  // main.ts and is verified in the browser instead (house rule 4).
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
