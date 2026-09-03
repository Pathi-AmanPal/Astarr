# SAT-SA — offline deployment

One container, one port, one file to carry. The frontend is built into the image and
served by the same FastAPI process, so there is no reverse proxy to configure and
nothing is fetched at runtime.

## Build (needs network, once)

```
docker build -t sat-sa:offline .
docker save sat-sa:offline -o sat-sa-offline.tar     # ~239 MB — this is the deliverable
```

## Run on the air-gapped machine

```
docker load -i sat-sa-offline.tar
docker run -d --name satsa -p 8000:8000 -v satsa-data:/data sat-sa:offline
```

Open <http://localhost:8000>. The database is seeded and every finding recomputed on
first start; nothing needs to be loaded by hand.

## Two operational hazards, both found by testing

**DuckDB is single-writer. Never run two containers against the same volume.** The
second one exits immediately with `Could not set lock on file "/data/sat_sa.duckdb"`.
If a container seems dead on arrival, check for an older one still holding the volume:

```
docker ps -a --filter ancestor=sat-sa:offline
docker rm -f <the stale one>
```

**Findings are not recomputed when rules change.** Startup seeds only when the database
is *empty*, so a container reusing an existing `satsa-data` volume after a rules change
will serve findings computed by the previous version — silently, with no error. After
changing any rule, weight or threshold, either:

```
curl -X POST http://localhost:8000/api/demo/reset      # recompute in place
docker volume rm satsa-data                            # or start clean
```

This bit during verification: the development server served the pre-amendment NS-001
wording for a full session because its database predated the change.

## Verifying an offline claim honestly

Running in Docker proves nothing on its own. What was actually tested:

1. **Egress denied and proven denied.** An `--internal` Docker network gives the
   container no route off the host, and connections to `1.1.1.1:53`, `8.8.8.8:53`,
   `pypi.org:443` and `registry-1.docker.io:443` are attempted from inside and asserted
   to **fail**. If any succeeded the offline claim would be void.
2. **Air-gap transfer simulated.** The image is `docker save`d, then `docker rmi` and
   `docker image prune` remove every local trace, then it is restored from the tar
   alone. Without the removal step you are re-running a cached image and proving
   nothing.
3. **Full verification inside the offline container.** `python verify.py` runs in the
   container with zero egress: 78 checks, 0 failures, output byte-identical to the host
   (7256 bytes each).
4. **Identical API responses.** `/api/entities` and every entity detail endpoint match
   the host byte for byte, including the SHAP-derived ML-001 explanation — confirming
   the container uses real SHAP rather than silently degrading to the z-score fallback,
   which would have changed the finding text.

```
docker network create --internal satsa-offline
docker run --rm --network satsa-offline -e SATSA_DB=/tmp/v.duckdb sat-sa:offline python verify.py
```

Note `--internal` blocks published ports on Docker Desktop, so the zero-egress run is
not reachable from the host. Reachability is tested separately on a normal bridge —
which is also the real deployment shape, since on an air-gapped machine it is the
*machine* that has no internet, not the container.

**Check what answered.** During testing a stray development server on port 8000 returned
`HTTP 200` for `/api/health` and was briefly mistaken for the container. The container
serves the SPA at `/`; a bare API server returns 404 there. `docker port <name>` shows
what is actually published.

## Image

- `python:3.14-slim`, non-root (uid 10001), `TZ=UTC` fixed — EG-005 buckets closures by
  minute, so a host timezone shift could otherwise alter findings.
- Every dependency installs from a prebuilt manylinux wheel; `--only-binary=:all:` makes
  a missing wheel a hard build failure rather than a silent source build. No compiler is
  present in the runtime image.
- `~1.06 GB` image / `~239 MB` tar. `sat_sa.duckdb`, `venv/`, `node_modules/` and
  `dist/` are excluded via `.dockerignore`; the database lives on the `/data` volume
  because it is state, not content.
