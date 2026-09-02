# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Locked by the Phase 1 PRD §11 — do not substitute or add libraries without explicit
instruction.

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, served via `uvicorn` on
  `http://localhost:8000`
- **Data processing:** Pandas (seed-data loading and derivation)
- **Database:** DuckDB, single local file `sat_sa.duckdb`
- **Frontend:** React + Vite + TypeScript, `react-router-dom`
- **Styling:** Plain CSS or minimal utility classes. No design-system or UI-library
  dependency, no charting library.
- **Machine learning:** scikit-learn (`IsolationForest`) and `shap`.
- **Packaging:** None. `uvicorn` + `npm run dev` / `vite preview`, run directly.

**Approved dependency amendment (2026-09-02).** `scikit-learn` and `shap` are added to
`backend/requirements.txt` by explicit instruction. This is the single authorised exception
to §11's "do not substitute or add libraries" lock — recorded here as an approved
amendment, not a silent violation. Both install once, offline at runtime like every other
dependency. The frontend dependency lock is untouched: still react, react-dom,
react-router-dom, and hand-written plain CSS.

**Location in this repo:** `backend/` and `frontend/` sit at the Astarr repo root, so the
PRD §14 run commands (`cd backend`, `cd frontend`) work verbatim.

**Frontend quality bar (revised 2026-09-02, supersedes PRD §7's "visual polish is
secondary to reliability"):** the frontend is held to a production-quality bar, not a
minimal one. The judging round shortlists partly on look and feel, assessed by
non-technical judges, so craft is a scored property of the deliverable rather than a
nicety. Specifically required:

- strong typography, spacing, and a consistent visual identity across all three screens —
  not bare functional tables;
- empty, loading, and error states that are deliberately designed, never browser or React
  defaults;
- restrained micro-interaction where it aids comprehension: risk-score reveal, entity-row
  hover, and transitions between list → detail → evidence.

**The dependency lock in §11 is unchanged and absolute.** All of the above is written in
plain CSS by hand. No npm package, no design system, no icon or font dependency, no
charting library, nothing fetched at runtime. Craft the CSS; do not reach for a library to
reach the bar. Nothing here may trade away reliability, determinism, or offline operation,
and PRD §10's acceptance run is unaffected — see Operating Context.

## Users

**Primary user — an NCIIPC supervisor.** They open the dashboard to see which supervised
entities need attention, ranked by risk, and to satisfy themselves that the ranking is not
a black box. Their job is oversight of other organisations' SOC (Security Operations
Centre) performance: judging whether an entity is genuinely investigating security alerts
or only appearing to.

Phase 1 has a **single implicit user**. No login, no roles, no multi-user concerns.

**Immediate evaluating audience — a competition judge, general rather than technical.**
For the 15 Sept 2026 demo, a judge operates the app unsupervised on an offline laptop.
They are not the product's long-term user, but Phase 1's success condition is defined by
their session — and shortlisting turns substantially on how the product looks and feels,
not only on whether it works. A judge who cannot read the SQL still forms a judgement from
the interface. Legibility to a non-specialist is therefore a product requirement: findings
must be understandable without SOC domain knowledge, and the interface must earn
confidence on sight.

## Product Purpose

SAT-SA (Supervisory Analytics Tool for SOC Assessment) surfaces the gap between what an
entity's SOC *reports* doing and what it *actually* did. It reads flattened SOC alert/case
records and detects two classes of supervisory finding:

- **Execution Gap** — work that was recorded but not really performed: high-severity
  alerts closed in under two minutes without escalation, `CRITICAL` alerts with no
  escalation record, and investigation notes repeated verbatim across cases.
- **Negative Space** — what is conspicuously *missing*: an entity reporting far fewer
  alerts than the dataset average, suggesting under-detection or under-reporting rather
  than a quiet environment.

Each entity gets a transparent additive risk score, and every point of that score traces
down to the exact source records that produced it.

**Phase 1 success:** a judge can, unsupervised, click the whole flow — entity list →
entity detail → evidence → reset — on a laptop with Wi-Fi off, three consecutive times,
with nothing erroring, blanking, or crashing.

## Positioning

**Explainability that goes all the way down to the source record.** The score is not a
model output to be trusted on faith — it is a visible sum of named findings, each with a
plain-language sentence, each linked to the specific alert rows that triggered it. A
supervisor can walk backwards from any number to the evidence in two clicks.

The complement to this is the **Negative Space** premise: most SOC assessment tooling
scores the alerts an entity submitted. SAT-SA also scores the alerts it *didn't* — absence
treated as a finding rather than as clean data.

Phase 1 keeps deterministic rules and statistics as the primary engine, because a
demonstrable, inspectable chain of reasoning is the thing being proven. An Isolation Forest
runs alongside them as a small corroborating signal that can never originate a finding —
the ordering is the point, and the build is what makes it true rather than a slide.

## Operating Context

- **Live judged demo, 15 Sept 2026**, on a specific laptop, operated by a judge without
  guidance. That is 13 days out from 2026-09-02.
- **Fully offline.** Zero outbound network calls at runtime. No CDN fonts, icons, or
  scripts — everything bundled. The acceptance run is performed with Wi-Fi disabled.
- **Two local processes.** Backend on `localhost:8000` (hardcoded as a constant in
  `api.ts`; no environment-variable setup in Phase 1), frontend on the Vite dev server.
- **Open pre-demo action — verify the demo machine's Python.** The development machine
  runs Python 3.14 against §11's 3.11+ floor, resolving to duckdb 1.5.5, pandas 3.0.5,
  pydantic 2.13.5. §10 requires the acceptance run on the exact demo laptop, so that
  machine's interpreter must be checked and the backend installed there well before
  15 Sept. Any 3.11+ version is fine; an older or divergent environment must be found now,
  not on demo day. Environment mismatch discovered on stage is the worst failure mode
  available, and it is entirely preventable.
- **Self-seeding.** The database is created and populated automatically on first server
  start; no manual seeding step ever exists.
- **The demo script is the definition of done.** PRD §10's six-step sequence must pass
  three consecutive times end-to-end, manually, with Wi-Fi disabled. A failure at any step
  means re-running the whole sequence, not just the failing step. This requirement is
  fixed and scales *with* scope: every rule and screen added enlarges what the three runs
  must cover. Added scope never buys reduced testing.
- **Phase 2 is a separate 36-hour national-round build.** Phase 1 must not carry partial
  versions of its features; a half-built deferred feature is worse than its absence
  because it adds stage-time failure surface.

## Capabilities and Constraints

### Three screens, fixed

1. **Entity Risk List (`/`)** — rank, entity name, risk-score badge (green `<30`, amber
   `30–60`, red `>60`), finding count. Server returns it sorted; the client must not
   re-sort in a way that could diverge. A "Reset Demo Data" action lives top-right.
2. **Entity Detail (`/entities/:id`)** — entity name, large score, and the findings split
   into two clearly separated sections, *Execution Gap Findings* and *Negative Space
   Findings*. Each finding is a card with title, weight, and a "View Evidence" action.
3. **Evidence View (`/findings/:id`, route or modal)** — the finding's explanation
   sentence prominent at top, then a table of the underlying records with full fields.

### Non-negotiable product behaviours

- **The score breakdown is always visible.** Both the list and detail screens must show
  the contributing findings and their weights, never the final number alone. The PRD calls
  this non-negotiable — it is the core explainability claim being demonstrated.
- **Determinism.** Seed generation uses index-based loops and a fixed anchor date — no
  RNG, no `NOW()`, no wall-clock dependency. Repeated resets must produce byte-identical
  entities, findings, and scores. Rankings visibly unchanged after reset is demo step 5.
- **No blank or broken states, ever.** Every API call carries an explicit loading state
  and an error state. Unknown entity or finding → inline "not found" with a link back,
  never a blank page. Unreachable backend → "Cannot reach backend — is it running on
  localhost:8000?". A failed reset → retry-able inline banner on the list page. An empty
  findings section → "No findings of this type", never empty space.
- **Sub-second API responses** on the fixed dataset, stated as an explicit acceptance bar.

### Detection and scoring, fixed

Four rules, thresholds hardcoded: `EG-001` rapid closure without escalation (weight 35,
per record), `EG-002` critical alert without escalation (25, per record), `EG-003`
repetitive/template investigation notes (20, per entity, ≥3 records sharing notes),
`NS-001` below-average alert volume (30, per entity, below `mean − 1.5 × stddev`).
EG-001 and EG-002 may both fire on one record; keeping both is intentional.

`ML-001` ML corroboration (10, per entity, only where an EG or NS finding already exists).

Score is `MIN(100, SUM(weights))` — simple, additive, capped. No tiered or
weighted-percentage formula in Phase 1.

Findings are recomputed from scratch on every detection run and are never hand-edited.

**Expansion to six rules (confirmed 2026-09-02).** Three rules added, each inheriting the
same discipline — deterministic, explicitly planted in the seed, and programmatically
verified to fire before being relied on:

- `EG-004` dismissed without recorded justification (15, per record) — `HIGH`/`CRITICAL`
  closed as `FALSE_POSITIVE`/`BENIGN` with empty investigation notes.
- `EG-005` bulk closure burst (25, per entity-minute group) — ≥5 records sharing one
  `closed_at` minute, consistent with queue-clearing rather than review.
- `NS-002` threat-category blind spot (25, per entity) — an entity with ≥10 records that
  filed nothing in a category at least 75% of entities report. NS-001 asks *how much*; NS-002
  asks *what kind*. The ≥10 guard stops a coverage gap being explained away by low volume
  and avoids double-penalising CSE-02.

`category` becomes load-bearing as a result — previously free text used by no rule.

**Seed discipline:** planted records replace filler slots inside their own entity, so
every per-entity total in PRD §12 holds exactly. NS-001's `mean − 1.5σ` is computed from
those counts, so holding them fixed leaves the Negative Space demo mathematically
untouched by any rule addition.

**NS-002 threshold is proportional, not absolute (deliberate choice, confirmed
2026-09-02).** A category counts as "expected" when at least **75% of entities** report it,
evaluated as `ceil(0.75 × entity_count)`. The rule previously used a hardcoded `6`, which
was 75% of 8 — so this preserves today's behaviour exactly (`ceil(0.75 × 8) = 6`) while
scaling correctly. The absolute form was rejected on purpose: at 12 entities a fixed `6`
silently becomes a 50% bar, and at 24 entities a 25% bar, weakening the rule with no error,
no warning, and nothing in any test to catch it. Proportional keeps the rule's meaning
stable as the dataset grows.

### Standing rule for any future dataset expansion

**Re-run the NS-001 margin check in BOTH directions — never only the entity you expect to
stay flagged.** Adding entities near the mean shrinks σ, which *raises* the threshold
(`mean − 1.5σ`). That makes an already-low entity safer while moving every clean entity
*closer* to falsely crossing the threshold from the other side. Both must be asserted:

1. the intended low-volume entity is still below the threshold, and
2. no clean entity has fallen below it.

Observed when expanding 8 → 12 entities: CSE-02's margin improved from 6.39 to 8.72, while
the next-lowest entity's margin **shrank** from 8.61 to 6.28. The second number is the one
that breaks a demo, and it is the one an expansion check naturally forgets to look at.

The same applies to NS-002's proportional bar and to the Isolation Forest: re-derive and
re-report both against the new entity count rather than carrying forward the previous
result. `verify.py` asserts all of this; keep it that way.

**Resolved defect:** PRD §10 step 2 requires the highest-risk entity to show both an
Execution Gap *and* a Negative Space finding, but CSE-01 had no NS finding — the
acceptance script could not pass as written. NS-002 is planted on CSE-01, which fixes it
in the seed rather than by amending the locked §10.

**Breakdown presentation (confirmed 2026-09-02).** §5's requirement is that a score is
never shown without its breakdown — not that every finding occupies its own full-height
card. Findings group by `rule_id`: one card per rule showing count and summed weight
("Rapid closure without escalation × 3 — 105 pts"), collapsed by default and expandable to
the individual instances, each keeping its own evidence link. This satisfies §5 in full —
every contributing weight stays visible and every record stays reachable — and adds an
insight a flat list cannot express: that a rule fired repeatedly. CSE-01 renders as five
cards rather than nine.

**Capped-score disclosure (confirmed 2026-09-02).** CSE-01's raw sum is 240, capped to 100
by §5. The cap is a deliberate scaling choice that keeps the scale comparable across
entities, and must read that way — never as an overflow or error state. The score displays
as "Risk Score: 100 · Maximum", with a supporting line: "Contributing findings total 240
points — scores are capped at 100 to keep the scale comparable across all entities." The
word "capped" is not used as a status label on the number itself. This adds copy beyond
§16 and a `risk_score_raw` field to the entity responses in §6; the §5 formula itself is
untouched.

**Two implementation traps recorded so they are not rediscovered:** DuckDB's `STDDEV()` is
`stddev_samp`, while §12 specifies population standard deviation — use `stddev_pop`
explicitly. And entity ordering must be `risk_score DESC, entity_id ASC`, since three
entities tie at zero and an unstable tiebreak would fail §10 step 5's determinism check.

### Terminology

*Entity* (a supervised organisation, `CSE-01`…`CSE-08`), *record* (one alert/case row),
*finding* (a rule firing, with weight and evidence), *Execution Gap*, *Negative Space*,
*disposition*, *escalation*, *Supervisory Risk Score*.

### ML corroboration (scope amendment, 2026-09-02)

PRD §9 deferred all ML to Phase 2. That deferral is **withdrawn for Isolation Forest and
SHAP only**, which are now implemented in Phase 1. Everything else in §9 stays deferred.

`ML-001` is a corroborating signal and never a sole trigger. It is evaluated **only** for
entities that already carry at least one Execution Gap or Negative Space finding from the
deterministic engine, so the model can never originate a finding on its own. Weight 10 —
deliberately the smallest in the system, because it corroborates rather than drives.
`finding_type` is `ML_CORROBORATION`, a third category kept separate from `EXECUTION_GAP`
and `NEGATIVE_SPACE` so nothing implies the model participated in either.

`IsolationForest(n_estimators=100, contamination="auto", random_state=42)` fits on all
entities' feature vectors fresh on every server start, sharing the lifecycle of the
existing detection. `random_state=42` is mandatory: it is what keeps §10 determinism true.
Features are `alert_count`, `avg_closure_time_minutes`, `escalation_rate`, and
`pct_high_critical`. Attribution comes from SHAP where available, falling back to per-
feature z-score deviation from the dataset mean — the same kind of auditable explanation
NS-001 already gives.

**Honest limitation to state, never hide:** the peer group is small, so this is a weak
statistical signal by construction. That is exactly why it corroborates at weight 10 and
cannot fire alone. The demo framing must stay: rules and statistics are primary and fully
deterministic; Isolation Forest is a small secondary signal. The build makes that claim
demonstrably true rather than merely asserted.

### Explicitly out of scope for Phase 1

YAML-configurable thresholds, multi-format
ingestion, any file-upload UI or endpoint accepting user-supplied data, Docker/offline
image packaging, authentication and roles, peer-cohort grouping for Negative Space, trend
analysis and time-series charts, rule/model versioning and run history, and the
weighted-tier scoring formula. These are documented and planned, not forgotten — they
belong to the Phase 2 build.

## Brand Commitments

- **Name:** SAT-SA — Supervisory Analytics Tool for SOC Assessment. The repository is
  named Astarr; the product is not.
- **Fixed UI copy** (PRD §16, use verbatim): tab title "SAT-SA — Supervisory Analytics";
  list header "Entities Requiring Supervisory Attention"; detail score label "Supervisory
  Risk Score"; reset button "Reset Demo Data".
- **No logo, wordmark, or brand assets exist.** The PRD requires no further branding for
  Phase 1.
- **Voice:** plain, factual, supervisory. Explanations are written to be read by a
  regulator who must defend the number, not to persuade.

## Evidence on Hand

- **The PRD itself** — [`docs/SAT-SA-Phase1-PRD.md`](docs/SAT-SA-Phase1-PRD.md), locked
  scope, the authority for Phase 1. Where it conflicts with general best practice, it
  wins.
- **A fully specified synthetic dataset** (PRD §12): 8 entities, 158 records, with the
  demo findings planted by construction. `CSE-01` (25 records) carries EG-001, EG-002, and
  EG-003 and must end up highest-risk — the primary demo entity. `CSE-02` (4 records) is
  the Negative Space entity. `CSE-05` (23 records) carries a single EG-002 to show a
  second, lower-weight profile. The remaining five are clean filler.

### What does not exist, and must not be fabricated

- **No real SOC data, no real entity, no customer, no deployment.** The dataset is
  synthetic and explicitly labelled as a demo dataset.
- **No peer-cohort analysis.** `NS-001` is a simplified comparison against the global
  dataset average. The PRD requires a small footer note on that finding's evidence view
  saying so, and forbids claiming peer-cohort comparison anywhere in Phase 1 UI copy.
- **No accuracy figures, no benchmarks, no validation claims.** An Isolation Forest now
  runs (see the scope amendment above), but nothing may state or imply it was validated,
  tuned, or measured for accuracy — it was not. It is an unsupervised outlier signal over a
  small peer group, presented as corroboration only.
- **No testimonials, press, pricing, or licensing claims.**

## Product Principles

1. **Every number traces to a record.** If a figure appears on screen and a supervisor
   cannot reach the rows behind it, it does not belong there. The breakdown is the
   product, not a disclosure.
2. **Claim exactly what is implemented.** Simplified logic is labelled as simplified.
   Deferred capability is never implied by copy, affordance, or visual suggestion.
3. **Nothing on screen may dead-end.** Every state — loading, error, empty, not-found — is
   designed and reachable-from. An unsupervised judge must never meet a blank.
4. **Determinism over freshness.** The same seed produces the same scores on any day, on
   any machine, offline. Nothing may introduce wall-clock or network dependence.
5. **Scope discipline beats completeness.** A narrow build that survives three consecutive
   runs outranks a broader one that might not.

## Accessibility & Inclusion

No product-specific requirement was established, and none is claimed. Ordinary hygiene —
readable contrast, keyboard-reachable controls, semantic structure — applies as craft, not
as a standard being certified against.
