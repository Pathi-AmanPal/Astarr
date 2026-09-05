# SAT-SA — Supervisory Analytics Tool for SOC Assessment

A supervisory audit tool that assesses **the quality of a SOC's work**, not the volume
of it. It reads closed alert records from monitored entities and surfaces two things a
throughput dashboard cannot:

- **Execution Gaps** — work that was done badly. Critical alerts closed in under two
  minutes with nobody escalated, serious alerts dismissed with no written justification,
  identical copy-pasted investigation notes, twenty alerts closed in the same minute.
- **Negative Space** — work that was never done at all. An entity reporting far fewer
  alerts than its peers, or reporting nothing in a threat category almost everyone else
  reports. Absence is evidence, and it is invisible to any tool that only counts what
  was submitted.

Every finding carries the exact records it was derived from. Every risk score decomposes
into arithmetic a reviewer can foot by hand. Nothing is a black box.

Built for the NCIIPC problem statement (Smart India Hackathon 2025).

---

## Setup

First time on a machine. Two terminals. No API keys, no internet, no cloud services.

```bash
# terminal 1 — backend
cd backend
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source venv/bin/activate && pip install -r requirements.txt  # macOS / Linux

# terminal 2 — frontend
cd frontend
npm install
```

Requires **Python 3.11+** and **Node 18+**. Both installs need network access once;
nothing after this point does.

## Running the demo

Once the dependencies above are installed, this is the whole thing — two commands, two
terminals, exactly as used for the acceptance run:

```bash
# terminal 1 — backend on :8000
cd backend && ./venv/Scripts/python.exe -m uvicorn main:app --reload

# terminal 2 — frontend on :5173
cd frontend && npm run dev
```

Then open **<http://localhost:5173>**.

The database seeds itself and every finding is recomputed on first start — there is no
manual load step. On macOS/Linux the backend line is
`cd backend && ./venv/bin/python -m uvicorn main:app --reload`.

The live demo runs on these dev servers, **not** on the container below. Both default to
port 8000, so do not run them at the same time.

## Running the offline container

The container is the air-gapped **deployment artifact**, built and verified separately
from the demo. The frontend is compiled into the image and served by the same FastAPI
process, so there is one port and nothing is fetched at runtime.

```bash
# on a machine with network, once
docker build -t sat-sa:offline .
docker save sat-sa:offline -o sat-sa-offline.tar     # ~239 MB — this is the deliverable

# on the air-gapped machine
docker load -i sat-sa-offline.tar
docker run -d --name satsa -p 8000:8000 -v satsa-data:/data sat-sa:offline
```

Then open **<http://localhost:8000>** — the container serves both the app and the API
there. **Publish it on port 8000 specifically:** the frontend resolves the API at
`http://localhost:8000` by name (`frontend/src/api.ts`), so on any other host port the
page loads and the data never arrives.

**[DEPLOYMENT.md](DEPLOYMENT.md)** covers the rest: how the zero-egress claim was actually
tested, the DuckDB single-writer hazard, and why a container reusing an old volume can
silently serve findings from a previous version of a rule.

---

## Verifying it

The tool is only worth as much as its claims, so the claims are testable:

```bash
cd backend && ./venv/Scripts/python.exe verify.py
```

This seeds a throwaway database, runs the full detection pipeline and asserts every
rule fires **exactly where it was planted and nowhere else** — the score vector, the
ranking order, the evidence behind each finding, and that two independent builds produce
identical results. It ends with `All checks passed.` or exits non-zero.

It also **proves the negative** where a guard exists: it disables the peer-cohort
validity gate and asserts the rule goes silent, demonstrating that the gate is load
bearing rather than decorative.

Run it after touching any rule, weight or threshold.

> **Findings are not recomputed when rules change.** Startup seeds only when the
> database is empty, so a running server will keep serving findings from the previous
> version of a rule — silently. After changing anything, `POST /api/demo/reset` or
> delete `backend/sat_sa.duckdb`.

---

## How scoring works

Each finding carries a weight. Weights are summed **per tier**, each tier is capped at
100 **individually**, then combined:

```
EG = MIN(100, SUM(EXECUTION_GAP    weights))
NS = MIN(100, SUM(NEGATIVE_SPACE   weights))
ML = MIN(100, SUM(ML_CORROBORATION weights))

risk_score = 0.45·EG + 0.40·NS + 0.15·ML
```

No outer cap is applied and none is needed: the three weights sum to exactly 1.00, so
the result is a convex combination of three values each ≤ 100. That invariant is
asserted at startup and again, independently, in `verify.py`.

The entity detail screen shows this as a footable table — raw sum → individual cap →
× weight → contribution → total.

---

## Honest limitations

Stated here because a limitation you can defend is worth more than a claim you cannot:

- **The score's attainable maximum is 86.5, not 100.** The ML tier cannot exceed 10, so
  a perfect 100 is unreachable. It is a **comparable ranking scale, not a percentage** —
  do not read "56.50" as "56% risk".
- **Peer-cohort comparison is gated, and currently inactive.** A cohort is used only
  when it has ≥ 5 members. The demo dataset has 12 entities across 12 *distinct*
  sectors, so every cohort has one member and all of them fall back to the global
  baseline — which each finding says, in words. Cohorting activates by itself as the
  data grows. A cohort of one has no spread, and a threshold drawn from it would be
  arithmetic dressed up as evidence.
- **The ML layer has never been validated or measured for accuracy.** The Isolation
  Forest is a *corroborating* signal only: it is evaluated exclusively for entities the
  deterministic rules already flagged, carries the smallest weight in the system, and
  can never originate a finding.
- **CSV upload is live; other formats are not.** `POST /api/dataset/upload` takes a CSV
  alert export, validates it and recomputes every finding and score over it — the demo
  seed stays the default and one button restores it. Validation rejects rather than
  repairs: a malformed file is refused with a line-numbered list of problems and the
  previous dataset stays in place. JSON, database-export and API ingestion remain
  unbuilt; the schema is format-agnostic and derives `closure_time_minutes` at load
  time, which is the seam those loaders plug into. The original decision to ship no
  upload path — and why the regression coverage added on 2026-09-05 withdrew it — is
  recorded in [PRODUCT.md](PRODUCT.md) and PRD §9.
- **The dataset is synthetic.** No real SOC data, no real entity, no customer.

---

## Layout

```
backend/
  main.py        FastAPI app + API (also serves the built SPA in the container)
  detection.py   the seven rules (EG-001..005, NS-001/002)
  scoring.py     weighted-tier risk scoring
  ml.py          ML-001 Isolation Forest corroboration, gated
  rules.yaml     every weight, threshold and condition — no defaults in code
  config.py      config loader; a missing key raises at startup, never defaults
  seed.py        the synthetic dataset, with each rule's trigger deliberately planted
  verify.py      the regression suite
frontend/src/    React + Vite: entity list, entity detail, evidence view
docs/            PRD and the skill index
Dockerfile       the offline image; frontend is built in and served by FastAPI
DEPLOYMENT.md    offline/air-gapped deployment and its operational hazards
PRODUCT.md       product record, including every amendment made during the build
DESIGN.md        the visual system — tokens, type, layout, components
```

---

## Design skill library

This repo also carries a vendored design + motion skill library for Claude Code (26
skills, 4 agents), used while building the frontend. It is independent of the
application.

```bash
./scripts/install-skills.sh          # run once after cloning
./scripts/install-skills.sh --global # or install into ~/.claude for every project
```

Impeccable's scripts resolve through `.agent/skills/impeccable`, a symlink to
`.claude/skills/impeccable`. Git for Windows checks symlinks out as plain files unless
`core.symlinks` is enabled, which breaks every Impeccable command; the install script
detects that and repairs the link. It verifies the link's *target*, not just that
something exists there — a link pointing at the wrong place, or a directory copy left
behind by a fallback, is repaired rather than reported as fine.

See **[docs/skills/README.md](docs/skills/README.md)** for the full index, and
`./scripts/update-skills.sh --latest` to re-sync from upstream (this overwrites local
edits — diff first).

## Licenses

Skills stay under their upstream licenses (MIT, Apache-2.0) — see
[`docs/skills/licenses/`](docs/skills/licenses) and `skills-manifest.json`.
This repo's own code is under [LICENSE](LICENSE).
