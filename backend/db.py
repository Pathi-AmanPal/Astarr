"""DuckDB connection and schema setup (PRD Section 3)."""

from __future__ import annotations

import os
import sys

import duckdb

DB_FILENAME = "sat_sa.duckdb"

# Beside the source by default, which is what local development wants. The container
# overrides it to a writable volume: the image runs as a non-root user with /app owned
# read-only in practice, and the database is rebuilt from the seed on startup anyway,
# so it is state, not content, and does not belong inside the image.
DB_PATH = os.environ.get("SATSA_DB") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), DB_FILENAME
)

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

-- Provenance. A supervisor reading a schedule must be able to see whether it was
-- computed over the built-in demo dataset or over a file they uploaded; a screenshot
-- of findings with no dataset attribution is not evidence of anything.
CREATE TABLE IF NOT EXISTS dataset_meta (
    id           INTEGER PRIMARY KEY,   -- always 1; one dataset is loaded at a time
    source       TEXT NOT NULL,         -- 'demo_seed' | 'upload'
    label        TEXT NOT NULL,
    loaded_at    TIMESTAMP NOT NULL,
    entity_count INTEGER NOT NULL,
    record_count INTEGER NOT NULL
);

-- The ML layer's working, persisted rather than discarded.
--
-- ML-001's explanation names its top two drivers in prose, which is enough to justify
-- the finding but not enough to interrogate it. These rows carry the whole feature
-- vector for every entity -- value, dataset mean, deviation and attribution -- so the
-- corroboration can be read the way the deterministic rules can: by looking at the
-- numbers it was computed from.
--
-- Written for EVERY entity, not only flagged ones. A supervisor's first question about
-- an anomaly score is "compared with what?", and the answer is the peer group.
CREATE TABLE IF NOT EXISTS ml_profile (
    entity_id    TEXT NOT NULL,
    feature      TEXT NOT NULL,
    label        TEXT NOT NULL,
    value        DOUBLE NOT NULL,
    dataset_mean DOUBLE NOT NULL,
    deviation    DOUBLE NOT NULL,   -- population sigmas from the mean
    contribution DOUBLE NOT NULL,   -- SHAP value, or the deviation when SHAP is absent
    method       TEXT NOT NULL,     -- 'shap' | 'zscore'
    anomalous    BOOLEAN NOT NULL,  -- the forest placed this entity outside the profile
    corroborated BOOLEAN NOT NULL   -- ... and a deterministic rule had already fired
);
"""


def connect(path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open (creating if needed) the DuckDB file and ensure the schema exists."""
    target_path = path or DB_PATH
    try:
        con = duckdb.connect(target_path)
    except Exception as exc:
        # DuckDB allows a single writer, so a second server (a stale uvicorn, or the
        # ingest CLI left running) holds the file and this connect fails. Falling back
        # to memory keeps the server usable instead of refusing to boot.
        #
        # It is announced loudly on purpose. In-memory means every upload and reset is
        # discarded on restart, and two processes would be serving different data --
        # discovering that silently, mid-demo, is far worse than a noisy start.
        print(
            f"\n*** WARNING: could not open {target_path} ({exc.__class__.__name__}: {exc})."
            f"\n*** Running IN MEMORY: data will NOT persist across a restart."
            f"\n*** Another process is probably holding the database. Close the other"
            f" server, then restart this one.\n",
            file=sys.stderr,
            flush=True,
        )
        con = duckdb.connect(":memory:")
    _apply_tuning(con)
    con.execute(SCHEMA)
    return con


def _apply_tuning(con: duckdb.DuckDBPyConnection) -> None:
    """Optional resource limits, off by default.

    DuckDB's own default is 80% of system RAM and it adapts to the machine, which is the
    right behaviour for an operator who has not asked for anything else. A fixed low
    limit is not free: measured on a million-record load, 256MB holds peak RSS to 404
    MiB, while 128MB fails outright with an OutOfMemoryError inside EG-003's aggregation.

    So this is a knob, not a policy. An operator deploying onto a constrained VM sets
    SATSA_DB_MEMORY_LIMIT (e.g. "512MB") and SATSA_DB_THREADS; nobody else needs to know
    the setting exists.
    """
    limit = os.environ.get("SATSA_DB_MEMORY_LIMIT")
    if limit:
        con.execute(f"SET memory_limit='{limit}'")
    threads = os.environ.get("SATSA_DB_THREADS")
    if threads:
        con.execute(f"SET threads={int(threads)}")


def is_empty(con: duckdb.DuckDBPyConnection) -> bool:
    """True when the database has no seeded entities yet."""
    return con.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0


def wipe(con: duckdb.DuckDBPyConnection) -> None:
    """Remove all rows. Used by the demo reset and by an upload before loading."""
    con.execute("DELETE FROM findings")
    con.execute("DELETE FROM ml_profile")
    con.execute("DELETE FROM records")
    con.execute("DELETE FROM entities")
    con.execute("DELETE FROM dataset_meta")


def set_dataset_meta(
    con: duckdb.DuckDBPyConnection,
    *,
    source: str,
    label: str,
    entity_count: int,
    record_count: int,
) -> None:
    """Record which dataset is loaded and when.

    `loaded_at` is the one wall-clock read in the system. It is provenance shown in the
    masthead, never an input to a rule, a threshold or a score -- the determinism the
    seed and verify.py depend on is untouched by it.
    """
    from datetime import datetime

    con.execute("DELETE FROM dataset_meta")
    con.execute(
        """
        INSERT INTO dataset_meta (id, source, label, loaded_at, entity_count, record_count)
        VALUES (1, ?, ?, ?, ?, ?)
        """,
        [source, label, datetime.now().replace(microsecond=0), entity_count, record_count],
    )


def dataset_meta(con: duckdb.DuckDBPyConnection) -> dict | None:
    """The loaded dataset's provenance, or None before anything is loaded."""
    row = con.execute(
        "SELECT source, label, loaded_at, entity_count, record_count "
        "FROM dataset_meta WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    return {
        "source": row[0],
        "label": row[1],
        "loaded_at": row[2],
        "entity_count": row[3],
        "record_count": row[4],
    }
