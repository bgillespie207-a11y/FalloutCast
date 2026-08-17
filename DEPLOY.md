# Deploying FalloutCast to Cloudflare

One Worker serves the whole app:

```
  browser
     |
     |  https://falloutcast.<subdomain>.workers.dev
     v
  Worker (worker/index.ts)
     |-- /api/*  --> Container: the FastAPI app, unmodified, from ./Dockerfile
     `-- else    --> Static assets: the built frontend in web/dist
```

Both halves share one origin, so the browser never makes a cross-origin
request: no CORS preflight on every compute, and no second hostname to keep in
sync. The frontend is built with `FALLOUTCAST_API_URL=/api` to match — that's
what `npm run build:web` does.

## Why Containers and not a Python Worker

The API needs `numpy`, `scipy` and `contourpy` — compiled packages — and a
national envelope makes **111 outbound wind fetches** (600 targets bucketed
into ~1° cells). Cloudflare Workers' free plan allows **50 subrequests and
10 ms of CPU** per request, so the envelope cannot run there at all, before
even asking whether scipy runs under Pyodide. Containers run the real image, so
the Python code is deployed unchanged.

## Prerequisites

1. **Workers Paid plan ($5/month).** Containers are not on the free tier.
   Enable it at Cloudflare dashboard → Workers & Pages → Plans. **You have to
   do this yourself** — it is a purchase.
2. **Docker with buildx.** `wrangler` builds the image locally and pushes it.
   This repo was set up against Colima:
   ```bash
   colima start
   docker buildx version   # must print a version, not an error
   ```
   If buildx is missing: `brew install docker-buildx` and link it:
   ```bash
   mkdir -p ~/.docker/cli-plugins
   ln -sfn "$(brew --prefix)/opt/docker-buildx/bin/docker-buildx" ~/.docker/cli-plugins/docker-buildx
   ```
3. **An authenticated wrangler.** `npx wrangler login` opens a browser for
   OAuth — being signed in to the dashboard is not enough, the CLI needs its
   own token.

## Deploy

```bash
npm install          # once: wrangler + @cloudflare/containers
npx wrangler login   # once
npm run deploy       # builds web/dist + typechecks the Worker, then deploys
```

`npm run deploy` runs `npm run check` first, so a broken frontend build or a
Worker type error stops the deploy rather than shipping.

The first deploy builds and uploads the ~489 MB image and takes several
minutes; later deploys reuse cached layers. On Apple Silicon the image is built
for `linux/amd64` (pinned in the Dockerfile) under emulation — correct, but
slow. Watch it with `npm run tail`.

## After deploying

Check these in order — each isolates a different half:

```bash
curl https://<your-worker-url>/api/health          # container is up
curl -s https://<your-worker-url>/ | head -5       # static assets serve
```

Then open the app and run one single-location compute and one national
envelope. The envelope is the endpoint that exercises everything: 111 wind
fetches, the 600-target grid, and the contour pipeline.

## Sizing and cost

`instance_type: "basic"` (1 GiB / 0.25 vCPU) is set from measurement, not
guesswork — the heaviest endpoint (sum envelope, 600 targets) peaks at **72 MB
RSS** and about **1.2 s of CPU** warm. That leaves ~14x memory headroom.

Containers bill for the time an instance is awake, and `sleepAfter = "10m"`
(worker/index.ts) stops it when idle. The Workers Paid plan's included
container usage works out to roughly **25 awake-hours/month** at this instance
size, which is generous for personal use — you pay per idle-timeout window, not
per request.

If the national envelope feels slow, raise `instance_type` to `standard-1` in
`wrangler.jsonc`. That doubles CPU but also quadruples the memory rate, so it
cuts the included awake-hours to about a quarter. Single plumes are dominated
by their one wind fetch and won't change.

## What was verified locally, and what wasn't

Verified against the real `linux/amd64` image:

- every compute path — Tier-0, Tier-1, ensemble (scipy), the 600-target
  envelope, `/targets`, `/deck`;
- the production frontend bundle (built with `/api`) driving that container
  through a stand-in that mirrors the Worker's routing;
- static assets and the SPA fallback served by the Worker itself.

**Not verified locally: the Worker → container hop.** `wrangler dev` reaches
containers by their Docker-network IP, which macOS cannot route into a Colima
VM, so the request hangs and the container is eventually SIGTERM'd (exit 143).
This is a local-tooling gap — Cloudflare's runtime doesn't use that path — but
it does mean **the first real deploy is the first test of that hop**. Check
`/api/health` immediately after deploying. With Docker Desktop instead of
Colima, `wrangler dev` should work locally.

## Gotchas

- **Rerun `npx wrangler types` after editing `wrangler.jsonc`.** It regenerates
  `worker-configuration.d.ts`, which declares `Env` (the `ASSETS` and
  `FALLOUTCAST_API` bindings). It is gitignored on purpose — it pins a workerd
  version that churns on every wrangler bump.
- **The target deck is package data** (`src/falloutcast/data/`), shipped via
  `[tool.setuptools.package-data]`. It used to live at the repo root and be
  found by walking up from `__file__`, which worked only in a source checkout —
  the installed package raised `FileNotFoundError` on every deck-backed
  endpoint. `tests/test_packaging.py` guards this; don't move it back out.
- **The image is pinned to `linux/amd64`** in the Dockerfile. Without that pin,
  building on an arm64 Mac produces an image that fails to start in the cloud,
  and the failure only shows at runtime.
