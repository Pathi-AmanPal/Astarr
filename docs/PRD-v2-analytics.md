# SAT-SA v2 — Product Requirements Document

**Supervisory Analytics Tool for SOC Assessment — Analytics Workspace rebuild**

Version 2.0 · Written 2026-09-05 · Status: ready to build

> **Who this is for.** This document is written to be executed by an AI coding agent
> working on a local checkout, with no access to the conversation that produced it.
> Every decision that could otherwise be guessed is stated. Where a decision is *not*
> made, it appears in §16 Open Questions and must be raised with the product owner
> rather than resolved silently.

---

## 1. What exists today

The repository is a working FastAPI + DuckDB + React application. **v2 is a frontend
rebuild and a data-lifecycle change. The detection and scoring engine is not being
rewritten and must not be.**

### 1.1 Keep, unchanged

| Path | What it is | Status in v2 |
| --- | --- | --- |
| `backend/detection.py` | 7 deterministic rules (EG-001…005, NS-001, NS-002) | **Frozen.** Read it; do not modify rule logic. |
| `backend/scoring.py` | Weighted-tier scoring, per-tier 100-point cap | **Frozen.** |
| `backend/rules.yaml` | All thresholds and weights. No defaults in the loader — a missing key raises at startup, on purpose | **Frozen** except additive keys |
| `backend/config.py` | Validating loader for the above | Keep |
| `backend/ml.py` | Isolation Forest + SHAP corroboration | Keep; extend read-only |
| `backend/ingest.py` | CSV/JSON validating parser | Keep; extend |
| `backend/verify.py` | The regression suite. Currently 110 checks | **Extend. Never weaken.** |
| `backend/db.py` | DuckDB schema and connection | Extend with new tables |

### 1.2 Replace

| Path | Why |
| --- | --- |
| `frontend/src/pages/*` | All three screens are replaced by the v2 information architecture |
| `frontend/src/styles.css` | New visual direction (§9). The 892-line audit-paper stylesheet is retired |
| `DESIGN.md` | Rewritten for the new direction once the build is done, not before |

### 1.3 Delete

| Path | Why |
| --- | --- |
| `backend/seed.py` | v2 has no built-in dataset. See §4. |
| `custom_test_alerts.csv` | Superseded. Fold its planted scenarios into `tests/fixtures/regression-dataset.csv` if useful, then delete |

### 1.4 The scoring formula, for reference

Each finding carries a weight from `rules.yaml`. Findings group into three tiers by
`finding_type`. Each tier's raw weight-sum is capped **individually** at 100, then
multiplied by its tier weight:

```
EXECUTION_GAP    × 0.45
NEGATIVE_SPACE   × 0.40
ML_CORROBORATION × 0.15
```

The three tier weights sum to exactly 1.0, which is what guarantees the total can never
exceed 100 without an outer clamp. **`config.py` asserts this at startup. If you change a
tier weight you must change another to preserve the sum, or the app will refuse to
start — which is the intended behaviour, not a bug.**

Attainable maximum is 86.5, not 100, because the ML tier cannot exceed 10 raw.

---

## 2. Goals

1. **A real tool, not a demo.** No dataset ships inside the product. The tool is empty
   until a supervisor loads their own data, and every number on screen traces to a row
   they supplied.
2. **An analytics workspace.** The primary screen answers "how is this SOC performing?"
   with charts, not a table of twelve rows.
3. **Everything is inspectable.** Every chart segment, every statistic, and every
   finding drills down to the source records. This is the product's existing promise and
   v2 must not weaken it.
4. **Case triage through a tree.** Findings are navigable as a hierarchy —
   entity → tier → rule → instance → record — not a flat list.
5. **It stays honest.** Where the data cannot support a claim, the UI says so rather
   than rendering an empty chart that looks like a zero.

## 3. Non-goals

Do not build these. If one seems necessary, stop and raise it.

- Authentication, users, roles, multi-tenancy
- Any outbound network call at runtime — see §3.1
- A chat assistant or LLM feature of any kind
- Real-time streaming, websockets, or polling for live alerts
- Alert triage *actions* (assign, close, comment). This is a supervisory read-only tool
- Rewriting the detection rules or the scoring formula
- Mobile-first design. Desktop is the target; the layout must not break below 1024px,
  but it need not be beautiful there

### 3.1 The offline constraint is absolute

The product must render identically with the network disabled, and ships as an
air-gapped container. Therefore:

- **No webfonts, no CDN, no runtime-fetched asset.** Fonts must be either system stacks
  or self-hosted files bundled at build time.
- npm dependencies are fine — they are compiled into the bundle. A dependency that
  *fetches at runtime* is not.
- Any new dependency must be added to `frontend/package.json` or
  `backend/requirements.txt` so the offline image build picks it up. A dependency
  installed only on a dev machine will fail the container build.

---

## 4. Data lifecycle: no built-in dataset

### 4.1 The rule

`backend/seed.py` is deleted. The application starts with an empty database and stays
empty until a file is loaded. There is no hidden fallback, no "if empty then generate",
and no fixture written on first boot.

### 4.2 What replaces it

**The schema template, and nothing else, in the product.**

| File | Shipped where | Reachable from the UI? |
| --- | --- | --- |
| `samples/sat-sa-template.csv` | `samples/` | **Yes** — a 3-row column reference, downloaded to answer "what shape does it want?" |
| `tests/fixtures/regression-dataset.csv` | `tests/fixtures/` | **No.** Test ground truth only |

**There is deliberately no "Load sample dataset" button.** The product owner's demo
opens on the empty state and the first action on camera is uploading the SOC's own alert
export. A one-click sample loader on that screen invites exactly the question the empty
start exists to pre-empt — *"so it does ship with data?"* — and answers it badly. The
template download is different: it is a column reference, three rows, obviously not a
dataset.

### 4.3 Regression suite consequence

`verify.py` currently seeds from `seed.py` and asserts 12 entities / 248 records /
18 findings. Rewrite it to load `tests/fixtures/regression-dataset.csv` through
`ingest.parse()` instead.

**Deleting `seed.py` without this step deletes the regression suite's ground truth.** The
fixture is not a product feature and must never be reachable from the UI, but it is
mandatory: it is the only thing that keeps "every rule fires exactly where planted" a
checkable claim.

The fixture must be **deterministic** — fixed timestamps, no randomness, no wall-clock
read — and committed. Generate it once with `scripts/make-fixture.py` (also committed)
and never regenerate it casually; regenerating changes every expected count in the suite.

Keep every existing assertion that is still meaningful. The counts will change; the
*structure* of the suite must not weaken.

### 4.4 Data lifecycle endpoints

| Method | Path | Behaviour |
| --- | --- | --- |
| `POST` | `/api/dataset/upload` | multipart CSV/JSON. Validate fully, then replace. Exists today — keep |
| `DELETE` | `/api/dataset` | Wipe everything and return to the empty state. **New** |
| `GET` | `/api/dataset` | Provenance: source, label, loaded_at, counts. Exists — keep |
| `GET` | `/api/dataset/template.csv` | Exists — keep |

**Validation must keep refusing rather than repairing.** A missing severity must not
become `MEDIUM`; a missing `entity_id` must not become a real entity's id. This is
already implemented in `ingest.py` and is load-bearing: a supervisory tool that
silently guesses a field produces findings that are wrong with nothing on screen
admitting it. Preserve every rejection case in `verify.py`.

---

## 5. Metrics catalogue

This is the analytical core of v2. **Every metric below is computed server-side and
exposed through the API. The frontend performs no analysis beyond formatting.** That
keeps one definition of every number, and keeps it testable in `verify.py`.

### 5.1 Computable from the current schema

Available columns: `record_id, entity_id, asset_id, severity, category, opened_at,
closed_at, escalated, disposition, investigation_notes, closure_time_minutes`.

**Volume and coverage**

| Metric | Definition |
| --- | --- |
| Total alerts | `COUNT(records)` |
| Alerts per entity | `COUNT(*) GROUP BY entity_id` |
| Open alerts | `closed_at IS NULL` |
| Alerts over time | `COUNT(*)` bucketed by day and by week on `opened_at` |
| Severity mix | share of LOW / MEDIUM / HIGH / CRITICAL |
| Category mix | share per `category` |
| Category coverage | distinct categories reported by an entity ÷ distinct categories across all entities |
| Asset concentration | share of an entity's alerts from its single busiest `asset_id` |

**Handling quality**

| Metric | Definition | Why it matters |
| --- | --- | --- |
| Mean closure time | `AVG(closure_time_minutes)` where closed | Headline throughput |
| **Median closure time** | 50th percentile | **Report this beside the mean.** A handful of month-old cases drags a mean; the gap between the two is itself a finding |
| p90 closure time | 90th percentile | The tail is where neglect hides |
| Rapid-closure rate | share of HIGH/CRITICAL closed in `< 2` min, unescalated | The EG-001 population, as a rate |
| Escalation rate | `AVG(escalated)` | |
| Critical escalation rate | `AVG(escalated)` where `severity='CRITICAL'` | A CRITICAL that is never escalated is EG-002 |
| Disposition mix | share TRUE_POSITIVE / FALSE_POSITIVE / BENIGN | |
| Undocumented dismissal rate | share of HIGH/CRITICAL with FALSE_POSITIVE or BENIGN and empty notes | The EG-004 population |
| Note-duplication rate | share of records whose `investigation_notes` are byte-identical to ≥2 others in the same entity | The EG-003 population |

**Supervisory outcomes**

| Metric | Definition |
| --- | --- |
| Risk score per entity | Existing weighted-tier score |
| Score distribution | Histogram across entities |
| Findings by rule | `COUNT(*) GROUP BY rule_id` |
| Findings by tier | `COUNT(*)` and summed weight per tier |
| Clean entity share | entities with zero findings ÷ all entities |
| Tier contribution | per entity, the three tier contributions that foot to the score |

### 5.2 NOT computable — do not invent these

The schema has **no analyst, owner, team, shift, SLA target, first-response timestamp,
or reopen count**. Therefore the following are impossible today and must not appear as
charts fed by guessed or derived-by-proxy data:

- Per-analyst or per-team performance, leaderboards, workload balance
- SLA compliance or breach rate
- Mean time to *acknowledge* (only time to close exists)
- Reopen / recidivism rate
- Shift or time-of-day performance **by team** (time-of-day *volume* is fine; attributing
  it to a shift is not)

> **This is the single most likely way this build goes wrong.** "SOC team performance"
> naturally suggests a per-analyst dashboard. The data cannot support one. Fabricating an
> `analyst` column, or presenting per-entity numbers as per-person numbers, would make the
> tool dishonest in exactly the way its detection rules exist to expose.

**If per-analyst analytics are wanted**, they require four optional schema columns —
`analyst_id`, `analyst_name`, `acknowledged_at`, `sla_target_minutes` — added to
`ingest.py` as *optional*, with every dependent metric hidden when the column is absent.
Treat that as a separate phase and confirm before building it (§16, Q2).

### 5.3 Honesty rules for every metric

1. **A metric computed over fewer than 5 entities, or fewer than 20 records, is
   labelled low-confidence in the UI.** The existing NS-001 cohort gate already embodies
   this principle; extend it rather than contradict it.
2. **Never render an empty chart as a zero.** No data means an explicit "not enough data
   to compute this" state naming what is missing.
3. **A percentage always shows its denominator** on hover or beneath the figure.

---

## 6. API surface

Existing endpoints stay. Additions:

```
GET  /api/analytics/overview
GET  /api/analytics/timeseries?bucket=day|week
GET  /api/analytics/distribution?by=severity|category|disposition|score
GET  /api/analytics/handling                 # closure percentiles, rates
GET  /api/entities/{id}/analytics            # the same metrics scoped to one entity
GET  /api/tree                               # the full case hierarchy, §8.3
DELETE /api/dataset                          # clear
```

### 6.1 Contract rules

- Every response is a Pydantic model in `backend/models.py`. No untyped dicts.
- Every numeric field that can be absent is `float | None`, never `0`. The frontend
  distinguishes "zero" from "unknown" and so must the wire format.
- Every metric object carries `{ value, denominator, confidence }` where
  `confidence` is `"ok" | "low" | "unavailable"`, so the UI never has to re-derive
  §5.3's rules.
- Errors keep the existing shape: `{ "error": str, "details": [str] }`.
- **Serialise all database access.** One DuckDB connection is shared across a
  threadpool; the existing `@serialised` decorator in `main.py` exists because parallel
  requests corrupted each other's reads. Every new endpoint must use it. This is not
  optional — the dashboard fires many requests at once and will reproduce the bug
  immediately.

---

## 7. Information architecture

Four destinations, reached from a persistent left sidebar.

```
01  Overview     Dashboard. Charts. The health of the whole dataset.
02  Entities     Ranked list → per-entity analytics + findings tree.
03  Cases        The tree. Every finding, hierarchically, with evidence.
04  Data         Provenance, upload, clear, template/sample download.
```

Routes:

```
/                      → Overview
/entities              → Entity list
/entities/:id          → Entity detail
/cases                 → Case tree (all entities)
/cases/:findingId      → Case tree focused on one finding, evidence open
/data                  → Data management
```

Deep links must work on reload — the SPA fallback in `main.py` already handles this for
the container build; keep it.

---

## 8. Screens

### 8.1 Overview

The question it answers: *is this SOC doing the work, and where is it not?*

Layout, top to bottom:

1. **Headline row** — 4 stat tiles: Entities, Alerts analysed, Findings raised, Entities
   requiring attention. Each tile shows the figure, a one-line definition, and is
   clickable through to the filtered view.
2. **Risk distribution** — histogram of entity risk scores, banded exception / caution /
   clear. Clicking a band filters the entity list.
3. **Alert volume over time** — line chart, day or week toggle, with severity as an
   optional breakdown.
4. **Handling quality** — grouped bar: mean vs **median** vs p90 closure time. The
   mean-median gap is the point; label it.
5. **Findings by rule** — horizontal bar, ordered by summed weight, coloured by tier.
6. **Disposition and severity mix** — two small donuts or stacked bars, side by side.
7. **Coverage matrix** — entities × categories heatmap. An empty cell is a candidate
   blind spot and is what NS-002 fires on; clicking one opens the finding if it exists.

Every chart is drillable. Every chart has an explicit empty state.

### 8.2 Entities

List, ranked by risk score, with sparkline of alert volume per entity. Clicking opens
the entity detail: the same metric set as Overview but scoped, plus the entity's findings
tree and its ML corroboration profile (peer means, sigma deviations, SHAP attribution —
this already exists, keep it).

### 8.3 Cases — the tree

A five-level hierarchy:

```
Entity  (CSE-01 · Northern Grid · risk 56.50)
└── Tier  (Execution Gap · 215 raw → 100 capped × 0.45 = 45.00)
    └── Rule  (EG-001 · Rapid closure without escalation · ×3 · 105 pts)
        └── Instance  (F-0001 · 35 pts · "Alert ALT-0007 (HIGH) was closed in 1 min…")
            └── Record  (ALT-0007 · HIGH · Malware · opened 08:00 · closed 08:01)
```

Behaviour:

- Expand/collapse per node, with state persisted in the URL so a tree view is shareable.
- **Keyboard navigable**: ↑↓ move, →← expand/collapse, Enter opens evidence. Use
  `role="tree"`, `role="treeitem"`, `aria-expanded`, `aria-level`.
- Each node shows its own count and summed weight, so a collapsed branch still carries
  information.
- Filter box that filters across all levels and auto-expands matches.
- Virtualise only if a dataset exceeds ~2000 visible nodes; measure before adding the
  dependency.

### 8.4 Data

Provenance card (source, filename, loaded time, counts), upload control, **Clear
dataset** (with confirmation — it is destructive and irreversible), and downloads for
the template and the sample.

### 8.5 The empty state — a first-class screen

With no data loaded, `/` shows a designed empty state, not a blank dashboard:

- What the tool does, in two sentences.
- The upload control, as the primary action — large, obvious, drag-and-drop as well as
  click.
- "Download the template" as the only secondary action.
- The expected columns, listed.

**This is the opening shot of the demo video (§8.6). It is a designed screen, not a
placeholder.**

Every other route redirects here while the dataset is empty. **Build this early, not
last** — with `seed.py` deleted it is the first thing anyone sees, and it will be the
state the tool is in most often during development.

---

### 8.6 The demo video path — a build requirement

The product is demonstrated by a recorded walkthrough that **starts from an empty tool
and loads a real SOC alert export on camera.** That sequence is a requirement, not a
marketing afterthought, because it is what makes "no built-in data" visible rather than
merely claimed.

The path, in order, must work end to end without a reload, a console error, or a visible
broken frame:

1. **Empty state.** Designed, composed, obviously intentional (§8.5).
2. **Upload.** Drag-and-drop or click. The filename is visible as it is accepted.
3. **Validation.** On a good file, no error. On a bad one, line-numbered problems over
   an unchanged empty state.
4. **Population.** The dashboard fills. Charts animate in from their zero baseline —
   one coordinated 400–600ms entrance, not eight independent ones.
5. **Provenance.** The uploaded filename is on screen, in the masthead, permanently.
   This is the shot that proves the data came from the operator.
6. **Drill down.** Overview → a chart segment → the entity → its findings tree → one
   finding → its evidence records.
7. **Clear.** The dataset is removed and the tool returns to the empty state.

Requirements this imposes:

- **No flash of a broken or skeletal layout** between upload and populated dashboard.
  Hold the previous frame until the data is ready, then transition once.
- **Upload → rendered dashboard in under 3 seconds** for a file of a few thousand rows.
- **Every number visible in step 4 must be traceable in step 6.** A headline figure that
  cannot be drilled into is a figure that will be asked about on camera.
- Respect `prefers-reduced-motion` — the entrance animation must have a no-motion path.

Build and rehearse this path in Phase 4; do not discover it in Phase 7.

---

## 9. Visual direction

The v1 "audit working paper" direction (green-bar ledger, hairline rules, no shadows, no
radius) is **retired** in v2. It was built for a document; v2 is an instrument panel.

### 9.1 Direction: instrument, not dashboard-template

Dark, dense, and precise — closer to an oscilloscope or a trading terminal than to a
SaaS admin theme. Specifically:

- **Dark ground**, near-black with a slight cool cast, not pure `#000`.
- **One accent** that carries interaction and focus. `#5227FF` is the React Bits default
  and is a reasonable choice; commit to it and use it consistently or replace it
  everywhere. Do not introduce a second accent for decoration.
- **Severity keeps its own scale**, independent of the accent: exception red, caution
  amber, clear green. These are data colours and must never be used for chrome.
- **Monospace for every figure**, with `font-variant-numeric: tabular-nums`, so columns
  of numbers align on their digits. Sans for prose. This rule survives from v1 and is
  worth keeping: a figure set in a proportional face stops being checkable.
- Restraint on glow and gradient. One accent glow on the focused element is enough;
  glowing everything is the generic-AI-dashboard tell.

### 9.2 Explicit bans

- No purple-to-blue gradient hero
- No card nested inside a card inside a card
- No rounded-square icon tile above every heading
- No emoji as iconography
- No chart junk: no 3D, no drop shadows on bars, no pie chart with more than 5 slices
- Grey text on a coloured background

### 9.3 Accessibility floor

- Contrast ≥ 4.5:1 for body text, ≥ 3:1 for large text and chart strokes, against the
  actual background used.
- **Never encode a distinction by colour alone.** Severity needs shape, label, or
  position as well — roughly 1 in 12 men cannot separate your red from your green.
- Visible focus ring on every interactive element.
- Respect `prefers-reduced-motion`: collapse all transitions to near-zero. v1 has a
  global block for this; carry it forward.

---

## 10. Charts

### 10.1 Library

Use **Recharts** (`recharts`, SVG-based, React-native API, no runtime fetching). Add it
to `package.json`. Rationale: it renders to SVG so it themes with CSS variables and
prints cleanly, and it does not require a canvas fallback for accessibility.

If Recharts proves limiting for the coverage heatmap, hand-write that one in SVG rather
than adding a second charting library.

### 10.2 Chart selection

| Data | Chart | Never |
| --- | --- | --- |
| Volume over time | Line, or area if a single series | Bars for a continuous time axis |
| Score distribution | Histogram | A pie |
| Findings by rule | Horizontal bar, sorted by value | Vertical bars with rotated labels |
| Severity / disposition mix | Stacked bar, or donut with ≤5 slices | A pie with 8 slices and a legend |
| Closure percentiles | Grouped bar | A single "average" number alone |
| Entity × category coverage | Heatmap | A stacked bar with 12 series |
| Per-entity trend, in a table row | Sparkline, no axes | A full chart shrunk down |

### 10.3 Chart rules

- Y axis starts at zero for any bar chart. Truncating a bar axis misrepresents the ratio.
- Direct-label the series where there are ≤4; use a legend only beyond that.
- Every chart is keyboard reachable and exposes its data as an accessible table
  (visually hidden `<table>` is acceptable and is the simplest correct answer).
- Tooltips show the value **and its denominator**.
- Every chart has an explicit `no data` and `not enough data` state (§5.3).

---

## 11. React Bits components

Two components are specified by the product owner. Both are integrated as given —
copy the source into `frontend/src/components/reactbits/`, import the CSS alongside.

### 11.1 `LineSidebar` — primary navigation

Used for the four-item main navigation in §7.

```jsx
<LineSidebar
  items={['Overview', 'Entities', 'Cases', 'Data']}
  accentColor="#5227FF"
  defaultActive={0}
  onItemClick={(index) => navigate(ROUTES[index])}
  showIndex
  showMarker
/>
```

**Required adaptations — do not ship it unmodified:**

1. **It is not a router.** `onItemClick` sets its own internal `activeIndex`; on a
   browser back/forward it will disagree with the URL. Drive `defaultActive` from the
   current route and force a remount (`key={pathname}`), or lift active state out.
2. **It is `<li onClick>`, not a link.** Keyboard users cannot reach it and it has no
   href to middle-click. Wrap each label in an `<a href>` / react-router `<Link>`, or
   add `tabIndex={0}` plus Enter/Space handling and `role="link"`. **Ship keyboard
   navigation; a nav that only works with a mouse fails §9.3.**
3. Its proximity effect is pointer-driven and inert on touch. Acceptable — desktop is
   the target — but the active item must still be visually obvious without hover.

### 11.2 `Folder` — the evidence opener

Used on a **finding instance** to open its evidence: the folder is the case file, the
papers are its evidence records.

```jsx
<Folder size={1.4} color="#5227FF" items={previewPapers} />
```

**Read this before designing around it:**

- **It holds exactly 3 papers.** `items.slice(0, maxItems)` with `maxItems = 3`. A
  finding with 25 evidence records cannot be represented by the papers.
- The papers are small decorative rectangles. They are not a place to render a table.

**Therefore, the specified use is:**

Place one `Folder` per finding instance as the affordance that *opens* evidence. The
three papers show a **preview** — the first three record ids — and the folder carries a
count badge beside it ("25 records"). Clicking it opens the full evidence table in a
panel or route (`/cases/:findingId`), where all records render as a proper table.

Do **not** attempt to page 25 records through 3 papers, and do not render a grid of 200
folders for 200 alerts — it is an accent for a focused view, not a list primitive. The
list primitive is the tree (§8.3).

Its click target must also be keyboard-operable; the source already has
`tabIndex`/`role="button"`/Enter/Space, so preserve that when restyling.

### 11.3 Theming both

Both ship with their own CSS and their own `:root` variables. Scope them — rename to
`--folder-color` etc. under a wrapper class, or the `:root` block in `Folder.css` will
leak defaults into the app. Wire their colours to the app's design tokens so a palette
change is one edit.

---

## 12. Non-functional requirements

All figures below are **measured**, not estimated — on the v1 pipeline, 2 vCPU, Linux,
Python 3.11, DuckDB. Reproduce with `scripts/bench.py`. They are the numbers to put in
the Architecture Document and the "Infrastructure requirements" deliverable.

### 12.1 Throughput, by dataset size

| Records | Entities | Ingest | Detect | **Total** | Peak RSS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 20 | 0.61s | 1.88s | **2.5s** | 299 MiB |
| 100,000 | 20 | 2.53s | 2.42s | **4.9s** | 343 MiB |
| 100,000 | 2,000 | 4.34s | 7.90s | **12.3s** | 311 MiB |
| 1,000,000 | 50 | 20.3s | 5.34s | **25.6s** | 504 MiB |

### 12.2 What this replaced

The v1 pipeline read every record into Python. Same hardware, same datasets:

| Records / entities | Before | After |
| --- | --- | --- |
| 100,000 / 20 | 5.7s · 438 MiB | **4.9s · 343 MiB** |
| 100,000 / 2,000 | 30.2s · 427 MiB | **12.3s · 311 MiB** |
| 1,000,000 / 50 | 37.7s · 1,530 MiB | **25.6s · 504 MiB** |

Peak memory no longer tracks dataset size the way it did: the validation stage alone
fell from 895 MiB to 143 MiB on a million rows.

### 12.3 How it works — do not undo these

**Ingestion streams.** `ingest.iter_validated_rows` is a generator accepting a string
*or a file handle*; `stage_csv` writes each validated row straight to a staged CSV and
`load_streaming` hands that to DuckDB in one statement. Three things were each costing a
full copy of the dataset and are all gone: `io.StringIO(text)` duplicated the file, a
second dict was built per row on top of `DictReader`'s, and the upload endpoint held the
whole body as a Python string (it now spools to disk and reads back a handle).

**Detection is set-based.** `rules_sql.py` expresses EG-001…005 and NS-002 as
`INSERT ... SELECT`, so neither a record nor a finding ever becomes a Python object.
NS-001 stays in Python deliberately — it reasons over one number per entity and its
peer-cohort validity gate is a judgement SQL would obscure rather than accelerate.

**`run_detection_python` is retained as the executable specification.** It is the
definition of what the rules mean; the SQL engine is an optimisation of it. `verify.py`
asserts the two produce byte-identical findings on every run. **If they ever disagree,
the Python one is right.** Do not delete it to tidy up.

### 12.4 Stated minimum specification

> **2 vCPU · 2 GiB RAM · 1 GiB disk · no GPU · no network.** Runs on a standard
> air-gapped Windows or Linux VM. One million alert records ingest, analyse and score in
> roughly 26 seconds at a peak of ~500 MiB; 100,000 records across 2,000 CSEs in 12
> seconds at ~310 MiB.

DuckDB's working memory can be bounded further with `SATSA_DB_MEMORY_LIMIT` and
`SATSA_DB_THREADS`. Both are unset by default on purpose: DuckDB's own default adapts to
the machine, and a fixed low limit is not free — 256MB holds peak RSS to 404 MiB on the
million-row load, while **128MB fails outright** with an OutOfMemoryError inside EG-003's
aggregation. Treat it as a deployment knob, not a default.

### 12.5 Other targets

| Requirement | Target |
| --- | --- |
| Cold start to interactive | < 2s |
| Upload → recomputed dashboard | < 5s for 100k records |
| Bundle size | < 500KB gzipped including Recharts |
| Offline | Renders identically with the network off. Verified by disabling it |
| Determinism | Same input file → byte-identical findings and scores, every run |
| Concurrency | Every DB endpoint serialised (§6.1) |

### 12.6 Remaining limits

**1. Ingest is now the dominant cost** — 20 of the 26 seconds on a million rows. That is
Python-level per-row validation, and it buys the line-numbered error messages the upload
UX depends on (§4.4). Parallelising it across processes is the next lever, and it is not
needed yet.

**2. The ML layer scales with entity count, not record count.** Isolation Forest plus
SHAP over a 2,000-row feature matrix is ~5s. Two O(n²) mistakes were already removed
here — `_zscores` recomputed every column's mean and sigma once per row, and the profile
insert used `executemany` — so what remains is the model itself. Beyond ~5,000 CSEs,
consider fitting on a sample and scoring the full set.

**3. Evidence lists for NS-001 and NS-002 are every record the entity filed.** At 20,000
records per entity that is a ~260 KB string per finding. Correct, but it is why those
two rules should never be given a per-category evidence list.

### 12.7 A product limit the numbers exposed

1,000,000 records produced **220,514 findings**. That is not a performance problem — it
is a prioritisation problem, and functional requirement #10 is *"prioritise entities,
controls, processes and alert samples for manual review."* A supervisor cannot review
220,000 findings, so at real volume the finding list stops being the deliverable and the
**ranked entity list** becomes it.

v2 must therefore treat entity-level rollup as the primary output and findings as
drill-down detail — which the §7 information architecture already does, but the tree
(§8.3) must be built to open lazily per entity rather than materialising every node.
Add to the metrics layer: findings per entity per rule as counts, so the Overview never
fetches individual findings at all.

## 13. Verification

`verify.py` is the gate. It currently reports **110 checks, 0 failures** and must never
be weakened to accommodate a change. Extend it:

**Existing, keep (adapted to the sample fixture):** every rule fires exactly where
planted and nowhere else; NS-001's threshold and cohort gate, including the negative
test that disables the gate and asserts the rule goes silent; determinism across two
independent builds; every ingest rejection case; concurrent-read safety.

**New:**

1. Every metric in §5.1 computes without error on the sample fixture, and each returns
   the hand-checked expected value. Compute the expectations once, by hand, and hard-code
   them — a test that recomputes the implementation's own logic proves nothing.
2. Median and p90 are correct against a known distribution, including even-length input
   (the classic off-by-one).
3. `confidence` is `"low"` below the §5.3 thresholds and `"ok"` above, asserted at both
   sides of each boundary.
4. A metric with a zero denominator returns `None`, never `0` and never a
   `ZeroDivisionError`.
5. `DELETE /api/dataset` empties every table including `findings`, `ml_profile` and
   `dataset_meta`, and the app serves the empty state afterwards.
6. The tree endpoint's node counts and summed weights equal the flat findings table's,
   per entity and per tier — the tree must not be able to disagree with the schedule.
7. **Prove the negative:** with `seed.py` deleted, a fresh database yields zero entities
   and zero findings. Assert no code path repopulates it.

**Frontend:** `npx tsc -b` clean before any commit. Playwright smoke test covering
empty state → upload sample → dashboard renders → drill to tree → open evidence → clear
dataset → empty state.

---

## 14. Delivery phases

Ship each phase working. Do not start a phase before the previous one's checks pass.

| Phase | Scope | Done when |
| --- | --- | --- |
| **0** | Branch, read `PRODUCT.md` + `DESIGN.md` + `rules.yaml`, run `verify.py`, record the baseline | Baseline recorded |
| **1** | Delete `seed.py`; build `samples/`, `scripts/make-sample.py`, `DELETE /api/dataset`; rewrite `verify.py` onto the fixture | Suite green on the new fixture; empty DB stays empty |
| **2** | Metrics layer + `/api/analytics/*`, fully typed, fully tested. **No UI work.** Aggregate in SQL — never `fetchall()` a raw records table into Python (§12.5) | Every §5.1 metric has a passing hand-checked assertion; 100k records still renders the Overview in < 4s |
| **3** | Shell: routes, `LineSidebar` with the §11.1 fixes, empty state, Data screen | Can upload, see provenance, clear, and land back on empty |
| **4** | Overview dashboard and all charts | Every chart renders, drills, and has empty/low-confidence states; **the §8.6 video path runs clean end to end** |
| **5** | Cases tree + `Folder` evidence opener | Tree keyboard-navigable; counts reconcile with the schedule |
| **6** | Entity detail, ML profile carried over, sparklines | — |
| **7** | Polish, offline verification with the network physically off, rewrite `DESIGN.md` from what shipped | Three consecutive clean end-to-end runs |

**Phase 2 before any charts.** Building charts against a metrics layer that does not
exist yet produces frontend-computed numbers that then have to be unpicked.

---

## 15. Rules for the agent building this

1. **Run `verify.py` after every backend change.** It is the contract. If it fails, fix
   the code, not the test.
2. **Propose numbers before implementing them.** Any new threshold, weight, or band
   boundary gets its computed values shown and confirmed first.
3. **Prove behaviour, don't assert it.** "Unchanged" means a diff of the full findings
   dump and the ranked entity list, before and after.
4. **Claim exactly what is implemented.** No UI copy, README line, or doc claim may
   outrun the code. A stale claim on screen is a demo failure.
5. **Never invent data.** No placeholder rows, no `Math.random()`, no lorem ipsum, no
   `analyst_name` that is not in the file. An empty state is correct; a fabricated one is
   not.
6. **No silent fallbacks.** `config.py` raises on a missing key on purpose. Match that
   posture: fail loudly, in the place the mistake was made.
7. **Read before replacing.** `detection.py` and `scoring.py` encode decisions with
   reasons; the comments explain them. If a change seems necessary there, stop and ask.
8. **Commit per phase**, with a message stating what was verified and how.

---

## 16. Open questions — resolve with the product owner before building

1. **Q1 — Regression fixture content.** *(Partly settled: there is no user-facing
   sample dataset — §4.2.)* Should `tests/fixtures/regression-dataset.csv` reuse the
   retired seed's planted scenarios (12 entities, 248 records, 18 findings), or model a
   different SOC? Reusing it preserves every existing assertion and is substantially
   less work. **Recommended: reuse it.** It is a test fixture nobody sees; novelty buys
   nothing and costs the whole suite's ground truth.
   
   Separately, the product owner must supply the **file used in the demo video** (§8.6).
   That is a real or realistic SOC export, is *not* committed to the repo, and is not
   this fixture.
2. **Q2 — Per-analyst analytics.** Are the four optional columns in §5.2
   (`analyst_id`, `analyst_name`, `acknowledged_at`, `sla_target_minutes`) in scope? If
   yes it is a phase of its own; if no, the dashboard is per-entity only and must be
   labelled that way so nobody reads it as per-person.
3. **Q3 — Accent colour.** Keep React Bits' `#5227FF`, or pick a palette specific to
   SAT-SA? A default accent from a component library is a recognisable tell.
4. **Q4 — Dark only, or a light theme too?** Dark-only is less work and a stronger
   commitment; a projector in a bright room favours light.
5. **Q5 — What happens to v1?** Is the audit-paper UI archived on a branch, or deleted?
   It is a genuinely distinctive design and worth keeping recoverable.
6. **Q6 — The frozen demo branch.** `claude/download-integrate-skills-2uy967` holds the
   verified Sept 15 build. Confirm v2 work never targets it.

---

## Appendix A — Data contract

```
record_id             TEXT     required, unique
entity_id             TEXT     required
entity_name           TEXT     required
sector                TEXT     required
asset_id              TEXT     required
severity              TEXT     required, one of LOW MEDIUM HIGH CRITICAL
category              TEXT     required, free text
opened_at             TIMESTAMP required, ISO 8601
disposition           TEXT     required, one of TRUE_POSITIVE FALSE_POSITIVE BENIGN
closed_at             TIMESTAMP optional, must be >= opened_at
escalated             BOOLEAN   optional, blank = false
investigation_notes   TEXT      optional
closure_time_minutes  DOUBLE    optional, derived from timestamps when absent
```

Minimum 2 entities — the Negative Space rules compare an entity against a population.
Maximum 50,000 rows per upload.

## Appendix B — Rules reference

| Rule | Tier | Weight | Fires when |
| --- | --- | --- | --- |
| EG-001 | Execution Gap | 35 | HIGH/CRITICAL closed in < 2 min, unescalated |
| EG-002 | Execution Gap | 25 | CRITICAL with no escalation record |
| EG-003 | Execution Gap | 20 | Identical investigation notes ≥3 times within one entity |
| EG-004 | Execution Gap | 15 | HIGH/CRITICAL dismissed FALSE_POSITIVE/BENIGN with empty notes |
| EG-005 | Execution Gap | 25 | ≥5 alerts closed within a single minute |
| NS-001 | Negative Space | 30 | Alert volume below `mean − 1.5σ` (population σ), cohort-gated at n≥5 |
| NS-002 | Negative Space | 25 | A category absent that ≥75% of peers report, entity has ≥10 records |
| ML-001 | ML Corroboration | 10 | Isolation Forest flags the entity **and** a deterministic rule already fired |

ML-001 can never originate a finding. Preserve that gate and the visual subordination
that expresses it.
