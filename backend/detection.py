"""Detection rules (PRD Section 4, expanded to six rules 2026-09-02).

Thresholds are no longer hardcoded: PRD Section 9 deferred YAML configuration to
Phase 2, and `rules.yaml` (via `config.py`) is that deferral discharged. Every value
below is read from that file at import time; none of them has a fallback default.
Findings are recomputed from scratch on every run and never hand-edited.

Determinism: every rule iterates entities and records in sorted order, and finding ids
are assigned in a fixed rule sequence, so the same seed always produces byte-identical
findings in the same order.
"""

from __future__ import annotations

import math
import statistics

import config
import ml
from ml import ML_RULE_ID, ml_corroboration

EXECUTION_GAP = "EXECUTION_GAP"
NEGATIVE_SPACE = "NEGATIVE_SPACE"

# --- Rule thresholds (from rules.yaml, resolved once at import) -------------------
# These module-level names are kept deliberately: they are the rules' vocabulary, and
# verify.py imports two of them. What changed is where the numbers come from, not what
# any of them means.
EG001_SEVERITIES = config.severities("EG-001")
EG001_MAX_CLOSURE_MINUTES = config.param("EG-001", "max_closure_minutes")
EG001_REQUIRE_UNESCALATED = config.param("EG-001", "require_unescalated")

EG002_SEVERITIES = config.severities("EG-002")
EG002_REQUIRE_UNESCALATED = config.param("EG-002", "require_unescalated")

EG003_MIN_DUPLICATES = config.param("EG-003", "min_duplicates")

EG004_SEVERITIES = config.severities("EG-004")
EG004_DISPOSITIONS = config.dispositions("EG-004")
EG004_REQUIRE_EMPTY_NOTES = config.param("EG-004", "require_empty_notes")

EG005_MIN_BURST_SIZE = config.param("EG-005", "min_burst_size")

NS001_STDDEV_MULTIPLIER = config.param("NS-001", "stddev_multiplier")

# Peer-cohort baseline. `cohort_by` names a column on `entities`, so it is checked
# against an allowlist rather than interpolated into SQL on trust -- rules.yaml is
# configuration, but it is still a file that ends up inside a query.
NS001_COHORT_BY = config.param("NS-001", "cohort_by")
NS001_MIN_COHORT_SIZE = config.param("NS-001", "min_cohort_size")

COHORT_COLUMNS = {"sector"}
if NS001_COHORT_BY not in COHORT_COLUMNS:
    raise config.ConfigError(
        f"rules.NS-001.cohort_by must be one of {sorted(COHORT_COLUMNS)}, "
        f"got {NS001_COHORT_BY!r}"
    )
if NS001_MIN_COHORT_SIZE < 2:
    # At n=1 sigma is 0 and "count < mean - k*0" is "count < count" -- never true, so
    # the rule would silently stop firing entirely rather than erroring.
    raise config.ConfigError(
        f"rules.NS-001.min_cohort_size must be at least 2, got {NS001_MIN_COHORT_SIZE}"
    )

NS002_MIN_RECORDS = config.param("NS-002", "min_records")

# A category is "expected" when at least this fraction of entities report it.
# Proportional, never absolute: the rule previously hardcoded 6, which was 75% of 8.
# Left absolute, that same 6 silently becomes a 50% bar at 12 entities and a 25% bar
# at 24 -- the rule weakening as the dataset grows, with nothing to catch it.
NS002_MIN_REPORTING_FRACTION = config.param("NS-002", "min_reporting_fraction")


def ns002_min_reporting(entity_count: int) -> int:
    """Entities that must report a category before absence counts as a blind spot."""
    return math.ceil(NS002_MIN_REPORTING_FRACTION * entity_count)


WEIGHTS = config.WEIGHTS


def _fetch_records(con) -> list[dict]:
    rows = con.execute(
        """
        SELECT record_id, entity_id, severity, category, opened_at, closed_at,
               escalated, disposition, investigation_notes, closure_time_minutes
        FROM records
        ORDER BY record_id
        """
    ).fetchall()
    cols = [
        "record_id", "entity_id", "severity", "category", "opened_at", "closed_at",
        "escalated", "disposition", "investigation_notes", "closure_time_minutes",
    ]
    return [dict(zip(cols, r)) for r in rows]


def _entity_cohorts(con) -> dict[str, str]:
    """entity_id -> its cohort key. Column name is allowlisted at import."""
    rows = con.execute(
        f"SELECT entity_id, {NS001_COHORT_BY} FROM entities ORDER BY entity_id"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def _entity_ids(con) -> list[str]:
    return [r[0] for r in con.execute("SELECT entity_id FROM entities ORDER BY entity_id").fetchall()]


def _fmt(value: float) -> str:
    """Trim a float for display: 1.4 not 1.4000000000000001, 20 not 20.0."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


# --- EG-001 ----------------------------------------------------------------------
def eg001(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        if (
            r["severity"] in EG001_SEVERITIES
            and r["closure_time_minutes"] is not None
            and r["closure_time_minutes"] < EG001_MAX_CLOSURE_MINUTES
            and not (EG001_REQUIRE_UNESCALATED and r["escalated"])
        ):
            out.append({
                "entity_id": r["entity_id"],
                "rule_id": "EG-001",
                "finding_type": EXECUTION_GAP,
                "title": "Rapid closure without escalation",
                "explanation": (
                    f"Alert {r['record_id']} ({r['severity']}) was closed in "
                    f"{_fmt(r['closure_time_minutes'])} minutes with no escalation - below the "
                    f"{EG001_MAX_CLOSURE_MINUTES}-minute threshold used to flag superficial closure."
                ),
                "evidence_record_ids": [r["record_id"]],
            })
    return out


# --- EG-002 ----------------------------------------------------------------------
def eg002(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        if r["severity"] in EG002_SEVERITIES and not (
            EG002_REQUIRE_UNESCALATED and r["escalated"]
        ):
            out.append({
                "entity_id": r["entity_id"],
                "rule_id": "EG-002",
                "finding_type": EXECUTION_GAP,
                "title": "Critical alert closed without escalation",
                "explanation": (
                    f"Alert {r['record_id']} was marked CRITICAL but has no escalation record, "
                    f"regardless of how quickly it was closed."
                ),
                "evidence_record_ids": [r["record_id"]],
            })
    return out


# --- EG-003 ----------------------------------------------------------------------
def eg003(records: list[dict], entity_ids: list[str]) -> list[dict]:
    out = []
    for entity_id in entity_ids:
        groups: dict[str, list[str]] = {}
        for r in records:
            if r["entity_id"] != entity_id:
                continue
            notes = r["investigation_notes"]
            if notes is None or not notes.strip():
                continue  # missing notes are not duplicates
            groups.setdefault(notes.strip().lower(), []).append(r["record_id"])

        for key in sorted(groups):
            ids = sorted(groups[key])
            if len(ids) >= EG003_MIN_DUPLICATES:
                out.append({
                    "entity_id": entity_id,
                    "rule_id": "EG-003",
                    "finding_type": EXECUTION_GAP,
                    "title": "Repetitive / template-driven investigation notes",
                    "explanation": (
                        f"{len(ids)} cases in this entity share the exact same investigation notes "
                        f"text, suggesting superficial or template-driven review rather than "
                        f"genuine investigation."
                    ),
                    "evidence_record_ids": ids,
                })
    return out


# --- EG-004 ----------------------------------------------------------------------
def eg004(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        notes = r["investigation_notes"]
        if (
            r["severity"] in EG004_SEVERITIES
            and r["disposition"] in EG004_DISPOSITIONS
            and not (EG004_REQUIRE_EMPTY_NOTES and notes is not None and notes.strip())
        ):
            out.append({
                "entity_id": r["entity_id"],
                "rule_id": "EG-004",
                "finding_type": EXECUTION_GAP,
                "title": "Dismissed without recorded justification",
                "explanation": (
                    f"Alert {r['record_id']} ({r['severity']}) was dismissed as "
                    f"{r['disposition']} with no investigation notes recorded - a serious alert "
                    f"closed without any written justification."
                ),
                "evidence_record_ids": [r["record_id"]],
            })
    return out


# --- EG-005 ----------------------------------------------------------------------
def eg005(records: list[dict], entity_ids: list[str]) -> list[dict]:
    out = []
    for entity_id in entity_ids:
        groups: dict[str, list[str]] = {}
        for r in records:
            if r["entity_id"] != entity_id or r["closed_at"] is None:
                continue
            minute = r["closed_at"].replace(second=0, microsecond=0)
            groups.setdefault(minute.isoformat(sep=" "), []).append(r["record_id"])

        for minute in sorted(groups):
            ids = sorted(groups[minute])
            if len(ids) >= EG005_MIN_BURST_SIZE:
                out.append({
                    "entity_id": entity_id,
                    "rule_id": "EG-005",
                    "finding_type": EXECUTION_GAP,
                    "title": "Bulk closure burst",
                    "explanation": (
                        f"{len(ids)} alerts in this entity were all closed within the same minute "
                        f"({minute}), consistent with bulk queue-clearing rather than individual "
                        f"review."
                    ),
                    "evidence_record_ids": ids,
                })
    return out


# --- NS-001 ----------------------------------------------------------------------
def _baseline(values: list[int]) -> tuple[float, float, float]:
    """mean, population sigma, and the low-volume threshold for a set of counts.

    pstdev, not stdev. PRD Section 12 specifies population standard deviation, and
    DuckDB's STDDEV() is stddev_samp -- an easy mismatch to introduce accidentally.
    """
    mean = statistics.fmean(values)
    std = statistics.pstdev(values)
    return mean, std, mean - NS001_STDDEV_MULTIPLIER * std


def ns001(records: list[dict], entity_ids: list[str],
          cohorts: dict[str, str] | None = None) -> list[dict]:
    """Alert volume below the peer baseline, with an explicit validity gate.

    An entity is compared against its own cohort ONLY where that cohort has at least
    `min_cohort_size` members. Otherwise it falls back to the global baseline, and the
    finding says so in words.

    The fallback is the honest half of this rule, not a workaround. A cohort of one has
    sigma = 0, which turns the test into "count < count" and silently switches the rule
    off; a cohort of two places both members exactly one sigma from their own mean by
    construction, so any threshold drawn from it is arithmetic rather than evidence.
    Comparing against a group too small to have a distribution is not a peer comparison,
    it is a number that looks like one.
    """
    cohorts = cohorts or {}
    counts = {eid: 0 for eid in entity_ids}
    for r in records:
        counts[r["entity_id"]] = counts.get(r["entity_id"], 0) + 1

    global_mean, _global_std, global_threshold = _baseline(
        [counts[eid] for eid in entity_ids]
    )

    members: dict[str, list[str]] = {}
    for eid in entity_ids:
        members.setdefault(cohorts.get(eid, ""), []).append(eid)

    out = []
    for entity_id in entity_ids:
        cohort = cohorts.get(entity_id, "")
        peers = sorted(members.get(cohort, []))

        if cohort and len(peers) >= NS001_MIN_COHORT_SIZE:
            mean, _std, threshold = _baseline([counts[p] for p in peers])
            basis = (
                f"its {cohort} peer cohort ({len(peers)} entities, average "
                f"{_fmt(mean)} alerts)"
            )
            qualifier = ""
        else:
            mean, threshold = global_mean, global_threshold
            basis = f"the dataset average of {_fmt(mean)} alerts across all {len(entity_ids)} entities"
            # State the fallback rather than letting a global comparison read as a peer
            # one. This sentence is the rule's own audit trail.
            qualifier = (
                f" Peer-cohort comparison was not available: this entity's "
                f"{cohort or 'cohort'} group holds "
                f"{len(peers)} {'entity' if len(peers) == 1 else 'entities'}, below the "
                f"{NS001_MIN_COHORT_SIZE}-entity minimum for a statistically valid "
                f"baseline, so the more conservative global baseline was used."
            )

        if counts[entity_id] < threshold:
            ids = sorted(r["record_id"] for r in records if r["entity_id"] == entity_id)
            out.append({
                "entity_id": entity_id,
                "rule_id": "NS-001",
                "finding_type": NEGATIVE_SPACE,
                "title": "Alert volume significantly below peer baseline",
                "explanation": (
                    f"This entity generated {counts[entity_id]} alerts, compared to "
                    f"{basis} - well below expectation for a comparable environment."
                    f"{qualifier}"
                ),
                "evidence_record_ids": ids,
            })
    return out


# --- NS-002 ----------------------------------------------------------------------
def ns002(records: list[dict], entity_ids: list[str]) -> list[dict]:
    by_entity: dict[str, set[str]] = {eid: set() for eid in entity_ids}
    counts = {eid: 0 for eid in entity_ids}
    for r in records:
        by_entity[r["entity_id"]].add(r["category"])
        counts[r["entity_id"]] += 1

    all_categories = sorted({r["category"] for r in records})
    reporting = {
        cat: sum(1 for eid in entity_ids if cat in by_entity[eid])
        for cat in all_categories
    }
    min_reporting = ns002_min_reporting(len(entity_ids))
    expected = [c for c in all_categories if reporting[c] >= min_reporting]

    out = []
    for entity_id in entity_ids:
        if counts[entity_id] < NS002_MIN_RECORDS:
            continue  # too few alerts for absence to mean anything
        for category in expected:
            if category in by_entity[entity_id]:
                continue
            ids = sorted(r["record_id"] for r in records if r["entity_id"] == entity_id)
            out.append({
                "entity_id": entity_id,
                "rule_id": "NS-002",
                "finding_type": NEGATIVE_SPACE,
                "title": "Threat-category blind spot",
                "explanation": (
                    f"This entity filed {counts[entity_id]} alerts and not one was categorised "
                    f"{category}, a category reported by {reporting[category]} of the other "
                    f"entities - suggesting a detection or reporting blind spot rather than "
                    f"genuine absence."
                ),
                "evidence_record_ids": ids,
            })
    return out


# --- Pipeline --------------------------------------------------------------------
def run_detection(con) -> int:
    """Recompute every finding from scratch. Returns the number generated."""
    records = _fetch_records(con)
    entity_ids = _entity_ids(con)
    cohorts = _entity_cohorts(con)

    findings: list[dict] = []
    findings += eg001(records)
    findings += eg002(records)
    findings += eg003(records, entity_ids)
    findings += eg004(records)
    findings += eg005(records, entity_ids)
    findings += ns001(records, entity_ids, cohorts)
    findings += ns002(records, entity_ids)

    # ML corroboration runs LAST and reads what the deterministic engine produced.
    # The gate is the whole point: an entity the rules found clean can never receive
    # an ML finding, however anomalous the model considers it.
    already_flagged = {f["entity_id"] for f in findings}
    analysis = ml.analyse(con)
    findings += ml_corroboration(con, already_flagged, analysis)

    # Persist the model's working alongside its conclusion. Same fit, so the profile
    # on screen is provably the one the finding was computed from.
    con.execute("DELETE FROM ml_profile")
    profile = ml.profile_rows(analysis, already_flagged)
    if profile:
        con.executemany(
            """
            INSERT INTO ml_profile (entity_id, feature, label, value, dataset_mean,
                                    deviation, contribution, method, anomalous,
                                    corroborated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            profile,
        )

    con.execute("DELETE FROM findings")
    for i, f in enumerate(findings, start=1):
        con.execute(
            """
            INSERT INTO findings (finding_id, entity_id, rule_id, finding_type, weight,
                                  title, explanation, evidence_record_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                f"F-{i:04d}",
                f["entity_id"],
                f["rule_id"],
                f["finding_type"],
                WEIGHTS[f["rule_id"]],
                f["title"],
                f["explanation"],
                ",".join(f["evidence_record_ids"]),
            ],
        )
    return len(findings)
