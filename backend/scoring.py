"""Risk scoring (PRD Section 5).

    entity_risk_score = MIN(100, SUM(weight of every finding for that entity))

Simple, transparent, additive, capped. No tiered or weighted-percentage formula in
Phase 1 -- that is deferred by Section 9.

`risk_score_raw` carries the uncapped sum alongside it. The formula is untouched; the
raw value exists only so the UI can say "100 - capped from 240" rather than showing a
number that does not equal the visible weights a judge can add up.
"""

from __future__ import annotations

SCORE_CAP = 100


def entity_scores(con) -> dict[str, dict]:
    """Per-entity capped score, raw sum, finding count, and alert count.

    Findings and records are counted in separate queries on purpose: joining both to
    `entities` at once multiplies the rows and inflates every aggregate.
    """
    rows = con.execute(
        """
        SELECT e.entity_id,
               COALESCE(SUM(f.weight), 0) AS raw,
               COUNT(f.finding_id)        AS n
        FROM entities e
        LEFT JOIN findings f ON f.entity_id = e.entity_id
        GROUP BY e.entity_id
        """
    ).fetchall()

    record_counts = dict(con.execute(
        """
        SELECT e.entity_id, COUNT(r.record_id)
        FROM entities e
        LEFT JOIN records r ON r.entity_id = e.entity_id
        GROUP BY e.entity_id
        """
    ).fetchall())

    return {
        entity_id: {
            "risk_score": min(SCORE_CAP, int(raw)),
            "risk_score_raw": int(raw),
            "capped": int(raw) > SCORE_CAP,
            "finding_count": int(n),
            "record_count": int(record_counts.get(entity_id, 0)),
        }
        for entity_id, raw, n in rows
    }


def ranked_entities(con) -> list[dict]:
    """Entities sorted by risk, highest first.

    The `entity_id` tiebreak is load-bearing: three entities score zero, and without a
    stable secondary sort their order could vary between runs -- which would fail the
    determinism check in PRD Section 10, step 5.
    """
    scores = entity_scores(con)
    rows = con.execute("SELECT entity_id, entity_name, sector FROM entities").fetchall()

    entities = [
        {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "sector": sector,
            **scores[entity_id],
        }
        for entity_id, entity_name, sector in rows
    ]
    entities.sort(key=lambda e: (-e["risk_score"], e["entity_id"]))
    return entities
