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

Four rules, thresholds now read from `backend/rules.yaml` (see the Phase 2 amendment
below; they were hardcoded through Phase 1): `EG-001` rapid closure without escalation (weight 35,
per record), `EG-002` critical alert without escalation (25, per record), `EG-003`
repetitive/template investigation notes (20, per entity, ≥3 records sharing notes),
`NS-001` below-average alert volume (30, per entity, below `mean − 1.5 × stddev`,
against the entity's sector cohort where that cohort has ≥ 5 members, otherwise against
the global baseline — see the peer-cohort amendment below).
EG-001 and EG-002 may both fire on one record; keeping both is intentional.

`ML-001` ML corroboration (10, per entity, only where an EG or NS finding already exists).

~~Score is `MIN(100, SUM(weights))` — simple, additive, capped.~~ Superseded by the
weighted-tier formula; see the Phase 2 amendment below.

Findings are recomputed from scratch on every detection run and are never hand-edited.

**Expansion to ~~six~~ seven detection rules (confirmed 2026-09-02; count corrected
2026-09-03).** Three rules added to the four the PRD specifies, giving seven deterministic
rules — eight findings sources counting `ML-001`, which is corroboration rather than a
detection rule. Each new rule inherits the
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

**Dataset expansion to 12 entities / 248 records (confirmed 2026-09-02, recorded here
2026-09-03).** Four clean entities were appended — `CSE-09` Entity India (Aviation, 22),
`CSE-10` Entity Juliet (Oil & Gas, 24), `CSE-11` Entity Kilo (Municipal Services, 21),
`CSE-12` Entity Lima (Space Research, 23). Appended **after** `CSE-08` on purpose, so every
existing record keeps its id (`ALT-0001`..`ALT-0158`) and every existing assertion holds
unchanged. They add no findings: their job is to thicken the peer group for NS-001's
baseline and the Isolation Forest's feature space. The margin check in the standing rule
below is what was run to confirm the expansion was safe in both directions, and PRD §12
carries the matching amendment.

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

### YAML-configurable rule thresholds (Phase 2 amendment, 2026-09-02)

PRD §9 deferred YAML configuration to Phase 2. That deferral is now **discharged**. Every
rule weight, severity list, disposition list and numeric threshold lives in
`backend/rules.yaml` and is read once at import time by `backend/config.py`.

**This was a pure refactor, and the regression proof is the point of it.** The YAML
transcribes the Phase 1 constants byte for byte, and two independent checks confirm nothing
moved: `verify.py` output is character-identical before and after, and a full dump of the
findings table — all 18 findings with their weights, titles, explanations and evidence
record ids, plus the ranked entity list — is byte-identical between the pre-refactor and
post-refactor code paths. Externalising configuration is exactly the kind of change that
looks safe and quietly shifts a threshold; this is the evidence that it did not.

**The loader has no default values, on purpose.** A missing, malformed or absent key raises
`ConfigError` at startup. A detection rule that silently falls back to a plausible-looking
threshold is worse than one that refuses to start: the demo would run, the numbers would be
wrong, and nothing on stage would say so. `rules.yaml` is resolved relative to `config.py`,
not the process working directory, so `python verify.py`, `uvicorn main:app` from the repo
root, and an import from a test directory all read the same file.

`ML-001`'s weight moved into the same file rather than staying in `ml.py`. A weight defined
in two places is a weight that will eventually disagree with itself.

`PyYAML>=6.0` joins `backend/requirements.txt` under the same approved-amendment process
used for `scikit-learn` and `shap`. It installs once and runs offline like everything else.

### Weighted-tier risk scoring (Phase 2 amendment, 2026-09-02)

PRD §5's additive formula is **superseded, not deleted**. It is struck in both documents
because it is the published Phase 1 behaviour and the record of what changed matters more
than a tidy document.

```
EG = MIN(100, SUM(EXECUTION_GAP    weights))
NS = MIN(100, SUM(NEGATIVE_SPACE   weights))
ML = MIN(100, SUM(ML_CORROBORATION weights))

risk_score = 0.45*EG + 0.40*NS + 0.15*ML
```

Each tier is capped at 100 **individually, before weighting**. Tiers key off
`finding_type`, not rule-id prefix, so a badly named future rule cannot land in the wrong
tier.

**Why no outer cap is needed.** The three weights sum to exactly 1.00, so the score is a
convex combination of three values each ≤ 100, and therefore ≤ 100 itself. The guarantee
depends entirely on that sum, which is invisible in the arithmetic and easy to break by
tuning one coefficient — so it is asserted at startup in `config.py` and again,
independently, in `verify.py`. Tier weights live in `rules.yaml` alongside every other
weight.

**The attainable maximum is 86.5, not 100 — say so, never imply otherwise.** The ML tier
cannot exceed 10, because `ml_corroboration` emits at most one `ML-001` per entity at
weight 10. The score is a **comparable ranking scale, not a percentage**. The Phase 1 demo
line "100, capped from 250" is gone; the equivalent moment is now CSE-01's Execution Gap
tier capping from 215 to 100 before weighting, which is visible in the tier calculation.

**`risk_score` is a float.** Tier weighting produces halves and quarters, and Python's
`round()` is banker's rounding — it would send 56.5 to 56 while sending 13.5 to 14. Shown
to two decimals everywhere, because a workpaper column mixing "18" and "24.75" cannot be
footed by eye.

**One ranking change, deliberate.** CSE-03 rises above CSE-02 (3rd and 4th). Both scored 40
additively and were separated only by the `entity_id` tiebreak; CSE-03's 40 is all
Execution Gap (×0.45 = 18.00) against CSE-02's Negative Space plus ML (×0.40 and ×0.15 =
13.50). The old equality was an artifact of flat addition. Everything else holds: CSE-01
strictly first, positions 2 and 5–12 unchanged, and the amendment **removes** the 40-point
tie rather than creating one. Seven entities still score zero, so the `entity_id ASC`
tiebreak stays load-bearing.

**Explainability had to be rebuilt, not merely preserved.** §5 requires the score shown as
a breakdown a reader can foot. Additively, listing finding weights satisfied that because
they summed to the score. Under weighted tiers **they no longer do** — so the detail screen
gained a tier calculation (raw → individual cap → × weight → contribution → total). Without
it the headline number would be unverifiable from anything on screen, which would have
broken §5 silently while every test still passed.

**UI band thresholds were re-cut, and this is a judgement call worth revisiting.** The
list's exception/caution/clear bands were 60 and 30 on the additive 0–100 scale; they are
now 50 and 10. This is not a naive rescale — the old score conflated tiers, so 40 from
Negative Space and 40 from Execution Gap looked identical. 50/10 is the pair that preserves
the existing grouping exactly (CSE-01 alone in exception; CSE-05, CSE-03, CSE-02 in
caution; CSE-06 and the zero-scoring entities clear), so no entity silently changes colour
as a side effect of the formula change. Chosen to preserve intent, not derived from first
principles, and kept in two named constants in `EntityList.tsx`.

### Peer-cohort baseline for NS-001 (Phase 2 amendment, 2026-09-02)

PRD §9 deferred peer-cohort grouping to Phase 2. The infrastructure is now built, and
it ships with an explicit **validity gate**: an entity is compared against its own
sector cohort **only where that cohort has at least 5 members**, and otherwise falls
back to the global baseline — saying so, in words, inside the finding itself.

**At 12 entities nothing qualifies, and that is the honest answer.** The dataset has
12 entities across **12 distinct sectors**, so every cohort holds exactly one member.
Every entity therefore uses the global baseline today, and NS-001's behaviour is
byte-for-byte what Phase 1 shipped. Cohorting activates on its own the moment sectors
genuinely repeat — no code change, no redeploy.

**Why a gate rather than just cohorting.** This was measured before it was built, not
assumed:

| grouping | cohorts | CSE-02 still flagged? | clean entity crossing in | tightest clean margin |
|---|---|---|---|---|
| global (today) | 1 × 12 | yes | none | **+6.28** |
| by sector | 12 × 1 | **no** | — | 0.00 (dead) |
| domain merge (5 groups) | 3,2,3,2,2 | **no** | none | +0.22 |
| two-way split (7/5) | 7, 5 | yes | none | **+0.21** |
| size bands | 1, 11 | **no** | **CSE-08** | −0.56 |

- **At n=1, σ = 0**, so `count < mean − 1.5×0` reduces to `count < count` — never true.
  Sector cohorting would not weaken NS-001, it would **switch it off entirely**.
  `verify.py` proves this empirically: with the gate disabled, NS-001 returns zero
  findings.
- **At n=2**, both members sit exactly one σ from their own mean by construction, so any
  threshold drawn from the pair is arithmetic rather than evidence.
- The domain merge looks reasonable and is the worst of the options: pairing Telecom
  (CSE-02, 4 alerts) with Space Research (CSE-12, 23) gives σ = 9.50 and a threshold of
  **−0.75**. A negative alert count is unreachable, so **CSE-02 would be silently
  exonerated** — cleared by being paired with one dissimilar peer.
- The two-way split is the only shape where every cohort reaches 5, and it still fails
  the standing rule: the clean group's counts cluster so tightly that σ falls to 1.67
  and the threshold rises to 19.79, leaving **CSE-06 at 20 alerts just 0.21 above the
  line**. One record's difference turns a clean entity into a false finding. The
  ≥ 3.0 margin `verify.py` asserts would fail.
- Size banding is **circular** — it groups entities by volume and then tests volume —
  and already produces a false positive on CSE-08 at −0.56.

**Say this on stage, do not hide it.** Asked "does this really use peer groups?", the
answer is:

> *"Yes — the cohort comparison is real, and every cohort is checked for statistical
> validity first: a minimum of 5 members. In this dataset of 12 entities across 12
> unique sectors no cohort reaches that, so the system falls back to the conservative
> global baseline and says so in the finding. As the dataset scales, cohorting activates
> by itself."*

A limitation that is measured, gated in code, stated in the finding text and defensible
in one sentence is a **strength**. A cohort of one dressed up as a peer comparison would
undermine the evidence-graph credibility that the whole tool rests on. This is the
"claim exactly what is implemented" principle applied to statistics.

**The finding text carries the audit trail**, so the honesty survives without the
document:

> This entity generated 4 alerts, compared to the dataset average of 20.67 alerts across
> all 12 entities — well below expectation for a comparable environment. Peer-cohort
> comparison was not available: this entity's Telecom group holds 1 entity, below the
> 5-entity minimum for a statistically valid baseline, so the more conservative global
> baseline was used.

`cohort_by` and `min_cohort_size` live in `rules.yaml`. `cohort_by` names a column on
`entities` and is checked against an allowlist rather than interpolated into SQL on
trust; `min_cohort_size` below 2 is rejected at startup, because that is the value that
would silently disable the rule.

### Multi-format ingestion: designed, deliberately not live-exposed (2026-09-02)

**There is no upload endpoint and no upload UI, in Phase 2 either.** This is a decision,
not an omission, and it needs a prepared one-sentence answer rather than a defensive one.

The ingestion *architecture* is real and documented: the record schema is format-agnostic,
and `closure_time_minutes` is derived at ingestion rather than trusted from a source, which
is exactly the seam a JSON / DB-export / API loader plugs into. What does not exist is a
path a visitor can feed arbitrary bytes into.

**Why it stayed cut when Phase 2 widened the scope.** Every other feature in this build
rests on a seed-based regression proof — a fixed dataset, a byte-for-byte diff, a claim
that can be checked. **Untrusted input is the one thing that proof cannot cover.** Parsing,
encoding, malformed rows, size limits and partial failures are a surface with no fixed
dataset to compare against, and a judge operating the tool live *will* hand it a bad file.
Shipping it would mean carrying, on stage, the one capability whose correctness could not
be demonstrated the way everything else here can.

Phase 2's remaining capacity went to **offline/Docker packaging** instead, which the
problem statement scores directly under deployment requirements, and which can be verified
honestly — by actually disconnecting the network.

**If a judge asks where file upload is:**

> *"The ingestion architecture is designed and documented — the schema is format-agnostic
> and derives its computed fields at load time. We deliberately did not expose a live
> upload path in the demo build: it is the one component we could not put behind the same
> regression proof as every rule and score here, so rather than demo something we cannot
> verify, the operator loads data server-side. The deployment packaging we did build is
> testable, and we tested it with the network off."*

That is the "claim exactly what is implemented" principle applied to scope, not just to
wording.

### Explicitly out of scope for Phase 1

~~YAML-configurable thresholds~~ and ~~the weighted-tier scoring formula~~ (**both
implemented in Phase 2, see amendments above**), multi-format
ingestion, any file-upload UI or endpoint accepting user-supplied data, ~~Docker/offline
image packaging~~ (**being built in Phase 2**), authentication and roles, ~~peer-cohort grouping for Negative Space~~
(**infrastructure implemented in Phase 2 behind a validity gate, see amendment above**),
trend analysis and time-series charts, and rule/model versioning and run history. These are documented and planned, not forgotten — they
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
- **A fully specified synthetic dataset** (PRD §12): ~~8 entities, 158 records~~
  **12 entities, 248 records**, with the demo findings planted by construction. `CSE-01`
  (25 records) carries ~~EG-001, EG-002, and EG-003~~ **EG-001 ×3, EG-002 ×3, EG-003,
  EG-004, NS-002 and ML-001** and must end up highest-risk — the primary demo entity, at
  56.50 under weighted tiers. `CSE-02` (4 records) is the Negative Space entity **(NS-001,
  ML-001)**. `CSE-05` (23 records) carries ~~a single EG-002~~ **EG-002 and EG-004 ×2** to
  show a second, lower-weight profile. **`CSE-03` carries EG-004 and EG-005; `CSE-06`
  carries EG-004.** The remaining ~~five~~ **seven** are clean filler and score zero —
  `CSE-04`, and `CSE-07` through `CSE-12`. 18 findings in total.

### What does not exist, and must not be fabricated

- **No real SOC data, no real entity, no customer, no deployment.** The dataset is
  synthetic and explicitly labelled as a demo dataset.
- **No peer-cohort analysis is in effect on this dataset — though the capability exists.**
  `NS-001` performs a cohort comparison only where the cohort has ≥ 5 members; with 12
  entities across 12 distinct sectors nothing qualifies, so every finding uses the global
  baseline. Never claim a peer comparison that did not happen: the finding text and the
  evidence-view footnote both state which baseline was used and why.
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
