---
name: SAT-SA
description: A supervisory analytics tool drawn as an audit working paper — every figure footed, every finding resolving to its source records.
colors:
  paper: "#f4f6f1"
  band: "#e4ede0"
  card: "#fbfcf9"
  rule-hairline: "#c6d0c2"
  rule-strong: "#7e8c7a"
  rule-heavy: "#3f4a3d"
  ink: "#1d211c"
  ink-soft: "#5c665a"
  ink-faint: "#8b948a"
  tick: "#1f4e79"
  exception: "#a32a1c"
  caution: "#8a5d0b"
  clear: "#3e6b4b"
typography:
  display:
    fontFamily: "ui-monospace, 'Cascadia Mono', 'Segoe UI Mono', Consolas, 'Liberation Mono', Menlo, monospace"
    fontSize: "44px"
    fontWeight: 600
    lineHeight: "1.05"
    fontFeature: "tabular-nums"
  headline:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    letterSpacing: "-0.015em"
  title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    letterSpacing: "-0.005em"
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: "1.5"
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.1em"
  data:
    fontFamily: "ui-monospace, 'Cascadia Mono', 'Segoe UI Mono', Consolas, 'Liberation Mono', Menlo, monospace"
    fontSize: "14.5px"
    fontWeight: 400
    fontFeature: "tabular-nums"
rounded:
  none: "0"
  stamp: "2px"
  ring: "50%"
spacing:
  hairline: "3px"
  tight: "9px"
  cell: "13px"
  gutter: "24px"
components:
  button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "9px 16px"
  button-hover:
    backgroundColor: "{colors.band}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
  button-disabled:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink-faint}"
    rounded: "{rounded.none}"
  link-inline:
    backgroundColor: "transparent"
    textColor: "{colors.tick}"
    padding: "0"
  index-tab:
    backgroundColor: "{colors.band}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.none}"
    padding: "3px 8px 3px 7px"
  workpaper-ref:
    backgroundColor: "transparent"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.none}"
    padding: "2px 6px"
  stamp:
    backgroundColor: "transparent"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.stamp}"
    padding: "7px 14px"
---

# Design System: SAT-SA

## Overview

**Creative North Star: "The Audit Working Paper"**

This is not a security dashboard. It is a sheet from an auditor's binder, rendered in a
browser. The governing idea is that a supervisory judgement is only worth what its
working is worth, so the interface is built the way an audit file is built: a schedule
that indexes, a reference that resolves, a total that foots, and a stamp that closes the
sheet. Every screen is a page of that file, and the reference number in the leftmost
column is the thread that ties one page to the next.

The material is green-bar analysis paper — the ruled, alternately banded stock that
ledger work was done on before spreadsheets — and the page carries its own faint
horizontal ruling behind the content. Density is high and deliberate: this is a reading
and checking surface, not a scanning surface, and the type is set small and tight with
the confidence of a document that expects to be read carefully. The field is achromatic
almost everywhere; colour is a scarce, load-bearing signal rather than a decorative one.

Two things were refused explicitly, and both refusals are visible in the result: the dark
SOC dashboard, with its neon severity chips and glowing cards, and its opposite — the
rounded-card SaaS surface with soft shadows and a generous radius. Neither is a document,
and a supervisor cannot foot a number on either. There is no shadow anywhere in this
system and no corner radius on any container.

**Key Characteristics:**

- Green-bar ledger paper (`#f4f6f1`) with alternating banded rows, never cream, never white
- Hairline rules only — no shadow anywhere in the system, no radius on any container
- Achromatic field; severity appears only as a 3px edge mark, never as a filled row
- Working-paper references (`WP-01.1`) thread score → finding → source record
- Tabular monospace for every figure, record id, and timestamp
- No webfont, no icon set, no package — the whole system is hand-written CSS that runs offline

## Colors

A single warm-green ledger neutral carrying three inks: an auditor's blue for anything
that resolves elsewhere, and a red and amber reserved almost entirely for severity edge
marks.

### Primary

- **Auditor's Blue** (`#1f4e79`): the tick mark. Every link, every reference that resolves
  to another page, and every focus ring. It is the colour of *"I checked this and here is
  where it goes"*, so it appears only on things that actually navigate or receive focus —
  never as a heading colour, a border, or a fill.

### Secondary

- **Exception Red** (`#a32a1c`): the red pen. The exception-band edge mark on a
  high-scoring row, the stroke through a raw total that has been capped, the auditor's
  ring drawn around a flagged value in an evidence table, and the "Tier capped" label. It
  never fills a surface and never colours body text.
- **Caution Amber** (`#8a5d0b`): the middle severity band's edge mark only.
- **Clear Green** (`#3e6b4b`): the edge mark on an entity with no findings, and the tick
  that marks it clean. A clean entity is a positive supervisory result, and this is the
  only place the system says so in colour.

### Neutral

- **Ledger Paper** (`#f4f6f1`): the page. Warm green-grey analysis stock, carrying a
  repeating 28px horizontal rule at 7% opacity so the sheet is visibly ruled.
- **Green Bar** (`#e4ede0`): the alternating band on even schedule rows, the fill behind
  a binder index tab, and the hover state on any interactive row or card head.
- **Card Stock** (`#fbfcf9`): the slightly brighter paper of a bordered sheet sitting on
  the page — the schedule, the summary strip, the evidence table.
- **Hairline** (`#c6d0c2`): every internal divider — row separators, cell borders, the
  rules inside a card.
- **Rule Strong** (`#7e8c7a`): the outer border of a sheet, and the underline beneath a
  table's column headers.
- **Rule Heavy** (`#3f4a3d`): reserved for the double rule under the masthead and the
  footing rule under a total. Two weights of "this is a boundary" and one weight of "this
  is *the* boundary".
- **Graphite** (`#1d211c`): body text. Not black — pencil on paper.
- **Graphite Soft** (`#5c665a`): secondary text, column labels, explanatory notes.
- **Graphite Faint** (`#8b948a`): a zero score, a struck value, the stamp border.

### Named Rules

**The Achromatic Field Rule.** Colour never fills a row, a cell, or a card. Severity is
carried by a 3px edge mark on the left of the score cell and nowhere else. A reader
scanning the schedule sees a column of coloured edges against uncoloured paper — which is
what makes a single exception readable at a glance, and what a filled-row treatment
destroys.

**The Tick Rule.** Auditor's blue means "this resolves somewhere". If an element is blue
and clicking it does not take you to the thing it names, the colour is wrong.

## Typography

**Display / Data Font:** system monospace stack (`ui-monospace`, Cascadia Mono, Segoe UI
Mono, Consolas, Liberation Mono, Menlo)
**Body Font:** system sans stack (`ui-sans-serif`, system-ui, -apple-system, Segoe UI,
Roboto, Helvetica Neue, Arial)
**Label Font:** the same sans, uppercased and tracked

**Character:** No webfont is loaded and none may be — the app must run with the network
off, which is a product constraint before it is a typographic one. The pairing works
because the roles are cleanly split rather than blended: the sans carries prose and the
mono carries every figure, record id, timestamp and reference. `font-variant-numeric:
tabular-nums` is set on every numeric run, so a column of scores lines up on the decimal
the way a printed schedule does. The result reads as a document set on office equipment,
which is exactly right for the world.

### Hierarchy

- **Display** (mono, 600, 44px, 1.05): the supervisory risk score on the entity detail
  page. One per page, and the only large figure in the system.
- **Headline** (sans, 700, 26px, -0.015em): the entity name on the detail page. Drops to
  21px below 720px.
- **Title** (sans, 700, 19px, -0.005em): section headings — "Entities Requiring
  Supervisory Attention", "Execution Gap Findings".
- **Body** (sans, 400, 15px, 1.5): explanation sentences and prose. Instance text is
  capped at 74ch and state copy at 56ch; running text never spans the full 1140px measure.
- **Label** (sans, 700, 11px, 0.1em, uppercase): table column headers, the score band
  label, the masthead reference line. Small, tracked, and always secondary in colour.
- **Data** (mono, 400, 14.5px, tabular-nums): schedule figures, record ids, timestamps,
  weights, working-paper references.

### Named Rules

**The Two-Register Rule.** Sans for language, mono for anything a reader might check
against another number. A figure set in the sans face reads as prose and stops being
checkable; a sentence set in mono reads as output and stops being explanation.

## Layout

A single centred measure of **1140px** with a **24px** gutter (14px below 720px), and no
sidebar, no panel, and no persistent chrome — a sheet is a sheet. Vertical rhythm comes
from the page's own 28px ruling, and blocks are separated by hairline rules rather than
by large gaps, which is what keeps the density legible instead of merely tight.

The entity list is a six-column schedule: working-paper reference, rank, entity (name over
sector), alerts, findings, risk score at the right edge. The right-alignment of the score
is structural — it is the column that foots. The detail page splits into a document body
on the left and a score block on the right, so the total and its per-tier calculation sit
beside the findings that produce them and can be read against each other without
scrolling.

Responsive behaviour is a single breakpoint at **720px**: the gutter tightens, the alerts
and findings columns drop out of the schedule entirely (rank, entity and score are what
the ranking is *for*), the display figure drops to 34px, the headline to 21px, and the
summary strip's cells stack full-width with their dividers rotating from left borders to
top borders. Nothing is hidden behind a menu and no layout reflows into cards.

### Named Rules

**The Footing Column Rule.** Every schedule's total column is right-aligned, monospaced
and tabular. If a column of figures does not line up on its digits, it cannot be footed by
eye, and the whole premise of the surface fails.

## Elevation & Depth

**This system has no shadows.** Not "few" — none. `box-shadow` appears nowhere in
`styles.css`, and adding one is a direction violation rather than a taste disagreement.
Paper does not float.

Depth is conveyed by three devices instead. First, **tonal layering**: card stock
(`#fbfcf9`) sits fractionally brighter than the page (`#f4f6f1`), and banded rows
(`#e4ede0`) sit fractionally darker, so a sheet reads as a distinct object without
lifting off. Second, a **three-weight rule hierarchy**: hairline for internal dividers,
strong for a sheet's outer edge, heavy for the masthead's double rule and a total's
footing rule. Third, **physical marks that imply a hand above the page** — the struck
total, the auditor's ring, the rotated verification stamp — which sit visibly *on* the
document rather than in it.

### Named Rules

**The No-Shadow Rule.** No `box-shadow`, anywhere, for any reason. Separation is expressed
by tone and rule weight. A shadow in this system reads instantly as a foreign component
pasted in from a different world.

## Shapes

**Square by default, and square as a statement.** Containers use `border-radius: 0`
explicitly rather than by omission — buttons, cards, sheets, tables, tabs, references.
Form language is entirely rectangular and rule-bound.

Exactly two radii exist in the whole system, and both belong to hand-marks rather than
containers: the auditor's ring is a full ellipse (`50%`, rotated -4°) drawn around a
flagged value in an evidence table, and the verification stamp carries a 2px radius
(rotated -1.5°) because a rubber stamp has a slightly softened edge. Both are rotated off
axis on purpose — they are the only things on the page that a machine did not set.

The recurring silhouette is the **bordered sheet**: 1px `rule-strong` outer border, card
stock fill, hairline internal dividers, no radius, no shadow. The schedule, the summary
strip, the evidence table and the rule cards are all the same object at different scales.

### Named Rules

**The Two Radii Rule.** A radius is permitted only on a mark made by a hand — the ring and
the stamp. Every container is square. If a new component needs rounding to look right, the
component is wrong for this world.

## Components

### Buttons

- **Shape:** square (`border-radius: 0`), 1px `rule-strong` border, card-stock fill.
- **Primary (and only) variant:** uppercase label type (13px, 0.06em tracking) in graphite
  on card stock, padding `9px 16px`. There is one button in the product — "Reset Demo
  Data" — and it is deliberately quiet; it is a utility control, not a call to action.
- **Hover:** fills to green-bar (`#e4ede0`) and the border darkens to `rule-heavy`, over
  120ms linear. No lift, no scale.
- **Disabled:** text drops to graphite-faint, border to hairline, `cursor: progress` —
  the reset is in flight, not forbidden.
- **Link variant:** borderless, no tracking, auditor's blue, underlined at a 3px offset.
- **Focus:** every focusable element takes a 2px auditor's-blue outline at 2px offset,
  set once globally on `:focus-visible`.

### Cards / Containers

- **Corner style:** square, always.
- **Background:** card stock on the page; banded green on alternate schedule rows.
- **Shadow strategy:** none — see Elevation & Depth.
- **Border:** 1px `rule-strong` outer, 1px hairline internal dividers.
- **Internal padding:** `13px 15px` for a row or card head; `13px 14px 13px 11px` for the
  score cell, whose left padding is reduced to seat the 3px edge mark.

### Finding cards (signature)

A rule card is a collapsed summary of one rule's firings: working-paper reference,
rule id, title, count (`×3`), summed weight, chevron. It opens on click to the individual
instances, each with its own explanation and evidence link. The body animates open via
`grid-template-rows: 0fr → 1fr` over 240ms rather than by animating `max-height` —
deliberately, so a long group is never clipped by an invented ceiling and the easing
tracks the real content height. The chevron rotates 45° → -135° over 160ms.

### Working-paper reference (signature)

The thread that holds the system together. An entity is a schedule (`CSE-01` → `WP-01`)
and a rule is a **fixed** section within it (`EG-003` → `.3`), so a reference means the
same thing on every entity and never shifts as findings appear or disappear. Gaps are
correct and meaningful: a schedule with no `WP-01.5` has no bulk-closure finding. It is
rendered in mono at 11.5px inside a 1px hairline box, and it appears in the schedule's
leftmost column, on every finding card and instance row, in the evidence header, and in
the closing stamp.

### The struck total (signature)

When a tier's raw sum exceeds its 100-point cap, the raw figure is shown struck and the
capped figure beside it. The strike is drawn as an absolutely-positioned 2px
exception-red rule rotated -5°, not as `text-decoration` — so it reads as a pen stroke
made by a person correcting a working paper, which is the point. It carries a plain
explanatory note beneath it and is **never** presented as an error state.

### Auditor's ring (signature)

In an evidence table, the value that actually triggered the rule (`1.4`, `No`) is circled
rather than recoloured: a 1.5px exception-red ellipse, inset `-5px -8px`, rotated -4°,
`pointer-events: none`. Recolouring the text would make it look like invalid input;
circling it looks like someone checked it.

### Verification stamp (signature)

Closes the evidence sheet, bottom-right: "VERIFIED AGAINST SOURCE RECORDS" over the
working-paper reference and record count, in a 1.5px graphite-faint box at 2px radius,
rotated -1.5° at 85% opacity.

### Corroboration profile (added 2026-09-05)

A four-row table inside the ML block, one row per model feature: the entity's figure, the
peer-group mean it was judged against, its deviation in population sigmas, the attribution
the ranking used, and a plotted mark.

It exists because the finding's prose names two drivers and stops. "Driven by share of
high/critical alerts" is a claim; `0.56 against a peer mean of 0.34, +2.98σ` is the
working. The deterministic rules have always resolved to their source records, and this is
the same promise kept by the one layer that could not previously honour it.

The plot is a **mark, not a fill**: a 1px centre rule for the peer mean, and a 3px bar to
one side of it whose length is the deviation, scaled to the largest on that entity with a
1.5-sigma floor so unremarkable spreads are not magnified. The bar is graphite except on
the two features the attribution leaned on hardest, which take exception ink and a 3px
left edge on the row — the same red pen that circles a triggering value in an evidence
table, and the same edge-mark language the schedule uses. The field stays achromatic.

The attribution column is not decoration: without it a row marked at +0.82σ sits above an
unmarked row at +0.72σ and the marking reads as arbitrary. The column shows the number the
ranking actually used.

It renders for entities the model did **not** flag, too, captioned "this entity sits inside
the normal profile". A supervisory tool that only shows its reasoning when it accuses is
showing an argument, not a method.

### Dataset provenance and upload (added 2026-09-05)

The masthead reference line carries the dataset the schedule was computed over — "Synthetic
demo dataset", or `Source: <filename>` after an upload. A screenshot of findings with no
dataset attribution is not evidence of anything.

Two buttons, both the existing quiet utility variant: "Load CSV" and "Reset Demo Data".
Loading data is preparation, not the point of the page, so neither is styled as a call to
action.

A rejected upload uses the exception banner **stacked** rather than inline: a heading in
exception ink, a monospace list of line-numbered problems, and a hairline-separated note
giving the expected columns and a template link. The schedule stays on screen behind it —
the previous dataset is still loaded, and the banner must not imply otherwise.

### Binder index tabs

Section headings ("Execution Gap Findings") carry a mono tab — `EG`, `NS`, `ML` — filled
green-bar with a 1px `rule-strong` border thickened to 3px on the left, like the tab of a
binder divider. The ML tab is dashed rather than solid, which is how the subordinate
section announces itself before its heading is read.

### Tables

Column headers are label type, underlined by a 1px `rule-strong` rule; rows are separated
by hairlines and alternate onto the green bar; every figure is monospaced and tabular.
Wide tables scroll inside their own container so the page body never scrolls sideways.

### States

Loading, error, empty and not-found are all designed, centred, and measure-capped at 56ch.
Loading uses a 50%-opacity pulse. Errors present as an inline bordered banner with a
retry — the previous content stays on screen behind it. "No findings of this type" is
plain text, never an empty region.

### Motion

The signature moment is **the footing rule**: the double rule beneath the supervisory risk
score draws once, left to right, over 420ms on
`cubic-bezier(0.22, 0.8, 0.3, 1)` after a 60ms delay — the gesture of a total being footed.
Everything else is functional and short: 110–120ms linear for hover fills, 160ms ease-out
for the chevron, 240ms ease-out for a card unrolling. A global
`prefers-reduced-motion: reduce` block collapses every animation and transition to 0.01ms.

## Do's and Don'ts

### Do:

- **Do** carry severity as a 3px left edge mark on the score cell (`--edge`), and leave
  the rest of the row achromatic.
- **Do** set every figure, record id, timestamp and reference in the mono stack with
  `font-variant-numeric: tabular-nums`.
- **Do** give any new resolvable reference the same treatment as `WP-01.1` — mono, 11.5px,
  hairline box — and make it actually navigate.
- **Do** separate blocks with hairline rules (`#c6d0c2`) and reserve `rule-heavy`
  (`#3f4a3d`) for the masthead's double rule and a total's footing rule.
- **Do** express a correction as a physical mark — struck rule, ring, stamp — rotated a
  degree or two off axis.
- **Do** keep running prose to its measure (74ch in instances, 56ch in states) even though
  the page is 1140px wide.
- **Do** hide the alerts and findings columns, not the score, when the schedule reaches
  720px.

### Don't:

- **Don't** add a `box-shadow`. There are none in this system and there is no exception.
- **Don't** round a container. `border-radius` belongs only to the ring (`50%`) and the
  stamp (`2px`).
- **Don't** fill a row, cell or badge with a severity colour — that is the dashboard
  language this direction exists to refuse.
- **Don't** introduce a webfont, icon font, SVG icon set, or any runtime-fetched asset.
  The app must render identically with the network off, and the CSP of the demo is "no
  network at all".
- **Don't** colour a capped or struck figure as an error. A cap is a deliberate scaling
  choice and must read as an auditor's correction, never as a failure.
- **Don't** use auditor's blue for anything that does not resolve to another view.
- **Don't** animate `max-height` to open a group; use `grid-template-rows: 0fr → 1fr` so
  nothing is clipped at an invented ceiling.
- **Don't** let the ML Corroboration section reach visual parity with the two detection
  sections. It sits below them, indented behind a rule, with a dashed tab, a smaller
  heading and a standing caveat — the subordination is a product truth expressed
  visually, not a layout preference. **(Amended 2026-09-05: the section now also carries
  the corroboration profile — see Components. Every device that expresses subordination
  is unchanged; what the block gained is depth, not prominence.)**
