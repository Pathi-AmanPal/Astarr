"""Deterministic demo dataset (PRD Section 12, as amended 2026-09-02).

Absolutely no randomness and no wall-clock reads. Every timestamp derives from a fixed
anchor by index arithmetic, so the dataset -- and therefore every finding and every score
-- is byte-identical on every run, on any machine, on any calendar day.

Amendment 1 (rules 4 -> 6): planted records REPLACE filler slots inside their own entity
rather than being appended, so every per-entity total from PRD Section 12 is preserved
exactly and CSE-01..CSE-08 stay at 158 records.

Amendment 2 (8 -> 12 entities, 248 records): CSE-09..CSE-12 are APPENDED after CSE-08 and
are purely additive. Existing entities keep their composition, their counts, and their
record ids (ALT-0001..ALT-0158) byte for byte. The four new entities are clean by
construction; they exist to thicken NS-001's statistical baseline and the Isolation
Forest's peer group, not to add findings.

Adding entities near the mean shrinks sigma, which RAISES NS-001's `mean - 1.5*sigma`
threshold. That makes a low-volume entity safer while moving clean entities closer to
falsely crossing from the other side. verify.py asserts both directions -- never only the
entity expected to stay flagged.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

# A fixed anchor. Never datetime.now() -- see module docstring.
ANCHOR = datetime(2026, 1, 5, 8, 0, 0)

# The single minute into which EG-005's burst records are all closed.
BURST_CLOSED_AT = ANCHOR + timedelta(days=40)

SEVERITY_CYCLE = ["LOW", "MEDIUM", "HIGH"]
DISPOSITION_CYCLE = ["TRUE_POSITIVE", "FALSE_POSITIVE", "BENIGN"]

ALL_CATEGORIES = ["Malware", "Unauthorized Access", "Phishing", "Data Exfiltration"]
# CSE-01 never files a Phishing alert. This is what NS-002 detects.
BLIND_SPOT_CATEGORY = "Phishing"
CSE01_CATEGORIES = [c for c in ALL_CATEGORIES if c != BLIND_SPOT_CATEGORY]

ENTITIES = [
    ("CSE-01", "Entity Alpha - Power Grid", "Energy", 25),
    ("CSE-02", "Entity Bravo - Telecom", "Telecom", 4),
    ("CSE-03", "Entity Charlie - Banking", "Banking", 24),
    ("CSE-04", "Entity Delta - Healthcare", "Healthcare", 22),
    ("CSE-05", "Entity Echo - Transport", "Transport", 23),
    ("CSE-06", "Entity Foxtrot - Water Utility", "Utilities", 20),
    ("CSE-07", "Entity Golf - Defence Logistics", "Defence", 21),
    ("CSE-08", "Entity Hotel - Insurance", "Finance", 19),
    # Added 2026-09-02. Purely additive: appended AFTER CSE-08 so every existing
    # record keeps its id (ALT-0001..ALT-0158) and every existing assertion holds.
    # These are genuinely clean by construction -- their job is to thicken the peer
    # group for NS-001's baseline and the Isolation Forest's feature space, not to
    # add demo findings.
    ("CSE-09", "Entity India - Aviation", "Aviation", 22),
    ("CSE-10", "Entity Juliet - Oil & Gas", "Oil & Gas", 24),
    ("CSE-11", "Entity Kilo - Municipal Services", "Municipal Services", 21),
    ("CSE-12", "Entity Lima - Space Research", "Space Research", 23),
]

EG003_NOTES = "Reviewed, closed as per standard procedure."


class _Ids:
    """Sequential record ids, assigned in entity order."""

    def __init__(self) -> None:
        self.n = 0

    def next(self) -> str:
        self.n += 1
        return f"ALT-{self.n:04d}"


def _record(
    record_id: str,
    entity_id: str,
    index: int,
    severity: str,
    category: str,
    opened_at: datetime,
    closed_at: datetime | None,
    escalated: bool,
    disposition: str,
    notes: str | None,
) -> dict:
    closure = None
    if closed_at is not None:
        closure = round((closed_at - opened_at).total_seconds() / 60.0, 2)
    return {
        "record_id": record_id,
        "entity_id": entity_id,
        "asset_id": f"{entity_id}-ASSET-{(index % 7) + 1:02d}",
        "severity": severity,
        "category": category,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "escalated": escalated,
        "disposition": disposition,
        "investigation_notes": notes,
        "closure_time_minutes": closure,
    }


def _filler(record_id: str, entity_id: str, index: int, categories: list[str]) -> dict:
    """A clean record. Deliberately trips no rule -- see the guards below."""
    severity = SEVERITY_CYCLE[index % 3]
    # 10..120 minutes, never below the 2-minute EG-001 threshold.
    closure = 10 + (index * 7) % 111
    opened_at = ANCHOR + timedelta(hours=6 * index)
    escalated = True if severity == "HIGH" else (index % 2 == 0)

    # Notes are either unique (record_id embedded, so EG-003 can never match across
    # records) or NULL. NULL is only ever assigned below HIGH severity, because a
    # HIGH record with empty notes and a dismissive disposition would trip EG-004.
    if severity != "HIGH" and index % 4 == 0:
        notes = None
    else:
        notes = f"Case {record_id} reviewed by duty analyst; no further action required."

    return _record(
        record_id=record_id,
        entity_id=entity_id,
        index=index,
        severity=severity,
        category=categories[index % len(categories)],
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=closure),
        escalated=escalated,
        disposition=DISPOSITION_CYCLE[index % 3],
        notes=notes,
    )


def _eg001_eg002(record_id: str, entity_id: str, index: int, category: str) -> dict:
    """CRITICAL, closed in 1.4 minutes, never escalated. Trips EG-001 and EG-002."""
    opened_at = ANCHOR + timedelta(hours=6 * index)
    return _record(
        record_id, entity_id, index,
        severity="CRITICAL",
        category=category,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(seconds=84),  # 1.4 min
        escalated=False,
        disposition="UNRESOLVED",
        notes=f"Auto-closed by analyst queue action {index + 1}.",
    )


def _eg002_only(record_id: str, entity_id: str, index: int, category: str) -> dict:
    """CRITICAL and unescalated, but closed in 15 min so EG-001 stays silent."""
    opened_at = ANCHOR + timedelta(hours=6 * index)
    return _record(
        record_id, entity_id, index,
        severity="CRITICAL",
        category=category,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=15),
        escalated=False,
        disposition="UNRESOLVED",
        notes="Closed pending vendor confirmation.",
    )


def _eg003(record_id: str, entity_id: str, index: int, category: str) -> dict:
    """HIGH, escalated, resolved -- identical notes are the only red flag."""
    opened_at = ANCHOR + timedelta(hours=6 * index)
    return _record(
        record_id, entity_id, index,
        severity="HIGH",
        category=category,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=45),
        escalated=True,
        disposition="TRUE_POSITIVE",
        notes=EG003_NOTES,
    )


def _eg004(record_id: str, entity_id: str, index: int, category: str, disposition: str) -> dict:
    """HIGH, escalated, closed in 35 min -- the only flag is the missing justification."""
    opened_at = ANCHOR + timedelta(hours=6 * index)
    return _record(
        record_id, entity_id, index,
        severity="HIGH",
        category=category,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=35),
        escalated=True,
        disposition=disposition,
        notes=None,
    )


def _eg005(record_id: str, entity_id: str, index: int, category: str, minutes_open: int) -> dict:
    """Low-noise records that all happen to close in the same minute."""
    opened_at = BURST_CLOSED_AT - timedelta(minutes=minutes_open)
    severity = "LOW" if index % 2 == 0 else "MEDIUM"
    return _record(
        record_id, entity_id, index,
        severity=severity,
        category=category,
        opened_at=opened_at,
        closed_at=BURST_CLOSED_AT,
        escalated=index % 2 == 0,
        disposition=DISPOSITION_CYCLE[index % 3],
        notes=f"Bulk triage sweep entry for {record_id}.",
    )


def build_records() -> list[dict]:
    """Build all 158 records. Pure function of the constants above."""
    ids = _Ids()
    rows: list[dict] = []

    for entity_id, _name, _sector, total in ENTITIES:
        categories = CSE01_CATEGORIES if entity_id == "CSE-01" else ALL_CATEGORIES
        planted: list[dict] = []
        i = 0

        if entity_id == "CSE-01":
            # 3 x (EG-001 + EG-002), 4 x EG-003, 1 x EG-004, then filler.
            for _ in range(3):
                planted.append(_eg001_eg002(ids.next(), entity_id, i, categories[i % len(categories)]))
                i += 1
            for _ in range(4):
                planted.append(_eg003(ids.next(), entity_id, i, categories[i % len(categories)]))
                i += 1
            planted.append(_eg004(ids.next(), entity_id, i, categories[i % len(categories)], "FALSE_POSITIVE"))
            i += 1

        elif entity_id == "CSE-03":
            # 5 records closing in one minute (EG-005), plus one EG-004.
            for burst_index in range(5):
                planted.append(
                    _eg005(
                        ids.next(), entity_id, i,
                        categories[i % len(categories)],
                        minutes_open=20 + burst_index * 15,
                    )
                )
                i += 1
            planted.append(_eg004(ids.next(), entity_id, i, categories[i % len(categories)], "BENIGN"))
            i += 1

        elif entity_id == "CSE-05":
            planted.append(_eg002_only(ids.next(), entity_id, i, categories[i % len(categories)]))
            i += 1
            for disposition in ("FALSE_POSITIVE", "BENIGN"):
                planted.append(_eg004(ids.next(), entity_id, i, categories[i % len(categories)], disposition))
                i += 1

        elif entity_id == "CSE-06":
            planted.append(_eg004(ids.next(), entity_id, i, categories[i % len(categories)], "FALSE_POSITIVE"))
            i += 1

        rows.extend(planted)

        # Filler fills the remainder of this entity's fixed total.
        for _ in range(total - len(planted)):
            rows.append(_filler(ids.next(), entity_id, i, categories))
            i += 1

    return rows


def build_entities() -> list[dict]:
    return [
        {"entity_id": eid, "entity_name": name, "sector": sector}
        for eid, name, sector, _total in ENTITIES
    ]


def seed(con) -> tuple[int, int]:
    """Wipe and re-insert the fixed dataset. Returns (entities, records)."""
    from db import wipe

    wipe(con)

    entities_df = pd.DataFrame(build_entities())
    records_df = pd.DataFrame(build_records())

    con.register("entities_df", entities_df)
    con.register("records_df", records_df)
    con.execute("INSERT INTO entities SELECT * FROM entities_df")
    con.execute(
        """
        INSERT INTO records (
            record_id, entity_id, asset_id, severity, category, opened_at, closed_at,
            escalated, disposition, investigation_notes, closure_time_minutes
        )
        SELECT record_id, entity_id, asset_id, severity, category, opened_at, closed_at,
               escalated, disposition, investigation_notes, closure_time_minutes
        FROM records_df
        """
    )
    con.unregister("entities_df")
    con.unregister("records_df")

    return len(entities_df), len(records_df)
