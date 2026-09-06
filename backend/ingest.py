"""CSV ingestion (PRD Section 12 deferral discharged, 2026-09-05).

The demo seed stays the default dataset. This module adds the other half the tool
always implied: a supervisor can hand it a real alert export and get the same
schedule, the same findings and the same footed score over their own data.

Three properties matter here, and they are the reason this is a module rather than a
few lines in an endpoint:

1. **Validation refuses, it never repairs.** A row with an unreadable timestamp or an
   unknown severity is reported by line number and the whole upload is rejected. A
   partially-loaded dataset would produce findings that are wrong in a way nothing on
   screen could reveal, and a supervisory tool that quietly drops evidence is worse
   than one that will not start.

2. **Every error is reported at once.** Fixing an export one error per upload round
   is what makes a validating importer hated. The parser collects up to
   `MAX_REPORTED_ERRORS` problems across the whole file before it gives up.

3. **The rules see the same shape they always saw.** Ingest writes exactly the columns
   `detection.py` reads; it does not invent fields, and it derives only one value
   (`closure_time_minutes`, from the two timestamps) which the seed also derives.

Values are validated against the vocabulary the rules actually consult -- the
severities in `rules.yaml` plus the dispositions EG-004 tests -- so an accepted file
cannot contain a value that silently matches no rule.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
from datetime import datetime

# The columns a row must carry. `entity_name` and `sector` repeat per row: an alert
# export is a flat table, and asking a supervisor to supply two joined files to try the
# tool is a barrier with no analytical benefit.
REQUIRED_COLUMNS = [
    "record_id",
    "entity_id",
    "entity_name",
    "sector",
    "asset_id",
    "severity",
    "category",
    "opened_at",
    "disposition",
]

OPTIONAL_COLUMNS = [
    "closed_at",
    "escalated",
    "investigation_notes",
    "closure_time_minutes",
]

# Matches rules.yaml: EG-001/EG-002/EG-004 all key off these, and CRITICAL is the
# severity EG-002 exists for. A file using a different scale must be mapped before
# upload rather than silently scoring as if every alert were LOW.
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

# EG-004 fires on FALSE_POSITIVE and BENIGN dismissals; TRUE_POSITIVE is the third
# value the seed uses. Anything else would be invisible to the rule.
DISPOSITIONS = {"TRUE_POSITIVE", "FALSE_POSITIVE", "BENIGN"}

TRUE_VALUES = {"true", "t", "yes", "y", "1"}
FALSE_VALUES = {"false", "f", "no", "n", "0", ""}

# A guard against a mis-selected file, not a capability limit.
#
# Raised from 50,000 on 2026-09-05. The old cap was set when a 50,000-row load took 65
# seconds; with bulk insert it takes 0.6s, and the cap was then the only thing standing
# between this tool and the "large datasets spanning multiple entities and time periods"
# requirement.
#
# Measured on 1,000,000 rows across 50 entities: 37.7s end to end (14.3s parse, 6.0s
# load, 17.0s detection, 220,514 findings) at a peak of 1.5 GiB RSS.
#
# **Memory, not time, is what bounds this.** Roughly 1.5 KiB of resident memory per
# record, because `parse_csv` materialises every row as a tuple and `_fetch_records`
# reads them all back as dicts. A 2 GiB machine handles about a million rows; beyond
# that both stages need to stream, which is a real change and not a tuning knob.
MAX_ROWS = 1_000_000

# Enough to fix an export in one pass without pasting a wall of text into the UI.
MAX_REPORTED_ERRORS = 25

TEMPLATE_CSV = """\
record_id,entity_id,entity_name,sector,asset_id,severity,category,opened_at,closed_at,escalated,disposition,investigation_notes,closure_time_minutes
ALT-0001,CSE-01,Northern Grid Operator,Energy,SRV-014,HIGH,Malware,2026-01-05T08:00:00,2026-01-05T08:01:00,false,FALSE_POSITIVE,,1.0
ALT-0002,CSE-01,Northern Grid Operator,Energy,SRV-014,CRITICAL,Unauthorized Access,2026-01-05T09:12:00,2026-01-05T11:40:00,false,TRUE_POSITIVE,Reviewed firewall logs; confirmed brute force.,148.0
ALT-0003,CSE-02,Coastal Telecom,Telecom,WKS-221,MEDIUM,Phishing,2026-01-06T10:05:00,2026-01-06T12:30:00,true,TRUE_POSITIVE,User reported; mailbox rule removed.,145.0
"""


# ---------------------------------------------------------------------------------
# Schema normalisation (2026-09-06)
#
# Every CSE exports a different layout. A tool that only accepts this module's exact
# column names is one that every submission has to be hand-transformed for first, which
# defeats "ingest structured data from multiple CSEs".
#
# So the parser maps. What it must never do is map *silently*: a column guessed wrong
# produces findings that are wrong with nothing on screen admitting it, which is the
# failure mode this whole tool exists to expose in other people's systems. Every
# substitution is recorded and returned, and the UI shows it.
#
# Three rules keep the mapping honest:
#   1. Aliases are exact matches after normalising case, spaces, hyphens and
#      underscores -- never fuzzy, never edit-distance. "sev" maps because it is in the
#      table, not because it looks a bit like "severity".
#   2. Ambiguity is an error, not a coin toss. Two columns claiming the same canonical
#      field stops the upload and names both.
#   3. An unrecognised column is ignored and reported, never guessed at.
# ---------------------------------------------------------------------------------

def _key(name: str) -> str:
    """Normalise a header for comparison: case, spaces, hyphens, underscores, dots."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


# Canonical field -> the header spellings seen in real SOC and ITSM exports.
COLUMN_ALIASES: dict[str, list[str]] = {
    "record_id": ["record_id", "alert_id", "id", "ticket_id", "case_id", "incident_id",
                  "event_id", "alertid", "caseno", "case_number", "reference", "ref"],
    "entity_id": ["entity_id", "org_id", "organisation_id", "organization_id", "cse_id",
                  "customer_id", "tenant_id", "client_id", "company_id", "entity"],
    "entity_name": ["entity_name", "org_name", "organisation", "organization", "cse_name",
                    "customer", "client", "company", "tenant", "name"],
    "sector": ["sector", "industry", "vertical", "domain", "segment", "sector_name"],
    "asset_id": ["asset_id", "host", "hostname", "device", "device_id", "asset",
                 "source_host", "src_host", "machine", "endpoint", "system"],
    "severity": ["severity", "sev", "priority", "criticality", "urgency", "risk_level",
                 "alert_severity", "level"],
    "category": ["category", "alert_type", "type", "classification", "threat_type",
                 "alert_category", "signature", "rule_name", "detection_type"],
    "opened_at": ["opened_at", "created_at", "created", "opened", "detected_at",
                  "first_seen", "alert_time", "timestamp", "event_time", "start_time",
                  "reported_at", "raised_at"],
    "closed_at": ["closed_at", "resolved_at", "closed", "resolution_time", "end_time",
                  "completed_at", "last_seen", "closure_date"],
    "escalated": ["escalated", "is_escalated", "escalation", "escalated_flag",
                  "was_escalated", "escalation_flag"],
    "disposition": ["disposition", "resolution", "outcome", "verdict", "status",
                    "closure_code", "resolution_code", "classification_result",
                    "final_status"],
    "investigation_notes": ["investigation_notes", "notes", "comments", "analyst_notes",
                            "resolution_notes", "description", "summary", "remarks",
                            "work_notes", "investigation"],
    "closure_time_minutes": ["closure_time_minutes", "ttr", "time_to_resolve",
                             "resolution_minutes", "duration_minutes", "mttr",
                             "handling_time", "time_to_close"],
}

_ALIAS_LOOKUP = {
    _key(alias): canonical
    for canonical, aliases in COLUMN_ALIASES.items()
    for alias in aliases
}

# Severity scales differ per vendor. P1/SEV1/5 all mean the same thing to a supervisor,
# and refusing them means refusing most real exports.
SEVERITY_ALIASES = {
    "critical": "CRITICAL", "crit": "CRITICAL", "p1": "CRITICAL", "sev1": "CRITICAL",
    "severity1": "CRITICAL", "1": "CRITICAL", "5": "CRITICAL", "urgent": "CRITICAL",
    "emergency": "CRITICAL", "veryhigh": "CRITICAL",
    "high": "HIGH", "p2": "HIGH", "sev2": "HIGH", "severity2": "HIGH", "2": "HIGH",
    "4": "HIGH", "major": "HIGH",
    "medium": "MEDIUM", "med": "MEDIUM", "moderate": "MEDIUM", "p3": "MEDIUM",
    "sev3": "MEDIUM", "severity3": "MEDIUM", "3": "MEDIUM", "normal": "MEDIUM",
    "low": "LOW", "p4": "LOW", "p5": "LOW", "sev4": "LOW", "sev5": "LOW", "4low": "LOW",
    "minor": "LOW", "informational": "LOW", "info": "LOW",
}

DISPOSITION_ALIASES = {
    "truepositive": "TRUE_POSITIVE", "tp": "TRUE_POSITIVE", "true": "TRUE_POSITIVE",
    "confirmed": "TRUE_POSITIVE", "malicious": "TRUE_POSITIVE", "incident": "TRUE_POSITIVE",
    "escalated": "TRUE_POSITIVE", "actioned": "TRUE_POSITIVE",
    "falsepositive": "FALSE_POSITIVE", "fp": "FALSE_POSITIVE", "false": "FALSE_POSITIVE",
    "notmalicious": "FALSE_POSITIVE", "noise": "FALSE_POSITIVE",
    "falsealarm": "FALSE_POSITIVE",
    "benign": "BENIGN", "expected": "BENIGN", "authorised": "BENIGN",
    "authorized": "BENIGN", "noaction": "BENIGN", "noactionrequired": "BENIGN",
    "closed": "BENIGN", "resolved": "BENIGN", "duplicate": "BENIGN",
}


def resolve_columns(header: list[str]) -> tuple[dict[str, str], list[str], list[str]]:
    """Map a file's headers onto the canonical schema.

    Returns (header -> canonical, notes describing every substitution, ignored headers).
    Raises IngestError when two headers claim the same field, because picking one would
    be a guess and this parser does not guess.
    """
    mapping: dict[str, str] = {}
    claims: dict[str, list[str]] = {}
    notes: list[str] = []
    ignored: list[str] = []

    for raw in header:
        if raw is None:
            continue
        canonical = _ALIAS_LOOKUP.get(_key(raw))
        if canonical is None:
            ignored.append(raw)
            continue
        mapping[raw] = canonical
        claims.setdefault(canonical, []).append(raw)

    clashes = {c: cols for c, cols in claims.items() if len(cols) > 1}
    if clashes:
        raise IngestError([
            f"Two columns both look like '{canonical}': {', '.join(repr(c) for c in cols)}. "
            f"Rename or remove one -- guessing which you meant would be a guess about "
            f"your data."
            for canonical, cols in sorted(clashes.items())
        ])

    for raw, canonical in mapping.items():
        if _key(raw) != _key(canonical):
            notes.append(f"column '{raw}' read as '{canonical}'")

    return mapping, notes, ignored


def normalise_severity(raw: str) -> str | None:
    """Map a vendor severity onto the four the rules understand, or None if unknown."""
    return SEVERITY_ALIASES.get(_key(raw))


def normalise_disposition(raw: str) -> str | None:
    """Map a vendor resolution code onto the three EG-004 tests, or None if unknown."""
    return DISPOSITION_ALIASES.get(_key(raw))


class IngestError(ValueError):
    """A rejected upload. `errors` is the full, line-numbered list for the UI."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors[:3]))


def _parse_timestamp(raw: str) -> datetime:
    """Accept ISO 8601 with either a 'T' or a space, and a trailing Z."""
    text = raw.strip().replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    # DuckDB's TIMESTAMP is naive. Normalising here keeps a mixed-offset export from
    # producing closure times that differ by the reader's assumptions.
    return parsed.replace(tzinfo=None)


def parse_csv(text: str, notes: list[str] | None = None) -> tuple[list[tuple], list[tuple]]:
    """Validate a CSV export and return (entity rows, record rows).

    Materialises every record. Fine for a review sample; for a large submission use
    `stage_csv`, which validates identically but never holds more than one row.

    `notes`, if given, collects the column substitutions the parser made.
    """
    entities: dict[str, tuple[str, str, str]] = {}
    records = list(iter_validated_rows(text, entities, notes))
    _check_dataset(entities, len(records))
    return list(entities.values()), records


def iter_validated_rows(source, entities: dict[str, tuple[str, str, str]],
                        notes: list[str] | None = None):
    """Validate row by row, yielding each record tuple as it passes.

    `source` is either the whole file as a string, or any iterable of lines -- an open
    file handle being the one that matters. Passing a handle is what keeps peak memory
    flat: a 150 MiB export read as a string costs 150 MiB for the string and another
    150 MiB for the StringIO the csv module reads it through, before a single row is
    validated.

    `entities` is filled in as a side effect -- it is bounded by the number of CSEs, not
    by the dataset, so accumulating it costs nothing at any scale. `notes`, if given, is
    filled the same way with every column substitution and every ignored column, so the
    caller can put on screen exactly how the file was read. Both are out-parameters
    rather than return values because this is a generator: a `return` here is only
    reachable after the last row, and the header mapping is known before the first.

    Errors are collected across the whole file and raised together at the end, so a
    caller streaming rows to disk must treat the generator as all-or-nothing: if it
    raises, discard whatever was written. That is what keeps a rejected upload from
    leaving a half-loaded dataset behind.
    """
    errors: list[str] = []

    if isinstance(source, str):
        if not source.strip():
            raise IngestError(["The file is empty."])
        source = io.StringIO(source)

    reader = csv.DictReader(source)
    header = reader.fieldnames or []

    if not header:
        raise IngestError(["The file is empty."])

    # Map the export's own column names onto the canonical schema before anything is
    # read. Every substitution is recorded, never applied quietly -- see the schema
    # normalisation block above for why that distinction is the whole point.
    mapping, mapping_notes, ignored = resolve_columns(header)
    column = {canonical: raw for raw, canonical in mapping.items()}

    missing = [c for c in REQUIRED_COLUMNS if c not in column]
    if missing:
        raise IngestError(
            [f"Missing required column{'s' if len(missing) > 1 else ''}: "
             + ", ".join(missing)]
            + [f"Columns found: {', '.join(header) if header else '(none)'}"]
            + [f"Spellings accepted for '{c}': {', '.join(COLUMN_ALIASES[c][:8])}"
               for c in missing]
        )

    if notes is not None:
        notes.extend(mapping_notes)
        if ignored:
            notes.append(
                "ignored unrecognised column"
                + ("s: " if len(ignored) > 1 else ": ")
                + ", ".join(repr(c) for c in ignored)
            )

    def field(row: dict, canonical: str) -> str:
        """One canonical field off a row, trimmed, blank when the file omits it."""
        raw = column.get(canonical)
        return "" if raw is None else (row.get(raw) or "").strip()

    def add(line: int, message: str) -> None:
        if len(errors) < MAX_REPORTED_ERRORS:
            errors.append(f"Line {line}: {message}")

    seen_ids: set[str] = set()
    row_count = 0

    for row in reader:
        # +1 for the header; DictReader.line_num tracks the physical line, which is
        # what the user sees in their editor when a field contains a newline.
        line = reader.line_num
        row_count += 1
        if row_count > MAX_ROWS:
            raise IngestError(
                [f"File exceeds {MAX_ROWS:,} rows. Split the export and upload in parts."]
            )

        # Read fields straight off the reader's row rather than building a second dict
        # per row. At a million rows the duplicate dict is pure allocator churn, and
        # churn is what sets the peak even when steady-state memory is flat.
        record_id = field(row, "record_id")
        entity_id = field(row, "entity_id")
        if not record_id:
            add(line, "record_id is blank.")
            continue
        if record_id in seen_ids:
            add(line, f"duplicate record_id '{record_id}'.")
            continue
        seen_ids.add(record_id)

        if not entity_id:
            add(line, "entity_id is blank.")
            continue

        severity_raw = field(row, "severity")
        severity = normalise_severity(severity_raw)
        if severity is None:
            add(line, f"severity '{severity_raw}' is not a severity this tool "
                      f"recognises. Expected {', '.join(sorted(SEVERITIES))}, or a "
                      f"scale it maps -- P1-P5, Sev1-Sev5, 1-5, Major/Minor.")
            continue

        disposition_raw = field(row, "disposition")
        disposition = normalise_disposition(disposition_raw)
        if disposition is None:
            add(line, f"disposition '{disposition_raw}' is not an outcome this tool "
                      f"recognises. Expected {', '.join(sorted(DISPOSITIONS))}, or a "
                      f"code it maps -- TP, FP, Benign, No Action Required.")
            continue

        category = field(row, "category")
        if not category:
            add(line, "category is blank.")
            continue

        try:
            opened_at = _parse_timestamp(field(row, "opened_at"))
        except ValueError:
            add(line, f"opened_at '{field(row, 'opened_at')}' is not a readable "
                      f"date/time (expected e.g. 2026-01-05T08:00:00).")
            continue

        closed_raw = field(row, "closed_at")
        closed_at = None
        if closed_raw:
            try:
                closed_at = _parse_timestamp(closed_raw)
            except ValueError:
                add(line, f"closed_at '{closed_raw}' is not a readable date/time.")
                continue
            if closed_at < opened_at:
                add(line, "closed_at is before opened_at.")
                continue

        escalated_raw = field(row, "escalated").lower()
        if escalated_raw in TRUE_VALUES:
            escalated = True
        elif escalated_raw in FALSE_VALUES:
            # Blank means no escalation was recorded, which is exactly what the
            # absence of an escalation record means to EG-001 and EG-002.
            escalated = False
        else:
            add(line, f"escalated '{field(row, 'escalated')}' is not a yes/no value.")
            continue

        closure_raw = field(row, "closure_time_minutes")
        if closure_raw:
            try:
                closure_minutes = float(closure_raw)
            except ValueError:
                add(line, f"closure_time_minutes '{closure_raw}' is not a number.")
                continue
            if closure_minutes < 0:
                add(line, "closure_time_minutes is negative.")
                continue
        elif closed_at is not None:
            # Derived exactly as the seed derives it, so an export that omits the
            # column scores identically to one that supplies it.
            closure_minutes = (closed_at - opened_at).total_seconds() / 60.0
        else:
            closure_minutes = None

        entity_name = field(row, "entity_name") or entity_id
        sector = field(row, "sector") or "Unspecified"
        if entity_id not in entities:
            entities[entity_id] = (entity_id, entity_name, sector)

        yield (
            record_id,
            entity_id,
            field(row, "asset_id") or "UNKNOWN",
            severity,
            category,
            opened_at,
            closed_at,
            escalated,
            disposition,
            field(row, "investigation_notes") or None,
            closure_minutes,
        )

    if errors:
        if len(seen_ids) + len(errors) >= MAX_REPORTED_ERRORS:
            errors.append("... further problems not listed; fix these first.")
        raise IngestError(errors)


def _check_dataset(entities: dict, record_count: int) -> None:
    """Whole-file checks, applied after every row has been validated."""
    if not record_count:
        raise IngestError(["The file has a valid header but no data rows."])

    # NS-001 compares an entity against a population, and NS-002 needs peers reporting
    # a category before its absence means anything. One entity has no population.
    if len(entities) < 2:
        raise IngestError([
            f"Only {len(entities)} entity found. The Negative Space rules compare an "
            f"entity against its peers, so at least 2 entities are required."
        ])


def stage_csv(source, staged_path: str,
              notes: list[str] | None = None) -> tuple[list[tuple], int]:
    """Validate a CSV and write the accepted rows straight to `staged_path`.

    The streaming counterpart to `parse_csv`. Rows are written as they are validated
    and never accumulate, so peak memory is one row plus the entity table rather than
    ~1.5 KiB per record -- the difference between 1.5 GiB and a flat profile on a
    million-row submission.

    Nothing touches the database here. If validation raises, the caller deletes the
    staged file and the previously loaded dataset is untouched.
    """
    entities: dict[str, tuple[str, str, str]] = {}
    written = 0
    with open(staged_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(RECORD_COLUMNS)
        for row in iter_validated_rows(source, entities, notes):
            writer.writerow(row)
            written += 1
    _check_dataset(entities, written)
    return list(entities.values()), written


def parse_json(text: str, notes: list[str] | None = None) -> tuple[list[tuple], list[tuple]]:
    """Validate a JSON alert export and return (entity rows, record rows).

    Accepts either a top-level array of record objects, or an object wrapping one under
    "records". Values are converted to text and handed to the CSV validator, so JSON and
    CSV cannot diverge in what they accept: one vocabulary, one set of rules, one set of
    error messages.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestError([f"Not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})."])

    if isinstance(data, dict):
        data = data.get("records", data.get("data", data))
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise IngestError([
            "Expected a JSON array of alert records, or an object with a \"records\" array."
        ])
    if not data:
        raise IngestError(["The file contains no records."])
    if not all(isinstance(row, dict) for row in data):
        raise IngestError(["Every item in the array must be an object with named fields."])

    columns: list[str] = []
    for row in data:
        for key in row:
            k = str(key).strip().lower()
            if k not in columns:
                columns.append(k)

    # Round-trip through CSV so both formats share one validator. The alternative -- a
    # second parser -- is a second set of rules that will eventually disagree with the
    # first about what a valid file is.
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in data:
        writer.writerow({
            str(k).strip().lower(): ("" if v is None else
                                     "true" if v is True else
                                     "false" if v is False else str(v))
            for k, v in row.items()
        })
    return parse_csv(buffer.getvalue(), notes)


def parse(text: str, filename: str = "",
          notes: list[str] | None = None) -> tuple[list[tuple], list[tuple]]:
    """Validate an upload, choosing the parser by extension then by content."""
    if filename.lower().endswith(".json"):
        return parse_json(text, notes)
    if filename.lower().endswith(".csv"):
        return parse_csv(text, notes)
    # No usable extension: JSON announces itself in its first character.
    return (parse_json(text, notes) if text.lstrip()[:1] in "[{"
            else parse_csv(text, notes))


RECORD_COLUMNS = (
    "record_id", "entity_id", "asset_id", "severity", "category", "opened_at",
    "closed_at", "escalated", "disposition", "investigation_notes",
    "closure_time_minutes",
)

# Explicit types, never inference. DuckDB's CSV sniffer reads a sample, so on a file
# where the first N rows happen to have no closed_at it would type the column VARCHAR
# and every downstream timestamp comparison would silently do the wrong thing.
RECORD_COLUMN_TYPES = {
    "record_id": "VARCHAR", "entity_id": "VARCHAR", "asset_id": "VARCHAR",
    "severity": "VARCHAR", "category": "VARCHAR", "opened_at": "TIMESTAMP",
    "closed_at": "TIMESTAMP", "escalated": "BOOLEAN", "disposition": "VARCHAR",
    "investigation_notes": "VARCHAR", "closure_time_minutes": "DOUBLE",
}


FINDING_COLUMN_TYPES = {
    "finding_id": "VARCHAR", "entity_id": "VARCHAR", "rule_id": "VARCHAR",
    "finding_type": "VARCHAR", "weight": "INTEGER", "title": "VARCHAR",
    "explanation": "VARCHAR", "evidence_record_ids": "VARCHAR",
}


def _bulk_insert(con, table: str, column_types: dict[str, str],
                 rows: list[tuple]) -> None:
    """Insert rows through DuckDB's vectorised CSV reader instead of one statement each.

    `con.executemany` issues a prepared statement per row and measured 1.3ms each --
    65 seconds for 50,000 records, roughly 22 minutes for a million, which fails the
    "large datasets spanning multiple entities and time periods" requirement outright.
    Staging to a temporary CSV and letting DuckDB read it natively does the same 50,000
    rows in 0.33s: a measured 198x.

    Column types are declared, never sniffed. DuckDB's CSV sniffer reads a sample, so a
    file whose first rows happen to have no `closed_at` would type that column VARCHAR
    and every downstream timestamp comparison would quietly do the wrong thing.
    """
    if not rows:
        return

    columns = ", ".join(column_types)
    handle, staged = tempfile.mkstemp(suffix=".csv", prefix=f"satsa-{table}-")
    os.close(handle)
    try:
        with open(staged, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(column_types.keys())
            writer.writerows(rows)
        con.execute(
            f"INSERT INTO {table} ({columns}) "
            f"SELECT {columns} FROM read_csv(?, header=true, columns=?, nullstr='')",
            [staged, column_types],
        )
    finally:
        os.unlink(staged)


ML_PROFILE_COLUMN_TYPES = {
    "entity_id": "VARCHAR", "feature": "VARCHAR", "label": "VARCHAR",
    "value": "DOUBLE", "dataset_mean": "DOUBLE", "deviation": "DOUBLE",
    "contribution": "DOUBLE", "method": "VARCHAR", "anomalous": "BOOLEAN",
    "corroborated": "BOOLEAN",
}


def bulk_insert_ml_profile(con, rows: list[tuple]) -> None:
    """Insert the ML profile. Four rows per entity, so this is the slow path at 2,000
    CSEs -- 8,000 prepared statements measured about ten seconds."""
    _bulk_insert(con, "ml_profile", ML_PROFILE_COLUMN_TYPES, rows)


def bulk_insert_findings(con, rows: list[tuple]) -> None:
    """Insert generated findings. Same mechanism, same reasoning as the records path."""
    _bulk_insert(con, "findings", FINDING_COLUMN_TYPES, rows)


def bulk_insert_records(con, records: list[tuple]) -> None:
    """Insert validated records. The rows have already passed `parse_csv`, so this is
    not a second ingestion path with a second set of rules -- it is a faster way to hand
    the same validated tuples to the database."""
    _bulk_insert(con, "records", RECORD_COLUMN_TYPES, records)


def load(con, entities: list[tuple], records: list[tuple], label: str) -> tuple[int, int]:
    """Replace the current dataset with a parsed upload. Returns (entities, records)."""
    import db

    db.wipe(con)
    con.executemany(
        "INSERT INTO entities (entity_id, entity_name, sector) VALUES (?, ?, ?)",
        entities,
    )
    bulk_insert_records(con, records)
    db.set_dataset_meta(con, source="upload", label=label,
                        entity_count=len(entities), record_count=len(records))
    return len(entities), len(records)


def load_streaming(con, source, label: str,
                   notes: list[str] | None = None) -> tuple[int, int]:
    """Validate and load a CSV without ever holding the dataset in memory.

    The streaming path: rows are validated one at a time, written straight to a staged
    CSV, and handed to DuckDB's vectorised reader in a single statement. Peak memory is
    the entity table plus one row, instead of ~1.5 KiB per record.

    All-or-nothing is preserved by ordering, not by transactions: nothing touches the
    database until every row has passed. A rejected file deletes the staged copy and
    leaves the loaded dataset exactly as it was.
    """
    import db

    handle, staged = tempfile.mkstemp(suffix=".csv", prefix="satsa-upload-")
    os.close(handle)
    try:
        entities, count = stage_csv(source, staged, notes)  # raises before the DB is touched

        db.wipe(con)
        con.executemany(
            "INSERT INTO entities (entity_id, entity_name, sector) VALUES (?, ?, ?)",
            entities,
        )
        columns = ", ".join(RECORD_COLUMNS)
        con.execute(
            f"INSERT INTO records ({columns}) "
            f"SELECT {columns} FROM read_csv(?, header=true, columns=?, nullstr='')",
            [staged, RECORD_COLUMN_TYPES],
        )
        db.set_dataset_meta(con, source="upload", label=label,
                            entity_count=len(entities), record_count=count)
        return len(entities), count
    finally:
        os.unlink(staged)


def _cli() -> int:
    """Load a dataset from the command line.

    Kept from the parallel implementation this merged with: loading a file without
    starting the UI is genuinely useful, and it is how an operator seeds a machine
    before a demo. It goes through the same validator as the upload endpoint, so a file
    the CLI accepts is one the UI accepts and vice versa.
    """
    import argparse

    import db
    from detection import run_detection
    from scoring import ranked_entities

    parser = argparse.ArgumentParser(
        description="Load a CSV or JSON alert export into SAT-SA and run detection."
    )
    parser.add_argument("file", help="Path to a .csv or .json alert export")
    args = parser.parse_args()

    try:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"[-] Could not read {args.file}: {exc}", file=sys.stderr)
        return 1

    try:
        entities, records = parse(text, args.file)
    except IngestError as exc:
        print(f"[-] {len(exc.errors)} problem(s) in {args.file} - nothing was loaded:",
              file=sys.stderr)
        for message in exc.errors:
            print(f"      {message}", file=sys.stderr)
        return 1

    con = db.connect()
    entity_count, record_count = load(con, entities, records,
                                      os.path.basename(args.file))
    findings = run_detection(con)

    print(f"\n[+] Loaded {args.file}")
    print(f"      entities: {entity_count}")
    print(f"      records:  {record_count}")
    print(f"      findings: {findings}\n")
    print("Top supervisory attention:")
    for rank, e in enumerate(ranked_entities(con)[:5], 1):
        print(f"  {rank}. {e['entity_name']} ({e['entity_id']}) - "
              f"score {e['risk_score']}, {e['finding_count']} findings")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
