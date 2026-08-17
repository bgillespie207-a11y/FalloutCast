# FalloutCast API container (Cloudflare Containers / any Docker host).
#
# linux/amd64 is pinned because Cloudflare's container runtime is amd64 and
# this repo is developed on an arm64 Mac -- without it, `wrangler deploy` from
# an Apple Silicon machine builds an arm64 image that fails to start in the
# cloud, with the failure only surfacing at runtime.
#
# Measured on the real endpoints (2026-08-17): 72 MB peak RSS during the
# heaviest request (sum envelope, 600 targets on one national grid) and ~1.2 s
# of CPU warm. The `basic` instance type (1 GiB / 0.25 vCPU) has ~14x the
# memory headroom needed; see wrangler.jsonc.
FROM --platform=linux/amd64 python:3.12-slim

# PYTHONUNBUFFERED so uvicorn's logs reach `wrangler tail` immediately rather
# than sitting in a block buffer.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency install is its own layer, keyed on pyproject.toml alone, so
# editing src/ doesn't re-resolve and re-download numpy/scipy every build.
# `pip install .` needs the package present, so this installs the declared
# dependencies first against a stub, then the package itself below.
COPY pyproject.toml ./
RUN python -c "import tomllib,pathlib,subprocess,sys; \
deps=tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['dependencies']; \
sys.exit(subprocess.call([sys.executable,'-m','pip','install',*deps]))"

COPY src ./src
RUN pip install --no-deps .

# The port the Worker's Container binding talks to (defaultPort in
# worker/index.ts). 0.0.0.0 is required: binding to localhost would leave the
# container unreachable from outside its own network namespace.
EXPOSE 8010
CMD ["uvicorn", "falloutcast.api.main:app", "--host", "0.0.0.0", "--port", "8010"]
