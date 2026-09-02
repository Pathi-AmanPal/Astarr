# SAT-SA — Phase 1 PRD (Live Demo Build, Target: 15 Sept 2026)

**Status:** Locked scope for Phase 1. Do not add features beyond what is listed in this document without explicit instruction. Where this document conflicts with general best practice, this document wins for Phase 1.

**Ground truth:** This PRD implements a deliberately narrow subset of the full NCIIPC "Supervisory Analytics Tool for SOC Assessment (SAT-SA)" problem statement, scoped for a **live, judge-operated demo** on an offline machine. Full-scope items (ML layer, statistical peer-cohort analysis, offline Docker packaging, multi-format ingestion) are explicitly deferred — see Section 9.

---

## 1. Objective

Build a small, end-to-end, **genuinely functional** (not mocked) web application that:
1. Loads a fixed, pre-seeded synthetic dataset of SOC alert/case records on startup.
2. Detects **Execution Gap** and **Negative Space** findings using simple, deterministic logic.
3. Displays entities ranked by a transparent risk score.
4. Lets a user click into any entity, see which findings drove its score, and drill down to the exact source records behind each finding.
5. Runs with **zero internet/network dependency** at runtime.

**Primary success condition:** A judge can, unsupervised, click through the entire flow (entity list → entity detail → evidence) on a laptop with Wi-Fi turned off, and nothing errors, blanks, or crashes.

---

## 2. In-Scope User Story

> As an NCIIPC supervisor, I open the dashboard and immediately see which entities need attention, ranked by risk. I click the highest-risk entity and see exactly which findings caused its score — with a plain-language reason for each. I click into any finding and see the exact underlying alert/case records that triggered it, so I can trust the number is not a black box.

Single implicit user. No login, no roles, no multi-user concerns in Phase 1.

---

## 3. Data Model

Use **DuckDB**, single local file (`sat_sa.duckdb`), created and seeded automatically on first server start.

### 3.1 Table: `records` (flattened alert/case record — one row per alert)

| Field | Type | Notes |
|---|---|---|
| `record_id` | TEXT, PK | e.g. `"ALT-0001"` |
| `entity_id` | TEXT | FK to `entities.entity_id` |
| `asset_id` | TEXT | free text |
| `severity` | TEXT | one of `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `category` | TEXT | free text, e.g. `"Malware"`, `"Unauthorized Access"` |
| `opened_at` | TIMESTAMP | |
| `closed_at` | TIMESTAMP, nullable | |
| `escalated` | BOOLEAN | |
| `disposition` | TEXT | one of `TRUE_POSITIVE`, `FALSE_POSITIVE`, `BENIGN`, `UNRESOLVED` |
| `investigation_notes` | TEXT, nullable | |
| `closure_time_minutes` | FLOAT, nullable | **derived at ingestion**: `(closed_at - opened_at)` in minutes; `NULL` if `closed_at` is `NULL` |

### 3.2 Table: `entities`

| Field | Type | Notes |
|---|---|---|
| `entity_id` | TEXT, PK | e.g. `"CSE-01"` |
| `entity_name` | TEXT | display name, e.g. `"Entity Alpha Power Grid"` |
| `sector` | TEXT | flavor text only, not used in logic |

### 3.3 Table: `findings` (computed by the detection layer, not part of raw seed data)

| Field | Type | Notes |
|---|---|---|
| `finding_id` | TEXT, PK | e.g. `"F-0001"` |
| `entity_id` | TEXT | FK |
| `rule_id` | TEXT | one of `EG-001`, `EG-002`, `EG-003`, `NS-001` |
| `finding_type` | TEXT | `EXECUTION_GAP` or `NEGATIVE_SPACE` |
| `weight` | INTEGER | see Section 4 for exact values |
| `title` | TEXT | short human title, e.g. `"Rapid closure without escalation"` |
| `explanation` | TEXT | full plain-language sentence, templated per rule (see 4) |
| `evidence_record_ids` | TEXT | comma-separated `record_id`s this finding is based on |

Findings are **recomputed from scratch** every time the detection pipeline runs (on server start, and on demo reset — see Section 6). They are never hand-edited.

---

## 4. Detection Rules (exact specification — implement precisely as written)

### EG-001 — Rapid Closure Without Escalation
**Fires per matching record.**
```
WHERE severity IN ('HIGH', 'CRITICAL')
  AND closure_time_minutes IS NOT NULL
  AND closure_time_minutes < 2
  AND escalated = FALSE
```
- `weight = 35`
- `title = "Rapid closure without escalation"`
- `explanation` template: `"Alert {record_id} ({severity}) was closed in {closure_time_minutes} minutes with no escalation — below the 2-minute threshold used to flag superficial closure."`

### EG-002 — Critical Alert Without Escalation
**Fires per matching record.**
```
WHERE severity = 'CRITICAL'
  AND escalated = FALSE
```
- `weight = 25`
- `title = "Critical alert closed without escalation"`
- `explanation` template: `"Alert {record_id} was marked CRITICAL but has no escalation record, regardless of how quickly it was closed."`
- Note: this MAY fire on the same record as EG-001. Both findings are kept — this is intentional and realistic (two independent red flags on one record).

### EG-003 — Template / Duplicate Investigation Notes
**Fires per entity, using cases within that entity only.**
```
Group records by entity_id.
Within each entity, group by investigation_notes (case-insensitive, trimmed).
If a single investigation_notes value is shared by >= 3 distinct records in that entity:
    flag ONE finding for the entity (not one per record).
```
- `weight = 20`
- `title = "Repetitive / template-driven investigation notes"`
- `explanation` template: `"{count} cases in this entity share the exact same investigation notes text, suggesting superficial or template-driven review rather than genuine investigation."`
- `evidence_record_ids` = all matching record_ids for that duplicate group.
- Ignore NULL/empty `investigation_notes` when grouping (do not flag missing notes as duplicates).

### NS-001 — Below-Average Alert Volume (simplified Negative Space)
**Fires per entity. Computed once per detection run, across all entities in the dataset.**
```
total_count(entity) = COUNT(records WHERE entity_id = entity)
mean_count = AVERAGE(total_count across all entities)
std_count  = STDDEV(total_count across all entities)

IF total_count(entity) < (mean_count - 1.5 * std_count):
    flag entity
```
- `weight = 30`
- `title = "Alert volume significantly below dataset average"`
- `explanation` template: `"This entity generated {total_count} alerts, compared to a dataset average of {mean_count} — well below expectation for a comparable environment."`
- `evidence_record_ids` = all record_ids for that entity (so the evidence view can show "here is everything this entity submitted — notice how little there is").
- **Explicitly note in the UI** (small footer text on the finding's evidence view) that this is a simplified global-average comparison, and the full version (peer-cohort grouping by sector/size/criticality) is planned for the next phase. Do not claim peer-cohort comparison anywhere in Phase 1 UI copy.

---

## 5. Risk Scoring (exact formula for Phase 1)

```
entity_risk_score = MIN(100, SUM(weight of every finding for that entity))
```

- Simple, transparent, additive, capped at 100. No tiered/weighted-percentage formula in Phase 1 (that is a Phase 2 refinement — see Section 9).
- The entity list and entity detail screens MUST show this as a **visible breakdown** (list of contributing findings and their weights), never just the final number alone. This is non-negotiable — it is the core explainability requirement being demonstrated.

---

## 6. API Specification

Backend: **FastAPI**, served locally (e.g. `http://localhost:8000`). All responses JSON. No authentication.

| Method | Path | Description | Response shape |
|---|---|---|---|
| GET | `/api/health` | Liveness check | `{"status": "ok"}` |
| GET | `/api/entities` | List all entities, sorted by `risk_score` descending | `[{entity_id, entity_name, risk_score, finding_count}]` |
| GET | `/api/entities/{entity_id}` | Entity detail | `{entity_id, entity_name, risk_score, findings: [{finding_id, rule_id, finding_type, title, weight, explanation}]}` |
| GET | `/api/findings/{finding_id}/evidence` | Evidence for one finding | `{finding_id, title, explanation, records: [ full record objects ]}` |
| POST | `/api/demo/reset` | Wipes and re-seeds the fixed demo dataset, re-runs detection | `{"status": "reset_complete", "entities_loaded": N, "findings_generated": M}` |

**Explicitly NOT in Phase 1:** file upload endpoint, any endpoint accepting arbitrary user-supplied data. The dataset is fixed and server-seeded only.

---

## 7. Frontend Specification

**Stack:** React + Vite + TypeScript. Minimal styling (plain CSS or a lightweight utility approach) — visual polish is secondary to reliability in Phase 1. No charting library required.

### Screen 1 — Entity Risk List (`/`)
- Table columns: Rank, Entity Name, Risk Score (colored badge — green if `<30`, amber if `30–60`, red if `>60`), Finding Count.
- Sorted descending by risk score (server already returns it sorted; do not re-sort client-side in a way that could diverge).
- Each row is clickable → navigates to Screen 2 for that entity.
- Top-right: **"Reset Demo Data"** button → calls `POST /api/demo/reset`, then refetches the list. Must show a loading state while resetting and MUST NOT leave the page in a broken state if the call is slow.

### Screen 2 — Entity Detail (`/entities/:id`)
- Header: entity name + large risk score display.
- Two sections, clearly separated: **"Execution Gap Findings"** and **"Negative Space Findings"** (filter the entity's `findings` array by `finding_type` client-side).
- Each finding shown as a card: `title`, `weight`, a **"View Evidence"** button.
- If a section has zero findings, show a plain "No findings of this type" message — never an empty blank area.

### Screen 3 — Evidence View (route `/findings/:id`, or a modal — either is acceptable)
- Show the finding's `explanation` sentence prominently at the top.
- Below it, a table of every record in `records` (full fields: record_id, severity, opened_at, closed_at, closure_time_minutes, escalated, investigation_notes).
- For `NS-001` findings, add a small footer note: *"Simplified dataset-average comparison — peer-cohort grouping planned for next phase."*

### Global requirements
- No screen may ever render a raw JavaScript error, blank white page, or unhandled network-error state. Every API call must be wrapped with a loading state and an error state that shows a plain message and does not break navigation.
- The app must be fully usable with the machine's Wi-Fi disabled (no CDN font/icon/script loads at runtime — bundle everything).

---

## 8. Non-Functional Requirements

1. **MUST** run with zero outbound network calls at runtime. Verify explicitly by disabling Wi-Fi and re-running the full demo script (Section 10) before 15 Sept.
2. **MUST NOT** crash or dead-end on any click within the three defined screens.
3. API responses **MUST** return in under 1 second on the fixed demo dataset (target size: 6–8 entities, ~150–200 records total — trivial at this scale, stated here as an explicit acceptance bar).
4. The demo dataset **MUST** load automatically on first server start with no manual steps beyond starting the backend and frontend.
5. Detection **MUST** be deterministic — running `/api/demo/reset` repeatedly must always produce identical entities, findings, and scores from the same seed data.

---

## 9. Explicitly Out of Scope for Phase 1 (do not build these yet)

> **AMENDMENT 2026-09-02 — Isolation Forest and SHAP are no longer deferred.** By explicit
> instruction they are pulled into Phase 1 as a corroboration-only layer (`ML-001`,
> `finding_type = ML_CORROBORATION`, weight 10), evaluated solely for entities that already
> carry a rule- or statistics-based finding. `scikit-learn` and `shap` are added to
> `backend/requirements.txt` as an approved amendment to §11's dependency lock. Every other
> item in this section remains deferred. See PRODUCT.md for the full record.

> **AMENDMENT 2026-09-02 (Phase 2, Day 1) — YAML-configurable rule thresholds are no longer
> deferred.** Every rule weight, severity list, disposition list and numeric threshold now
> lives in `backend/rules.yaml`, loaded once at import by `backend/config.py`. This was a
> **pure refactor**: the YAML transcribes the Phase 1 constants exactly, and the proof is
> that `verify.py` produces byte-identical output before and after, and the full findings
> table (all 18 findings, weights, explanations and evidence ids) is byte-identical too.
> The loader has **no default values** — a missing or malformed key raises `ConfigError` at
> startup rather than letting a rule run against a silently substituted threshold.
> `PyYAML>=6.0` is added to `backend/requirements.txt` under the same §11 amendment process
> used for `scikit-learn`/`shap`.

- ~~Isolation Forest / any ML model / SHAP explainability layer~~ — **implemented, see amendment above**
- ~~YAML-configurable rule thresholds (hardcoded constants in code are fine for Phase 1)~~ — **implemented in Phase 2, see amendment below**
- Multi-format ingestion (JSON, DB export, API ingestion) or any file upload UI
- Docker / offline image packaging (`uvicorn` + `npm run dev` run locally is sufficient for this phase)
- Authentication, multi-user roles, permissions
- Peer-cohort grouping for Negative Space (sector/size/criticality-based) — Phase 1 uses the simplified global-average version in Section 4 (NS-001) only
- Trend analysis, time-series charts, historical comparison across multiple analysis runs
- Rule/model versioning, analysis-run history
- Weighted-tier scoring formula (e.g. 35% rules + 30% stats + …) — Phase 1 uses the simple additive-and-cap formula in Section 5 only

These are documented, planned, and already described in the project's full architecture (see prior deliverables) — they belong to the 36-hour national-round build, not this phase. Do not implement them now even partially; a half-built version of any of these is worse for the live demo than not having it, because it increases surface area for something to break on stage.

---

## 10. Demo Script / Acceptance Criteria (Definition of Done)

The build is considered **done** only when the following sequence has been performed **successfully, three consecutive times in a row, with Wi-Fi disabled**, on the exact machine that will be used for the live demo:

1. Start backend and frontend. Open the app. Entity list appears, ranked by risk score, highest first.
2. Click the highest-risk entity. Detail page shows a score breakdown with at least one Execution Gap finding and at least one Negative Space finding.
3. Click "View Evidence" on the Execution Gap finding. The evidence table shows the exact record(s) — visually confirm `closure_time_minutes` is under 2 and `escalated` is false, matching the rule's stated condition.
4. Go back. Click "View Evidence" on the Negative Space finding. The evidence view shows the entity's alert count and the dataset average, matching the explanation text.
5. Return to the entity list. Click "Reset Demo Data." The list reloads with identical rankings (proving determinism).
6. Repeat steps 1–5 end to end without any error, blank screen, or crash.

If any step fails on any of the three consecutive runs, the build is **not done** — fix and re-run the full sequence from step 1, not just the failing step.

---

## 11. Locked Tech Stack for Phase 1

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| Data processing | Pandas (for seed-data loading/derivation) |
| Database | DuckDB, single local file |
| Frontend | React, Vite, TypeScript |
| Styling | Plain CSS or minimal utility classes — no design system dependency |
| Charts | None required in Phase 1 |
| Packaging | None — run directly via `uvicorn` and `npm run dev` / `vite preview` |

Do not substitute or add libraries beyond this list without explicit instruction.

---

## 12. Exact Demo Dataset Specification (implements Section 3)

The seed data **MUST** be generated by a deterministic script (no `random`/RNG calls) so the dataset — and therefore every finding and score — is byte-identical on every run. Use simple index-based loops for timestamps and filler content, not randomness.

**8 entities, fixed IDs and names:**

| entity_id | entity_name | sector |
|---|---|---|
| CSE-01 | Entity Alpha — Power Grid | Energy |
| CSE-02 | Entity Bravo — Telecom | Telecom |
| CSE-03 | Entity Charlie — Banking | Banking |
| CSE-04 | Entity Delta — Healthcare | Healthcare |
| CSE-05 | Entity Echo — Transport | Transport |
| CSE-06 | Entity Foxtrot — Water Utility | Utilities |
| CSE-07 | Entity Golf — Defence Logistics | Defence |
| CSE-08 | Entity Hotel — Insurance | Finance |

**Per-entity record composition (total 158 records):**

| entity_id | Total records | Composition |
|---|---|---|
| CSE-01 | 25 | 3 records planted for **EG-001 + EG-002** (severity=`CRITICAL`, `closed_at - opened_at` ≈ 1.4 min, `escalated=FALSE`, `disposition=UNRESOLVED`, distinct short `investigation_notes` each) + 4 records planted for **EG-003** (severity=`HIGH`, closure time ≈ 45 min, `escalated=TRUE`, `disposition=TRUE_POSITIVE`, `investigation_notes` identical exact string `"Reviewed, closed as per standard procedure."` on all 4) + 18 filler "clean" records (see Filler Rule below). This entity must end up **highest risk score** — use it as the primary demo entity. |
| CSE-02 | 4 | All filler "clean" records only (see Filler Rule). Deliberately low volume — this is the **Negative Space** demo entity. |
| CSE-03 | 24 | Filler "clean" records only. |
| CSE-04 | 22 | Filler "clean" records only. |
| CSE-05 | 23 | 1 record planted for **EG-002 only** (severity=`CRITICAL`, `escalated=FALSE`, closure time ≈ 15 min — i.e. ≥ 2 min so EG-001 does **not** fire, only EG-002) + 22 filler "clean" records. Use this to demonstrate a second, distinct entity with a single lower-weight finding. |
| CSE-06 | 20 | Filler "clean" records only. |
| CSE-07 | 21 | Filler "clean" records only. |
| CSE-08 | 19 | Filler "clean" records only. |

**Filler Rule (applies to every "clean" record above):** severity cycles deterministically through `LOW, MEDIUM, HIGH` (never `CRITICAL` in filler records, to avoid accidentally triggering EG-002); `closure_time_minutes` between 10 and 120 (never `< 2`); `escalated = TRUE` whenever severity is `HIGH`, otherwise alternate `TRUE`/`FALSE`; `investigation_notes` either `NULL` or a short unique string per record (e.g. include the `record_id` in the text so no two filler records ever accidentally match and trigger EG-003); `disposition` cycles deterministically through `TRUE_POSITIVE, FALSE_POSITIVE, BENIGN`. `opened_at` values increment deterministically (e.g. one record every 6 hours starting from a fixed anchor date) — do not use `NOW()` or any wall-clock-dependent value anywhere in seed generation, so the dataset (and therefore every score) never silently changes from one demo run to the next calendar day.

**Verification the agent MUST perform after generating this dataset** (do not skip): compute `mean` and `population standard deviation` of total alert count per entity across all 8 entities, and confirm `CSE-02`'s count is below `mean − 1.5 × stddev` (it must be, by construction, since 4 is far below the other entities' 19–25 range) — this is what makes NS-001 fire correctly on CSE-02 and nowhere else. If a different set of counts is used for any reason, re-verify this condition holds before finalizing.

This dataset must be embedded directly in the seeding code (e.g. a Python function that builds these rows programmatically per the table above) — not stored as an external CSV that requires a manual load step, per NFR #4.

---

## 13. Repository Structure

```
sat-sa/
├── backend/
│   ├── main.py            # FastAPI app, route definitions
│   ├── seed.py             # deterministic dataset generation (Section 12)
│   ├── detection.py        # EG-001/002/003, NS-001 rule implementations (Section 4)
│   ├── scoring.py          # risk score calculation (Section 5)
│   ├── db.py                # DuckDB connection + schema setup (Section 3)
│   ├── models.py            # Pydantic request/response models
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── EntityList.tsx
│   │   │   ├── EntityDetail.tsx
│   │   │   └── EvidenceView.tsx
│   │   ├── api.ts           # fetch wrapper for backend calls
│   │   └── App.tsx           # routing
│   └── package.json
└── README.md                 # exact run instructions (Section 14)
```

---

## 14. Setup & Run Instructions (must work exactly as written)

**Backend:**
```
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
On startup, `main.py` MUST call the seeding logic automatically if `sat_sa.duckdb` does not yet exist or is empty, so no manual seeding step is ever required.

**Frontend:**
```
cd frontend
npm install
npm run dev
```
Frontend dev server MUST point to `http://localhost:8000` for all API calls (hardcode this as a constant in `api.ts` — no environment-variable setup required for Phase 1).

**`requirements.txt` (pin to these or newer compatible minor versions):**
```
fastapi>=0.110
uvicorn>=0.29
pydantic>=2.6
duckdb>=0.10
pandas>=2.2
```

**`package.json` key dependencies:** `react`, `react-dom`, `react-router-dom`, `vite`, `typescript` — no additional UI/chart libraries per Section 11.

---

## 15. Error Handling & Edge Cases (must be explicitly implemented, not left to default framework behavior)

- `GET /api/entities/{entity_id}` with an unknown `entity_id` → HTTP 404 with JSON `{"error": "Entity not found"}`. Frontend must catch this and show an inline "Entity not found" message with a link back to the list — never a blank page.
- `GET /api/findings/{finding_id}/evidence` with an unknown `finding_id` → HTTP 404, same pattern.
- `POST /api/demo/reset` failing for any reason → HTTP 500 with a JSON error message; frontend must show a retry-able inline error banner on the list page, not a crash.
- Backend unreachable (server not started, wrong port) → every frontend page must show a clear "Cannot reach backend — is it running on localhost:8000?" message instead of an unhandled fetch exception.
- Empty findings list for an entity (should not happen for the 8 seeded entities, but must be handled defensively) → show "No findings of this type" text, per Section 7, Screen 2.

---

## 16. Minimal UI Copy

- App/browser tab title: **"SAT-SA — Supervisory Analytics"**
- Entity list page header: **"Entities Requiring Supervisory Attention"**
- Entity detail page score label: **"Supervisory Risk Score"**
- Reset button label: **"Reset Demo Data"**

No further branding, logos, or theming required for Phase 1 — functional clarity over visual polish.
