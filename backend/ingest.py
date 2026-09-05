"""Ingest custom CSV or JSON alert dataset into SAT-SA for supervisory analysis (Zero Dependencies)."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import os
import sys
_base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base_dir)
_site_pkg = os.path.join(_base_dir, "venv", "Lib", "site-packages")
if os.path.isdir(_site_pkg) and _site_pkg not in sys.path:
    sys.path.insert(0, _site_pkg)

import db
from detection import run_detection
from scoring import ranked_entities


def parse_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str or not dt_str.strip():
        return None
    dt_str = dt_str.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def parse_bool(val: any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "t", "y")
    return False


def ingest_file(file_path: str, con=None, clear_existing: bool = True) -> tuple[int, int, int]:
    """Ingest CSV or JSON records into DuckDB and run supervisory detection pipeline.

    Returns (entities_count, records_count, findings_count).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Data file not found: {file_path}")

    records = []
    if file_path.lower().endswith(".csv"):
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
    elif file_path.lower().endswith(".json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            records = data if isinstance(data, list) else [data]
    else:
        raise ValueError("Unsupported file format. Please provide a .csv or .json file.")

    if not records:
        raise ValueError("Dataset file is empty.")

    close_con = False
    if con is None:
        con = db.connect()
        close_con = True

    if clear_existing:
        db.wipe(con)

    entities_map: dict[str, tuple[str, str, str]] = {}
    parsed_records = []

    for idx, r in enumerate(records, start=1):
        record_id = str(r.get("record_id") or f"ALT-{idx:04d}")
        entity_id = str(r.get("entity_id") or "CSE-01")
        entity_name = str(r.get("entity_name") or f"Entity {entity_id}")
        sector = str(r.get("sector") or "General")

        entities_map[entity_id] = (entity_id, entity_name, sector)

        asset_id = str(r.get("asset_id") or "AST-001")
        severity = str(r.get("severity") or "MEDIUM").upper()
        category = str(r.get("category") or "General Security")
        
        opened_at = parse_datetime(r.get("opened_at")) or datetime.utcnow()
        closed_at = parse_datetime(r.get("closed_at"))
        escalated = parse_bool(r.get("escalated"))
        disposition = str(r.get("disposition") or "TRUE_POSITIVE").upper()
        notes = r.get("investigation_notes")
        notes_str = str(notes) if notes is not None and str(notes).strip() else None

        closure_time_minutes = r.get("closure_time_minutes")
        if closure_time_minutes is not None and str(closure_time_minutes).strip() != "":
            try:
                closure_min = float(closure_time_minutes)
            except ValueError:
                closure_min = None
        elif closed_at and opened_at:
            delta = (closed_at - opened_at).total_seconds() / 60.0
            closure_min = max(0.0, round(delta, 2))
        else:
            closure_min = None

        parsed_records.append((
            record_id, entity_id, asset_id, severity, category,
            opened_at, closed_at, escalated, disposition, notes_str, closure_min
        ))

    # Insert entities into DuckDB
    for eid, ename, esector in entities_map.values():
        con.execute(
            "INSERT OR IGNORE INTO entities (entity_id, entity_name, sector) VALUES (?, ?, ?)",
            [eid, ename, esector]
        )

    # Insert records into DuckDB
    for rec in parsed_records:
        con.execute(
            """
            INSERT INTO records (record_id, entity_id, asset_id, severity, category,
                                 opened_at, closed_at, escalated, disposition,
                                 investigation_notes, closure_time_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            list(rec)
        )

    # Run supervisory detection rules & analytics
    findings_generated = run_detection(con)
    entities_count = len(entities_map)
    records_count = len(parsed_records)

    if close_con:
        con.close()

    return entities_count, records_count, findings_generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest custom alert dataset into SAT-SA")
    parser.add_argument("file", help="Path to custom .csv or .json file")
    args = parser.parse_args()

    try:
        e_cnt, r_cnt, f_cnt = ingest_file(args.file)
        print(f"\n[+] Success! Ingested dataset: {args.file}")
        print(f"    - Entities: {e_cnt}")
        print(f"    - Records: {r_cnt}")
        print(f"    - Findings Raised: {f_cnt}\n")

        con = db.connect()
        ranked = ranked_entities(con)
        print("Top Supervisory Attention Ranking:")
        for rank, e in enumerate(ranked[:5], 1):
            print(f"  {rank}. {e['entity_name']} ({e['entity_id']}) — Risk Score: {e['risk_score']} ({e['finding_count']} findings)")
        con.close()
    except Exception as exc:
        print(f"[-] Ingestion failed: {exc}", file=sys.stderr)
        sys.exit(1)
