# SAT-SA — Design

*Written 2026-09-06, after the build, from the shipped stylesheet rather than from
intentions. Everything here is in `frontend/src/styles.css` and can be checked
against it.*

## Scope of this document

This records the direction now on screen: the **three existing screens** — ranking,
entity, evidence — rebuilt around a new visual system, a persistent shell and a real
navigation trail. It is **not** the v2 information architecture described in
[`docs/PRD-v2-analytics.md`](docs/PRD-v2-analytics.md): there is still no case tree,
no `Folder` component, no `LineSidebar`, and no chart beyond the composition bar. Those
remain that document's scope, and PRD §9's binding floor (anti-patterns, accessibility,
tabular figures) is what this direction was built to satisfy.

## The one-line brief

**An instrument, not a document.** v1 was an audit working paper — green-bar ledger
stock, hairlines, no radius, no shadow. It was coherent, and it was the wrong metaphor:
a supervisor scanning forty entities is reading an instrument face, and an instrument
has a lit ground, reserved signal colour, and figures that align.

## Three decisions that carry it

**1. The ground is dark and tinted, not neutral.** `#0d1110` is a green-graphite. It
keeps a memory of the ledger stock it replaces and it is deliberately not the `#121212`
every generated dark theme lands on. One grey family throughout — no warm greys mixed
with cool ones.

**2. Cool means navigate, warm means risk.** There is exactly one accent, a lifted
version of v1's auditor's-blue tick mark, and it means one thing: *this is traceable,
follow it*. Severity is warm and is never spent on chrome. Nothing is distinguished by
colour alone — every band carries a written label (`exception` / `caution` / `clear`),
every composition segment carries a legend row, and the deviation plot encodes
direction as position rather than hue.

**3. Density is the feature.** Figures are monospace with `tabular-nums` everywhere.
A column of scores that does not align on its digits cannot be compared by eye, which
is the entire job of the ranking screen.

## Tokens

| | Value | Contrast on ground | Used for |
| --- | --- | --- | --- |
| `--ground` | `#0d1110` | — | page |
| `--ground-2` | `#111614` | — | table head, wells |
| `--panel` | `#151b19` | — | sheets, cards |
| `--panel-hi` | `#1c2421` | — | hover |
| `--rule` / `--rule-strong` | `#232b28` / `#36423d` | — | hairlines |
| `--ink` | `#e8eeea` | 14.6:1 | body |
| `--ink-soft` | `#a3b0aa` | 7.4:1 | secondary |
| `--ink-faint` | `#7b8981` | 4.7:1 | the floor — nothing below it |
| `--accent` | `#86b9dc` | 8.3:1 | links, references, focus, primary action |
| `--exception` | `#e8705c` | 5.6:1 | severity only |
| `--caution` | `#d9a441` | 8.4:1 | severity only |
| `--clear` | `#74a58c` | 6.5:1 | severity only |
| `--tier-eg/ns/ml` | `#86b9dc` `#7fb59b` `#6f7f8a` | ≥3:1 | composition bar, always with a legend |

Type is system stacks — `ui-sans-serif` and `ui-monospace` heads. **No webfont, ever**:
the tool must render identically with the network disabled and it ships air-gapped, so
character comes from the typographic system, not from a downloaded face. The favicon is
an inline SVG data URI for the same reason.

Radius tightens inward: `10px` containers, `6px` panels, `3px` chips. Shadows carry the
ground's hue rather than black, and all of them fall from one light.

## Rules the build follows

- **Every figure carries a unit, a denominator or a comparison.** `57.00` alone says
  nothing; `57.00 of 86.5 attainable` does. The attainable maximum is 86.5, not 100,
  because the ML tier can contribute at most 1.5 — it is printed rather than assumed.
- **Composition bars are scaled to a shared maximum, never normalised per row.** A bar
  normalised to its own row is full on every row and compares nothing.
- **A capped tier is noted beside the scale, never in place of it.** "Tier capped" does
  not mean a maximum score, and replacing the denominator with it implied that it did.
- **No screen is a dead end.** Every screen carries a breadcrumb; an unknown URL gets a
  designed screen rather than a silent redirect.
- **Focus is visible on everything**, one treatment, including inside tables.
- **`prefers-reduced-motion` collapses every transition**, and the ranking rows' entry
  cascade is switched off outright rather than left mid-animation.

## Two things worth knowing before editing

**The sticky table header must not sit inside an `overflow: hidden` container.** An
overflow container is a scrollport; a sticky header inside one that cannot scroll gets
pushed down by its own `top` offset and paints over the first row. `.sheet` therefore
clips its corners through the cells that touch them, and only `.sheet--scroll` — which
really does scroll — sets `top: 0`.

**`--topbar-h` and the sticky header's offset are coupled.** Change the top bar's
padding and that variable has to follow, or the header will float or overlap.
