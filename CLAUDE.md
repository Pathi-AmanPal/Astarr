# Astarr — working notes for Claude

## State

**Built.** SAT-SA (Supervisory Analytics Tool for SOC Assessment) is a working
FastAPI + DuckDB + React app. Two branches matter:

- `claude/download-integrate-skills-2uy967` — **the Sept 15 demo branch. Frozen.**
  Verified Phase 1 at commit `296c5ab`: additive scoring, 46 checks passing. Do not
  commit here without being asked explicitly.
- `phase-2-full-scope` — active development. Weighted-tier scoring, YAML-configured
  rules, gated peer-cohort baseline, offline Docker packaging.

`cd backend && ./venv/Scripts/python.exe verify.py` is the regression suite and the
first thing to run after touching any rule, weight or threshold. It must end
`All checks passed.` — currently 78 checks on `phase-2-full-scope`.

**Demo environment is the dev servers** (`uvicorn main:app --reload` + `npm run dev`),
not the container. The Docker image is the offline-deployment *submission artifact*;
keep the two separate, and mind that both default to port 8000.

## Working style this project expects

Established over the Phase 2 build and worth keeping:

- **Propose numbers before implementing.** Any change to a rule, weight, threshold or
  formula gets its recomputed values shown and confirmed first.
- **Prove behaviour is unchanged, don't assert it.** The standard is a byte-for-byte
  diff of the full findings dump (all 18 findings, weights, explanations, evidence ids)
  plus the ranked entity list, before and after.
- **State consequences rather than letting them surface on stage.** A ranking change or
  a reworded finding is fine; an unannounced one is not.
- **Claim exactly what is implemented.** Amendments are recorded in `PRODUCT.md` and the
  PRD with the superseded text *struck, not deleted*. Docs and UI copy must never
  outrun the code — a stale claim on screen is a demo failure.
- **Prove the negative.** Where a guard exists, disable it in a test and assert the bad
  outcome really happens (e.g. `verify.py` disables the NS-001 cohort gate and confirms
  the rule goes silent).

## Skills

26 skills are vendored under `.claude/skills/`, from three upstreams
(`skills-manifest.json` has the pins). Full index with routing advice:
[`docs/skills/README.md`](docs/skills/README.md).

- **Impeccable** (`/impeccable <command> <target>`) — the heavyweight design system.
  Its scripts resolve through `.agent/skills/impeccable` (a symlink to
  `.claude/skills/impeccable`). Run
  `node .claude/skills/impeccable/scripts/context.mjs` once per session before
  design work, keeping cwd at the project root.
- **taste-skill family** — visual direction and anti-generic frontend. Directory names
  and frontmatter `name:` differ; invoke by the frontmatter name.
- **emilkowalski** — motion, craft, component polish, Swift.

## Rules for this repo

- Vendored skill files under `.claude/skills/` are upstream code. Change them only when
  asked, and note it — `./scripts/update-skills.sh` overwrites local edits.
- `.agent/skills/impeccable` must stay a symlink; several `allowed-tools` entries and
  script paths depend on it. If it ever shows up as a plain file (a Windows checkout
  without `core.symlinks`), run `./scripts/install-skills.sh` to repair it rather than
  editing it by hand.
- Impeccable's hooks are opt-in (`.claude/settings.impeccable-hooks.json`), not active.
  Don't enable them without asking — they run on every Edit/Write.
- `PRODUCT.md` is the product record, including every Phase 2 amendment. Read it before
  changing product behaviour. `DESIGN.md` is the *current* visual direction (dark
  instrument face, rebuilt 2026-09-06); the retired v1 audit-paper direction is archived
  at `docs/design/v1-audit-working-paper.md`. An earlier version of this file claimed
  DESIGN.md did not exist -- it did, and acting on that nearly lost it.
- Rule weights, thresholds and tier weights live in `backend/rules.yaml`, never in code.
  The loader has no defaults — a missing key raises at startup on purpose.
- Findings are **not** recomputed when rules change: startup seeds only when the
  database is empty. After changing a rule, `POST /api/demo/reset` or the server keeps
  serving findings from the previous version, silently. This has already caused a
  session of testing against stale text.
- `DEPLOYMENT.md` covers the offline/air-gapped build and its operational hazards.
