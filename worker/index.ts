// Cloudflare entry point: one Worker serving both halves of FalloutCast.
//
// `/api/*` is proxied to the FastAPI container (the real Python app, running
// unmodified from the repo's Dockerfile -- numpy/scipy/contourpy included).
// Everything else is served from the built frontend in web/dist.
//
// One origin for both is deliberate: it means the browser never makes a
// cross-origin request, so there is no CORS preflight on every compute and no
// second hostname to keep in sync when either half moves. The frontend is
// built with FALLOUTCAST_API_URL=/api to match (see DEPLOY.md).

import { Container, getContainer } from "@cloudflare/containers";

export class FalloutcastApi extends Container<Env> {
  // Must match the port uvicorn binds in the Dockerfile.
  defaultPort = 8010;
  // Containers bill for the time they're awake, so idle instances should stop.
  // 10 minutes is long enough that a session of tweaking a scenario keeps
  // hitting a warm instance (a cold start pays for the Python + numpy/scipy
  // import), and short enough that a forgotten tab doesn't bill all day.
  sleepAfter = "10m";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      // Strip the /api prefix: the FastAPI app owns routes at the root
      // (/plume, /ensemble, /exchange/envelope, ...), and rewriting here keeps
      // the API's own route definitions and docs unchanged.
      const target = new URL(request.url);
      target.pathname = url.pathname.slice("/api".length) || "/";
      return getContainer(env.FALLOUTCAST_API).fetch(new Request(target, request));
    }

    // Static assets. Cloudflare serves these from its edge cache without
    // spinning up the container, so browsing the app costs nothing until an
    // actual compute is requested.
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
