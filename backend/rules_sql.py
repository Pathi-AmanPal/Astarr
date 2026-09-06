"""Set-based implementations of the detection rules (2026-09-05).

The Python rules in `detection.py` read every record into a list of dicts and iterate
them. That costs roughly 1.5 KiB of resident memory per record -- 1.5 GiB for a million
alerts -- and memory, not time, is what bounds this tool. `_fetch_records` is the larger
half of that cost.

These implementations express the same rules as SQL and write findings with
`INSERT ... SELECT`, so a finding's row never becomes a Python object at all. Peak memory
stops tracking dataset size and becomes DuckDB's buffer pool, which is bounded and
configurable.

**This module must produce byte-identical findings to `detection.py`.** Not equivalent,
not equally valid -- identical: same finding ids, same order, same explanation strings,
same evidence lists. `verify.py` asserts that on every run against the reference dataset,
and the Python implementations are deliberately kept as the executable specification
rather than deleted. If the two ever disagree, the Python one is right.

Three translation details are easy to get subtly wrong, and each has a test:

- **Whitespace.** Python's `str.strip()` removes all whitespace; SQL `trim()` removes
  spaces only. EG-003 groups on stripped-and-lowered notes, so a note ending in a tab
  would group differently. `_norm_notes` uses a regex to match Python exactly.
- **Float formatting.** `_fmt` renders 20.0 as "20" and 1.40 as "1.4". The SQL
  equivalent is `rtrim(rtrim(printf('%.2f', x), '0'), '.')`, which agrees on every case
  including whole numbers and zero.
- **Ordering.** Finding ids are assigned in rule order, then by the order each rule
  emits. Every statement below carries the `ORDER BY` that reproduces its Python
  counterpart's iteration order.
"""

from __future__ import annotations

import config

EXECUTION_GAP = "EXECUTION_GAP"
NEGATIVE_SPACE = "NEGATIVE_SPACE"

# Python: notes.strip().lower(). SQL trim() is spaces-only, so strip the full whitespace
# class explicitly or a tab-terminated note lands in a different group.
_NORM_NOTES = r"lower(regexp_replace(investigation_notes, '^\s+|\s+$', '', 'g'))"

# Python: f"{v:.2f}".rstrip("0").rstrip(".")
def _fmt_sql(expr: str) -> str:
    return f"rtrim(rtrim(printf('%.2f', {expr}), '0'), '.')"


def _quote(value: str) -> str:
    """Single-quote a literal for embedding in SQL."""
    return "'" + str(value).replace("'", "''") + "'"


def _in_list(values) -> str:
    return "(" + ", ".join(_quote(v) for v in sorted(values)) + ")"


def _insert(con, offset: int, select_sql: str, params: list | None = None) -> int:
    """Run one rule's INSERT ... SELECT and return how many findings it wrote.

    `offset` is the count of findings already written, so `row_number()` continues the
    F-0001 sequence across rules exactly as the Python loop's `enumerate` does.
    """
    before = con.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    con.execute(select_sql, params or [])
    after = con.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    return after - before


def _finding_id(offset: int, order_by: str) -> str:
    """The F-0001 sequence, continued from `offset`, ordered as the Python rule emits.

    Python's `f"F-{i:04d}"` pads to four digits and never truncates, so the ten-thousandth
    finding is F-10000. DuckDB's `lpad(s, 4, '0')` *truncates* a longer string, which
    turned F-10000 into F-1000 and collided with the thousandth finding on the primary
    key. The CASE reproduces Python: pad below four digits, pass through at or above.
    """
    n = f"CAST({offset} + row_number() OVER (ORDER BY {order_by}) AS VARCHAR)"
    return f"'F-' || CASE WHEN length({n}) >= 4 THEN {n} ELSE lpad({n}, 4, '0') END"


COLUMNS = ("finding_id, entity_id, rule_id, finding_type, weight, title, explanation, "
           "evidence_record_ids")


# --- EG-001 -----------------------------------------------------------------------
def eg001(con, offset: int) -> int:
    sev = _in_list(config.severities("EG-001"))
    max_minutes = config.param("EG-001", "max_closure_minutes")
    unescalated = "AND NOT escalated" if config.param("EG-001", "require_unescalated") else ""
    order = "record_id"
    return _insert(con, offset, f"""
        INSERT INTO findings ({COLUMNS})
        SELECT {_finding_id(offset, order)},
               entity_id,
               'EG-001',
               '{EXECUTION_GAP}',
               {config.WEIGHTS['EG-001']},
               'Rapid closure without escalation',
               'Alert ' || record_id || ' (' || severity || ') was closed in '
                 || {_fmt_sql('closure_time_minutes')}
                 || ' minutes with no escalation - below the {max_minutes}-minute '
                 || 'threshold used to flag superficial closure.',
               record_id
        FROM records
        WHERE severity IN {sev}
          AND closure_time_minutes IS NOT NULL
          AND closure_time_minutes < {max_minutes}
          {unescalated}
        ORDER BY {order}
    """)


# --- EG-002 -----------------------------------------------------------------------
def eg002(con, offset: int) -> int:
    sev = _in_list(config.severities("EG-002"))
    unescalated = "AND NOT escalated" if config.param("EG-002", "require_unescalated") else ""
    order = "record_id"
    return _insert(con, offset, f"""
        INSERT INTO findings ({COLUMNS})
        SELECT {_finding_id(offset, order)},
               entity_id,
               'EG-002',
               '{EXECUTION_GAP}',
               {config.WEIGHTS['EG-002']},
               'Critical alert closed without escalation',
               'Alert ' || record_id || ' was marked CRITICAL but has no escalation '
                 || 'record, regardless of how quickly it was closed.',
               record_id
        FROM records
        WHERE severity IN {sev} {unescalated}
        ORDER BY {order}
    """)


# --- EG-003 -----------------------------------------------------------------------
def eg003(con, offset: int) -> int:
    """Grouped in SQL. Python iterates entities in sorted order, then note-keys sorted."""
    min_dupes = config.param("EG-003", "min_duplicates")
    order = "entity_id, note_key"
    return _insert(con, offset, f"""
        INSERT INTO findings ({COLUMNS})
        WITH grouped AS (
            SELECT entity_id,
                   {_NORM_NOTES} AS note_key,
                   COUNT(*) AS n,
                   string_agg(record_id, ',' ORDER BY record_id) AS ids
            FROM records
            WHERE investigation_notes IS NOT NULL
              AND regexp_replace(investigation_notes, '^\\s+|\\s+$', '', 'g') <> ''
            GROUP BY entity_id, note_key
            HAVING COUNT(*) >= {min_dupes}
        )
        SELECT {_finding_id(offset, order)},
               entity_id,
               'EG-003',
               '{EXECUTION_GAP}',
               {config.WEIGHTS['EG-003']},
               'Repetitive / template-driven investigation notes',
               CAST(n AS VARCHAR) || ' cases in this entity share the exact same '
                 || 'investigation notes text, suggesting superficial or template-driven '
                 || 'review rather than genuine investigation.',
               ids
        FROM grouped
        ORDER BY {order}
    """)


# --- EG-004 -----------------------------------------------------------------------
def eg004(con, offset: int) -> int:
    sev = _in_list(config.severities("EG-004"))
    disp = _in_list(config.dispositions("EG-004"))
    # Python: not (require_empty and notes is not None and notes.strip())
    empty_notes = ""
    if config.param("EG-004", "require_empty_notes"):
        empty_notes = ("AND (investigation_notes IS NULL OR "
                       "regexp_replace(investigation_notes, '^\\s+|\\s+$', '', 'g') = '')")
    order = "record_id"
    return _insert(con, offset, f"""
        INSERT INTO findings ({COLUMNS})
        SELECT {_finding_id(offset, order)},
               entity_id,
               'EG-004',
               '{EXECUTION_GAP}',
               {config.WEIGHTS['EG-004']},
               'Dismissed without recorded justification',
               'Alert ' || record_id || ' (' || severity || ') was dismissed as '
                 || disposition || ' with no investigation notes recorded - a serious '
                 || 'alert closed without any written justification.',
               record_id
        FROM records
        WHERE severity IN {sev} AND disposition IN {disp} {empty_notes}
        ORDER BY {order}
    """)


# --- EG-005 -----------------------------------------------------------------------
def eg005(con, offset: int) -> int:
    """Python keys the group on closed_at truncated to the minute, formatted
    'YYYY-MM-DD HH:MM:SS', and sorts on that string."""
    min_burst = config.param("EG-005", "min_burst_size")
    order = "entity_id, minute_key"
    return _insert(con, offset, f"""
        INSERT INTO findings ({COLUMNS})
        WITH bursts AS (
            SELECT entity_id,
                   strftime(date_trunc('minute', closed_at), '%Y-%m-%d %H:%M:%S') AS minute_key,
                   COUNT(*) AS n,
                   string_agg(record_id, ',' ORDER BY record_id) AS ids
            FROM records
            WHERE closed_at IS NOT NULL
            GROUP BY entity_id, minute_key
            HAVING COUNT(*) >= {min_burst}
        )
        SELECT {_finding_id(offset, order)},
               entity_id,
               'EG-005',
               '{EXECUTION_GAP}',
               {config.WEIGHTS['EG-005']},
               'Bulk closure burst',
               CAST(n AS VARCHAR) || ' alerts in this entity were all closed within the '
                 || 'same minute (' || minute_key || '), consistent with bulk '
                 || 'queue-clearing rather than individual review.',
               ids
        FROM bursts
        ORDER BY {order}
    """)


# --- NS-002 -----------------------------------------------------------------------
def ns002(con, offset: int, entity_ids: list[str]) -> int:
    """A category absent from an entity that most of its peers report.

    The proportional bar is computed the same way `detection.ns002_min_reporting` does,
    in Python, from the entity count -- there is one integer to agree on and importing
    it keeps a single definition.
    """
    from detection import ns002_min_reporting

    min_records = config.param("NS-002", "min_records")
    min_reporting = ns002_min_reporting(len(entity_ids))
    order = "entity_id, category"
    return _insert(con, offset, f"""
        INSERT INTO findings ({COLUMNS})
        WITH entity_counts AS (
            SELECT entity_id, COUNT(*) AS n FROM records GROUP BY entity_id
        ),
        entity_categories AS (
            SELECT DISTINCT entity_id, category FROM records
        ),
        reporting AS (
            SELECT category, COUNT(DISTINCT entity_id) AS reporters
            FROM records GROUP BY category
        ),
        expected AS (
            SELECT category, reporters FROM reporting WHERE reporters >= {min_reporting}
        ),
        entity_evidence AS (
            SELECT entity_id, string_agg(record_id, ',' ORDER BY record_id) AS ids
            FROM records GROUP BY entity_id
        ),
        gaps AS (
            SELECT c.entity_id, e.category, c.n, e.reporters, v.ids
            FROM entity_counts c
            CROSS JOIN expected e
            JOIN entity_evidence v ON v.entity_id = c.entity_id
            WHERE c.n >= {min_records}
              AND NOT EXISTS (
                  SELECT 1 FROM entity_categories ec
                  WHERE ec.entity_id = c.entity_id AND ec.category = e.category
              )
        )
        SELECT {_finding_id(offset, order)},
               entity_id,
               'NS-002',
               '{NEGATIVE_SPACE}',
               {config.WEIGHTS['NS-002']},
               'Threat-category blind spot',
               'This entity filed ' || CAST(n AS VARCHAR) || ' alerts and not one was '
                 || 'categorised ' || category || ', a category reported by '
                 || CAST(reporters AS VARCHAR) || ' of the other entities - suggesting a '
                 || 'detection or reporting blind spot rather than genuine absence.',
               ids
        FROM gaps
        ORDER BY {order}
    """)


def entity_counts(con) -> dict[str, int]:
    """Alert count per entity, including entities with none.

    NS-001 needs only these counts, never the records themselves, so it stays in Python
    at a cost that is bounded by the entity count rather than the dataset size.
    """
    rows = con.execute(
        """
        SELECT e.entity_id, COUNT(r.record_id)
        FROM entities e LEFT JOIN records r ON r.entity_id = e.entity_id
        GROUP BY e.entity_id ORDER BY e.entity_id
        """
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def entity_evidence(con, entity_id: str) -> list[str]:
    """Every record id for one entity, sorted -- the evidence NS-001 attaches."""
    return [r[0] for r in con.execute(
        "SELECT record_id FROM records WHERE entity_id = ? ORDER BY record_id",
        [entity_id],
    ).fetchall()]
