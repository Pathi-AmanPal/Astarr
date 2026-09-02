"""Detection rules (PRD Section 4, expanded to six rules 2026-09-02).

Thresholds are hardcoded constants by design -- PRD Section 9 defers YAML configuration
to Phase 2. Findings are recomputed from scratch on every run and never hand-edited.

Determinism: every rule iterates entities and records in sorted order, and finding ids
are assigned in a fixed rule sequence, so the same seed always produces byte-identical
findings in the same order.
"""

from __future__ import annotations

import math
import statistics

from ml import ML_RULE_ID, ML_WEIGHT, ml_corroboration

EXECUTION_GAP = "EXECUTION_GAP"
NEGATIVE_SPACE = "NEGATIVE_SPACE"

# --- Rule thresholds -------------------------------------------------------------
EG001_MAX_CLOSURE_MINUTES = 2
EG003_MIN_DUPLICATES = 3
EG005_MIN_BURST_SIZE = 5
NS001_STDDEV_MULTIPLIER = 1.5
NS002_MIN_RECORDS = 10          # below this, a coverage gap is just low volume

# A category is "expected" when at least this fraction of entities report it.
# Proportional, never absolute: the rule previously hardcoded 6, which was 75% of 8.
# Left absolute, that same 6 silently becomes a 50% bar at 12 entities and a 25% bar
# at 24 -- the rule weakening as the dataset grows, with nothing to catch it.
NS002_MIN_REPORTING_FRACTION = 0.75


def ns002_min_reporting(entity_count: int) -> int:
    """Entities that must report a category before absence counts as a blind spot."""
    return math.ceil(NS002_MIN_REPORTING_FRACTION * entity_count)

WEIGHTS = {
    "EG-001": 35,
    "EG-002": 25,
    "EG-003": 20,
    "EG-004": 15,
    "EG-005": 25,
    "NS-001": 30,
    "NS-002": 25,
    ML_RULE_ID: ML_WEIGHT,
}


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
            r["severity"] in ("HIGH", "CRITICAL")
            and r["closure_time_minutes"] is not None
            and r["closure_time_minutes"] < EG001_MAX_CLOSURE_MINUTES
            and not r["escalated"]
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
        if r["severity"] == "CRITICAL" and not r["escalated"]:
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
            r["severity"] in ("HIGH", "CRITICAL")
            and r["disposition"] in ("FALSE_POSITIVE", "BENIGN")
            and (notes is None or not notes.strip())
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
def ns001(records: list[dict], entity_ids: list[str]) -> list[dict]:
    counts = {eid: 0 for eid in entity_ids}
    for r in records:
        counts[r["entity_id"]] = counts.get(r["entity_id"], 0) + 1

    values = [counts[eid] for eid in entity_ids]
    mean = statistics.fmean(values)
    # pstdev, not stdev. PRD Section 12 specifies population standard deviation, and
    # DuckDB's STDDEV() is stddev_samp -- an easy mismatch to introduce accidentally.
    std = statistics.pstdev(values)
    threshold = mean - NS001_STDDEV_MULTIPLIER * std

    out = []
    for entity_id in entity_ids:
        if counts[entity_id] < threshold:
            ids = sorted(r["record_id"] for r in records if r["entity_id"] == entity_id)
            out.append({
                "entity_id": entity_id,
                "rule_id": "NS-001",
                "finding_type": NEGATIVE_SPACE,
                "title": "Alert volume significantly below dataset average",
                "explanation": (
                    f"This entity generated {counts[entity_id]} alerts, compared to a dataset "
                    f"average of {_fmt(mean)} - well below expectation for a comparable environment."
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

    findings: list[dict] = []
    findings += eg001(records)
    findings += eg002(records)
    findings += eg003(records, entity_ids)
    findings += eg004(records)
    findings += eg005(records, entity_ids)
    findings += ns001(records, entity_ids)
    findings += ns002(records, entity_ids)

    # ML corroboration runs LAST and reads what the deterministic engine produced.
    # The gate is the whole point: an entity the rules found clean can never receive
    # an ML finding, however anomalous the model considers it.
    already_flagged = {f["entity_id"] for f in findings}
    findings += ml_corroboration(con, already_flagged)

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
