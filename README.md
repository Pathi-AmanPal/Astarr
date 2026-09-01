# Astarr

Hackathon workspace, pre-loaded with a design + motion skill library for AI-assisted
frontend work. **No application code yet** — that starts after the Figma education
account is verified.

## What's in here right now

```
.claude/
  skills/          26 vendored agent skills (design, motion, image-gen, craft)
  agents/          4 Impeccable subagents
  settings.json    pre-approved Bash permissions for the skill scripts
  settings.impeccable-hooks.json   opt-in design-detector hooks
.agent/skills/impeccable   symlink Impeccable's scripts expect
docs/skills/README.md      the skill index — start here
scripts/install-skills.sh  post-clone setup (+ --global for all projects)
scripts/install-skills.ps1 the same, for Windows
scripts/update-skills.sh   re-sync skills from upstream
skills-manifest.json       source repos + pinned commits + licenses
```

Skills load automatically in Claude Code from `.claude/skills/`. Nothing to install,
no dependencies, no API keys. Node 22+ is only needed for Impeccable's detector
scripts.

## Quick start

```bash
git clone https://github.com/Pathi-AmanPal/Astarr.git && cd Astarr
./scripts/install-skills.sh     # run once after cloning
claude                          # skills are discovered on launch
```

Windows (PowerShell):

```powershell
git clone https://github.com/Pathi-AmanPal/Astarr.git; cd Astarr
.\scripts\install-skills.ps1
claude
```

Type `/` in Claude Code and you should see `impeccable`, `taste-skill`, `animate`
and the rest. Then, once there's something to design:

```
/impeccable init        # records product truth in PRODUCT.md
```

### Why the install step

Impeccable's scripts resolve through `.agent/skills/impeccable`, a symlink to
`.claude/skills/impeccable`. Git for Windows checks symlinks out as plain text files
unless `core.symlinks` is enabled, which breaks every Impeccable command. The install
script detects that and recreates the link (a directory junction on Windows — no admin
rights needed). On macOS and Linux it's a no-op that confirms the link is intact.

### Using the skills in other projects

```bash
./scripts/install-skills.sh --global      # macOS / Linux / Git Bash
.\scripts\install-skills.ps1 -Global      # Windows
```

Copies all 26 skills and the 4 agents into `~/.claude/`, so they load in every project,
and pre-approves Impeccable's script calls in `~/.claude/settings.json` so it doesn't
prompt on each run. Existing skills of the same name are left alone unless you pass
`--force` / `-Force`.

A global install changes where the skills *live*, not where they *work* — Impeccable
still reads the code of, and writes `PRODUCT.md` / `DESIGN.md` into, whatever project
you run it in.

See **[docs/skills/README.md](docs/skills/README.md)** for every skill, what it does,
and which to reach for.

## When the project starts

The stack is deliberately unchosen — nothing here pins you to a framework. Add the app
at the root (or under `apps/`) and the skills apply to it as-is. Two files Impeccable
will create and then keep reading, both meant to be edited by hand:

- `PRODUCT.md` — audience, purpose, constraints, voice. Durable.
- `DESIGN.md` — the visual world: type, color, spacing, motion. Per project.

## Editing the skills

They're plain Markdown in `.claude/skills/` — open one and change it. Upstream re-syncs
overwrite local edits, so diff first if you've customized anything:

```bash
./scripts/update-skills.sh --latest
```

## Licenses

Skills stay under their upstream licenses (MIT, Apache-2.0) — see
[`docs/skills/licenses/`](docs/skills/licenses) and `skills-manifest.json`.
This repo's own code is under [LICENSE](LICENSE).
