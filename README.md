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
scripts/update-skills.sh   re-sync skills from upstream
skills-manifest.json       source repos + pinned commits + licenses
```

Skills load automatically in Claude Code from `.claude/skills/`. Nothing to install,
no dependencies, no API keys. Node 22+ is only needed for Impeccable's detector
scripts.

## Quick start

```bash
git clone <this repo> && cd Astarr
claude          # skills are discovered on launch
```

Then, once there's something to design:

```
/impeccable init        # records product truth in PRODUCT.md
```

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
