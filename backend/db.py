"""DuckDB connection and schema setup (PRD Section 3)."""

from __future__ import annotations

import os

import duckdb

DB_FILENAME = "sat_sa.duckdb"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_FILENAME)

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id   TEXT PRIMARY KEY,
    entity_name TEXT NOT NULL,
    sector      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    record_id             TEXT PRIMARY KEY,
    entity_id             TEXT NOT NULL,
    asset_id              TEXT NOT NULL,
    severity              TEXT NOT NULL,
    category              TEXT NOT NULL,
    opened_at             TIMESTAMP NOT NULL,
    closed_at             TIMESTAMP,
    escalated             BOOLEAN NOT NULL,
    disposition           TEXT NOT NULL,
    investigation_notes   TEXT,
    closure_time_minutes  DOUBLE
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id          TEXT PRIMARY KEY,
    entity_id           TEXT NOT NULL,
    rule_id             TEXT NOT NULL,
    finding_type        TEXT NOT NULL,
    weight              INTEGER NOT NULL,
    title               TEXT NOT NULL,
    explanation         TEXT NOT NULL,
    evidence_record_ids TEXT NOT NULL
);
"""


def connect(path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open (creating if needed) the DuckDB file and ensure the schema exists."""
    con = duckdb.connect(path or DB_PATH)
    con.execute(SCHEMA)
    return con


def is_empty(con: duckdb.DuckDBPyConnection) -> bool:
    """True when the database has no seeded entities yet."""
    return con.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0


def wipe(con: duckdb.DuckDBPyConnection) -> None:
    """Remove all rows. Used by the demo reset before re-seeding."""
    con.execute("DELETE FROM findings")
    con.execute("DELETE FROM records")
    con.execute("DELETE FROM entities")
