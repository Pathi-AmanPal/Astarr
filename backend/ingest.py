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

# A guard against a mis-selected file, not a licence limit. 50k alert rows is far more
# than any supervisory review sample and still parses in well under a second.
MAX_ROWS = 50_000

# Enough to fix an export in one pass without pasting a wall of text into the UI.
MAX_REPORTED_ERRORS = 25

TEMPLATE_CSV = """\
record_id,entity_id,entity_name,sector,asset_id,severity,category,opened_at,closed_at,escalated,disposition,investigation_notes,closure_time_minutes
ALT-0001,CSE-01,Northern Grid Operator,Energy,SRV-014,HIGH,Malware,2026-01-05T08:00:00,2026-01-05T08:01:00,false,FALSE_POSITIVE,,1.0
ALT-0002,CSE-01,Northern Grid Operator,Energy,SRV-014,CRITICAL,Unauthorized Access,2026-01-05T09:12:00,2026-01-05T11:40:00,false,TRUE_POSITIVE,Reviewed firewall logs; confirmed brute force.,148.0
ALT-0003,CSE-02,Coastal Telecom,Telecom,WKS-221,MEDIUM,Phishing,2026-01-06T10:05:00,2026-01-06T12:30:00,true,TRUE_POSITIVE,User reported; mailbox rule removed.,145.0
"""


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


def parse_csv(text: str) -> tuple[list[tuple], list[tuple]]:
    """Validate a CSV export and return (entity rows, record rows).

    Raises IngestError carrying every problem found, each prefixed with its line
    number as it appears in the user's file.
    """
    errors: list[str] = []

    if not text.strip():
        raise IngestError(["The file is empty."])

    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    normalised = [(h or "").strip().lower() for h in header]

    missing = [c for c in REQUIRED_COLUMNS if c not in normalised]
    if missing:
        raise IngestError(
            [f"Missing required column{'s' if len(missing) > 1 else ''}: "
             + ", ".join(missing)]
            + [f"Columns found: {', '.join(header) if header else '(none)'}"]
        )

    def add(line: int, message: str) -> None:
        if len(errors) < MAX_REPORTED_ERRORS:
            errors.append(f"Line {line}: {message}")

    records: list[tuple] = []
    entities: dict[str, tuple[str, str, str]] = {}
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

        value = {k: (row.get(k) or "").strip() for k in normalised if k}

        record_id = value.get("record_id", "")
        entity_id = value.get("entity_id", "")
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

        severity = value.get("severity", "").upper()
        if severity not in SEVERITIES:
            add(line, f"severity '{value.get('severity', '')}' is not one of "
                      f"{', '.join(sorted(SEVERITIES))}.")
            continue

        disposition = value.get("disposition", "").upper()
        if disposition not in DISPOSITIONS:
            add(line, f"disposition '{value.get('disposition', '')}' is not one of "
                      f"{', '.join(sorted(DISPOSITIONS))}.")
            continue

        category = value.get("category", "")
        if not category:
            add(line, "category is blank.")
            continue

        try:
            opened_at = _parse_timestamp(value.get("opened_at", ""))
        except ValueError:
            add(line, f"opened_at '{value.get('opened_at', '')}' is not a readable "
                      f"date/time (expected e.g. 2026-01-05T08:00:00).")
            continue

        closed_raw = value.get("closed_at", "")
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

        escalated_raw = value.get("escalated", "").lower()
        if escalated_raw in TRUE_VALUES:
            escalated = True
        elif escalated_raw in FALSE_VALUES:
            # Blank means no escalation was recorded, which is exactly what the
            # absence of an escalation record means to EG-001 and EG-002.
            escalated = False
        else:
            add(line, f"escalated '{value.get('escalated', '')}' is not a yes/no value.")
            continue

        closure_raw = value.get("closure_time_minutes", "")
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

        entity_name = value.get("entity_name", "") or entity_id
        sector = value.get("sector", "") or "Unspecified"
        if entity_id not in entities:
            entities[entity_id] = (entity_id, entity_name, sector)

        records.append((
            record_id,
            entity_id,
            value.get("asset_id", "") or "UNKNOWN",
            severity,
            category,
            opened_at,
            closed_at,
            escalated,
            disposition,
            value.get("investigation_notes", "") or None,
            closure_minutes,
        ))

    if errors:
        if len(seen_ids) + len(errors) >= MAX_REPORTED_ERRORS:
            errors.append("... further problems not listed; fix these first.")
        raise IngestError(errors)

    if not records:
        raise IngestError(["The file has a valid header but no data rows."])

    # NS-001 compares an entity against a population, and NS-002 needs peers reporting
    # a category before its absence means anything. One entity has no population.
    if len(entities) < 2:
        raise IngestError([
            f"Only {len(entities)} entity found. The Negative Space rules compare an "
            f"entity against its peers, so at least 2 entities are required."
        ])

    return list(entities.values()), records


def parse_json(text: str) -> tuple[list[tuple], list[tuple]]:
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
    return parse_csv(buffer.getvalue())


def parse(text: str, filename: str = "") -> tuple[list[tuple], list[tuple]]:
    """Validate an upload, choosing the parser by extension then by content."""
    if filename.lower().endswith(".json"):
        return parse_json(text)
    if filename.lower().endswith(".csv"):
        return parse_csv(text)
    # No usable extension: JSON announces itself in its first character.
    return parse_json(text) if text.lstrip()[:1] in "[{" else parse_csv(text)


def load(con, entities: list[tuple], records: list[tuple], label: str) -> tuple[int, int]:
    """Replace the current dataset with a parsed upload. Returns (entities, records)."""
    import db

    db.wipe(con)
    con.executemany(
        "INSERT INTO entities (entity_id, entity_name, sector) VALUES (?, ?, ?)",
        entities,
    )
    con.executemany(
        """
        INSERT INTO records (record_id, entity_id, asset_id, severity, category,
                             opened_at, closed_at, escalated, disposition,
                             investigation_notes, closure_time_minutes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        records,
    )
    db.set_dataset_meta(con, source="upload", label=label,
                        entity_count=len(entities), record_count=len(records))
    return len(entities), len(records)


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
