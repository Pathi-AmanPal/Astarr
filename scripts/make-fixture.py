"""Script to generate tests/fixtures/regression-dataset.csv.

This creates the deterministic 12-entity, 248-record ground-truth regression dataset.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

ANCHOR = datetime(2026, 1, 5, 8, 0, 0)
BURST_CLOSED_AT = ANCHOR + timedelta(days=40)

SEVERITY_CYCLE = ["LOW", "MEDIUM", "HIGH"]
DISPOSITION_CYCLE = ["TRUE_POSITIVE", "FALSE_POSITIVE", "BENIGN"]

ALL_CATEGORIES = ["Malware", "Unauthorized Access", "Phishing", "Data Exfiltration"]
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
    ("CSE-09", "Entity India - Aviation", "Aviation", 22),
    ("CSE-10", "Entity Juliet - Oil & Gas", "Oil & Gas", 24),
    ("CSE-11", "Entity Kilo - Municipal Services", "Municipal Services", 21),
    ("CSE-12", "Entity Lima - Space Research", "Space Research", 23),
]

EG003_NOTES = "Reviewed, closed as per standard procedure."

class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def next(self) -> str:
        self.n += 1
        return f"ALT-{self.n:04d}"

def _record(
    record_id: str,
    entity_id: str,
    entity_name: str,
    sector: str,
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
        "entity_name": entity_name,
        "sector": sector,
        "asset_id": f"{entity_id}-ASSET-{(index % 7) + 1:02d}",
        "severity": severity,
        "category": category,
        "opened_at": opened_at.isoformat(),
        "closed_at": closed_at.isoformat() if closed_at else "",
        "escalated": "true" if escalated else "false",
        "disposition": disposition,
        "investigation_notes": notes or "",
        "closure_time_minutes": closure if closure is not None else "",
    }

def _filler(record_id: str, entity_id: str, name: str, sector: str, index: int, categories: list[str]) -> dict:
    severity = SEVERITY_CYCLE[index % 3]
    closure = 10 + (index * 7) % 111
    opened_at = ANCHOR + timedelta(hours=6 * index)
    escalated = True if severity == "HIGH" else (index % 2 == 0)

    if severity != "HIGH" and index % 4 == 0:
        notes = None
    else:
        notes = f"Case {record_id} reviewed by duty analyst; no further action required."

    return _record(
        record_id, entity_id, name, sector, index,
        severity=severity,
        category=categories[index % len(categories)],
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=closure),
        escalated=escalated,
        disposition=DISPOSITION_CYCLE[index % 3],
        notes=notes,
    )

def _eg001_eg002(record_id: str, entity_id: str, name: str, sector: str, index: int, category: str) -> dict:
    opened_at = ANCHOR + timedelta(hours=6 * index)
    return _record(
        record_id, entity_id, name, sector, index,
        severity="CRITICAL",
        category=category,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(seconds=84),
        escalated=False,
        disposition="TRUE_POSITIVE",
        notes=f"Auto-closed by analyst queue action {index + 1}.",
    )

def _eg002_only(record_id: str, entity_id: str, name: str, sector: str, index: int, category: str) -> dict:
    opened_at = ANCHOR + timedelta(hours=6 * index)
    return _record(
        record_id, entity_id, name, sector, index,
        severity="CRITICAL",
        category=category,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=15),
        escalated=False,
        disposition="TRUE_POSITIVE",
        notes="Closed pending vendor confirmation.",
    )


def _eg003(record_id: str, entity_id: str, name: str, sector: str, index: int, category: str) -> dict:
    opened_at = ANCHOR + timedelta(hours=6 * index)
    return _record(
        record_id, entity_id, name, sector, index,
        severity="HIGH",
        category=category,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=45),
        escalated=True,
        disposition="TRUE_POSITIVE",
        notes=EG003_NOTES,
    )

def _eg004(record_id: str, entity_id: str, name: str, sector: str, index: int, category: str, disposition: str) -> dict:
    opened_at = ANCHOR + timedelta(hours=6 * index)
    return _record(
        record_id, entity_id, name, sector, index,
        severity="HIGH",
        category=category,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=35),
        escalated=True,
        disposition=disposition,
        notes=None,
    )

def _eg005(record_id: str, entity_id: str, name: str, sector: str, index: int, category: str, minutes_open: int) -> dict:
    opened_at = BURST_CLOSED_AT - timedelta(minutes=minutes_open)
    severity = "LOW" if index % 2 == 0 else "MEDIUM"
    return _record(
        record_id, entity_id, name, sector, index,
        severity=severity,
        category=category,
        opened_at=opened_at,
        closed_at=BURST_CLOSED_AT,
        escalated=index % 2 == 0,
        disposition=DISPOSITION_CYCLE[index % 3],
        notes=f"Bulk triage sweep entry for {record_id}.",
    )

def build_records() -> list[dict]:
    ids = _Ids()
    rows: list[dict] = []

    for entity_id, name, sector, total in ENTITIES:
        categories = CSE01_CATEGORIES if entity_id == "CSE-01" else ALL_CATEGORIES
        planted: list[dict] = []
        i = 0

        if entity_id == "CSE-01":
            for _ in range(3):
                planted.append(_eg001_eg002(ids.next(), entity_id, name, sector, i, categories[i % len(categories)]))
                i += 1
            for _ in range(4):
                planted.append(_eg003(ids.next(), entity_id, name, sector, i, categories[i % len(categories)]))
                i += 1
            planted.append(_eg004(ids.next(), entity_id, name, sector, i, categories[i % len(categories)], "FALSE_POSITIVE"))
            i += 1

        elif entity_id == "CSE-03":
            for burst_index in range(5):
                planted.append(
                    _eg005(
                        ids.next(), entity_id, name, sector, i,
                        categories[i % len(categories)],
                        minutes_open=20 + burst_index * 15,
                    )
                )
                i += 1
            planted.append(_eg004(ids.next(), entity_id, name, sector, i, categories[i % len(categories)], "BENIGN"))
            i += 1

        elif entity_id == "CSE-05":
            planted.append(_eg002_only(ids.next(), entity_id, name, sector, i, categories[i % len(categories)]))
            i += 1
            for disposition in ("FALSE_POSITIVE", "BENIGN"):
                planted.append(_eg004(ids.next(), entity_id, name, sector, i, categories[i % len(categories)], disposition))
                i += 1

        elif entity_id == "CSE-06":
            planted.append(_eg004(ids.next(), entity_id, name, sector, i, categories[i % len(categories)], "FALSE_POSITIVE"))
            i += 1

        rows.extend(planted)

        for _ in range(total - len(planted)):
            rows.append(_filler(ids.next(), entity_id, name, sector, i, categories))
            i += 1

    return rows

def generate(output_path: Path) -> None:
    records = build_records()
    fieldnames = [
        "record_id", "entity_id", "entity_name", "sector", "asset_id",
        "severity", "category", "opened_at", "closed_at", "escalated",
        "disposition", "investigation_notes", "closure_time_minutes"
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"Generated {len(records)} records across {len(ENTITIES)} entities -> {output_path}")

if __name__ == "__main__":
    dest = Path(__file__).parent.parent / "tests" / "fixtures" / "regression-dataset.csv"
    generate(dest)
