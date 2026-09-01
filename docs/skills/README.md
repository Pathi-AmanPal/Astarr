# Skill library

Every skill below is **vendored** into `.claude/skills/` — the files live in this
repo, so they load with zero install steps and you can edit any of them in place.

Sources, pinned commits and licenses: [`skills-manifest.json`](../../skills-manifest.json)
and [`licenses/`](./licenses).

## How skills load

| Path | What it is |
| --- | --- |
| `.claude/skills/<name>/SKILL.md` | A skill. Claude Code auto-discovers it; the `name:` in the frontmatter is how you invoke it. |
| `.claude/agents/impeccable-*.md` | Subagents Impeccable delegates to (asset production, docs, finish review, manual edits). |
| `.agent/skills/impeccable` | Symlink → `.claude/skills/impeccable`. Impeccable's own scripts and `allowed-tools` reference this path; keep it. |
| `.claude/settings.json` | Pre-approved Bash permissions so the skill scripts don't prompt every run. |
| `.claude/settings.impeccable-hooks.json` | Opt-in design-detector hooks (see below). |

Directory name and skill `name:` differ for some of the taste-skill entries — the
**Invoke as** column is the one that matters.

## Impeccable — full design system (Apache-2.0)

Source: [pbakaus/impeccable](https://github.com/pbakaus/impeccable)

One skill, 20+ sub-commands, 61 deterministic detector rules that run locally with
no LLM and no API key.

```
/impeccable init          # interview → writes PRODUCT.md (durable product truth)
/impeccable shape <target>
/impeccable polish <target>
/impeccable audit <target>
/impeccable critique <target>
/impeccable animate | colorize | typeset | layout | bolder | quieter | distill
/impeccable harden | optimize | adapt | extract | document | doctor | live
```

Full command list: [`.claude/skills/impeccable/reference/`](../../.claude/skills/impeccable/reference)
(one file per command) and `scripts/command-metadata.json`.

It writes two files at the project root when you run it:
`PRODUCT.md` (who/what/why — durable) and `DESIGN.md` (the visual world — per project).
Neither exists yet; `/impeccable init` creates them.

**Optional hooks.** `.claude/settings.impeccable-hooks.json` runs the detector after
every Edit/Write and a deep pass on Stop. It's off by default because it adds latency
to every turn — merge its `hooks` block into `.claude/settings.json` if you want it.
Requires Node 22+ (this repo is verified on Node 22).

## Design taste — leonxlnx/taste-skill (MIT)

Source: [leonxlnx/taste-skill](https://github.com/leonxlnx/taste-skill)

| Directory | Invoke as | What it does |
| --- | --- | --- |
| `taste-skill` | `design-taste-frontend` | Anti-slop frontend for landing pages, portfolios, redesigns. The default. |
| `taste-skill-v1` | `design-taste-frontend-v1` | The original v1, kept for behavior-compatibility. |
| `redesign-skill` | `redesign-existing-projects` | Audits an existing site, strips generic AI patterns, raises it to premium. |
| `soft-skill` | `high-end-visual-design` | Agency-grade fonts, spacing, shadows, card structure, motion. |
| `minimalist-skill` | `minimalist-ui` | Editorial, warm monochrome, flat bento, no gradients. |
| `brutalist-skill` | `industrial-brutalist-ui` | Swiss print × military terminal. Rigid grids, extreme type contrast. |
| `stitch-skill` | `stitch-design-taste` | Generates an agent-friendly `DESIGN.md` with anti-generic UI standards. |
| `brandkit` | `brandkit` | Brand-guideline boards, logo systems, identity decks. |
| `image-to-code-skill` | `image-to-code` | Generates the design image first, analyzes it, then codes it. |
| `imagegen-frontend-web` | `imagegen-frontend-web` | Premium website design references (one image per screen). |
| `imagegen-frontend-mobile` | `imagegen-frontend-mobile` | App-native mobile screen concepts and flows. |
| `output-skill` | `full-output-enforcement` | Bans placeholders/truncation; forces complete code generation. |
| `gpt-tasteskill` | `gpt-taste` | GPT/Codex-targeted variant with GSAP motion + AIDA structure. |

Extra reading: [`taste-skill-llms.txt`](./taste-skill-llms.txt),
`.claude/skills/stitch-skill/DESIGN.md`.

## Motion & craft — emilkowalski/skills

Source: [emilkowalski/skills](https://github.com/emilkowalski/skills) (author of Sonner and Vaul)

| Skill | What it does |
| --- | --- |
| `animate` | Build an animation from scratch, decisions in the order that makes it feel right. |
| `animate-expo` | Same, for React Native / Expo. |
| `animation-vocabulary` | Reverse glossary: vague description → the exact motion term. |
| `improve-animations` | Audits existing motion code, emits prioritized implementation plans. |
| `review-animations` | Reviews motion against a high craft bar. Defaults to flagging. |
| `find-animation-opportunities` | Read-only sweep for things that should animate — and things that shouldn't. |
| `apple-design` | Apple's fluid, physical motion translated to the web. |
| `emil-design-eng` | The underlying philosophy: polish, component design, invisible details. |
| `prototype` | Builds several genuinely different versions behind a live visual picker. |
| `pick-ui-library` | Opinionated library picks: OTP, charts, command menus, virtualization, DnD. |
| `ask-sonner` | Sonner toast library reference (`API.md` included). |
| `write-swift` | Modern Swift: value types, Swift 6 data-race safety, approachable concurrency. |

## Which one do I reach for?

- **Starting a surface from nothing** → `/impeccable init`, then `/impeccable shape`, or `design-taste-frontend` for a fast landing page.
- **Existing UI feels generic** → `redesign-existing-projects`, or `/impeccable critique` for a written verdict first.
- **Locking a visual direction before building** → `stitch-design-taste` (writes `DESIGN.md`) or an `imagegen-*` skill for references.
- **It works but feels dead** → `find-animation-opportunities` → `animate` → `review-animations`.
- **Final pass before demo** → `/impeccable polish`, then `/impeccable audit`.

## Installing elsewhere

`./scripts/install-skills.sh --global` (or `.\scripts\install-skills.ps1 -Global` on
Windows) copies every skill and agent into `~/.claude/`, making them available in all
projects, and merges the Impeccable script permissions into `~/.claude/settings.json`.

Run the same script with no flags after a fresh clone — it repairs
`.agent/skills/impeccable` when the checkout didn't preserve the symlink, which is the
default on Windows.

## Updating / editing

Everything here is ordinary tracked files — edit them directly and commit. To pull
upstream changes instead:

```bash
./scripts/update-skills.sh                    # re-sync all at pinned commits
./scripts/update-skills.sh --latest           # pull upstream HEAD
./scripts/update-skills.sh impeccable --latest
```

A `--latest` run prints the SHAs it checked out; paste them into
`skills-manifest.json` so the pins stay honest. **Local edits to a skill are
overwritten by a re-sync** — if you've customized one, diff before you sync.
