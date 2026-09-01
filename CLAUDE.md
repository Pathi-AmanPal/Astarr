# Astarr — working notes for Claude

## State

Pre-build. This repo currently contains **only** a vendored skill library — no
application code, no framework chosen, no package.json. Do not scaffold an app unless
asked; the build starts after Figma verification.

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
- `PRODUCT.md` and `DESIGN.md` don't exist yet. `/impeccable init` writes the first.
