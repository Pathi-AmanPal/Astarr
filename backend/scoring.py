"""Risk scoring (PRD Section 5, weighted-tier amendment 2026-09-02).

    EG = MIN(100, SUM(EXECUTION_GAP weights))
    NS = MIN(100, SUM(NEGATIVE_SPACE weights))
    ML = MIN(100, SUM(ML_CORROBORATION weights))

    entity_risk_score = 0.45*EG + 0.40*NS + 0.15*ML

This replaces Phase 1's `MIN(100, SUM(all weights))`. The old formula is struck in
PRD Section 5 and PRODUCT.md, not deleted -- it is the published Phase 1 behaviour and
the record of what changed matters more than a tidy document.

**Why no outer cap is needed.** Each tier is clamped into [0, 100] *before* weighting,
and the three tier weights sum to exactly 1.0, so the score is a convex combination of
three values each <= 100:

    0.45(100) + 0.40(100) + 0.15(100) = 100 * (0.45 + 0.40 + 0.15) = 100

The lower bound is 0 by the same argument. The guarantee rests entirely on the weights
summing to 1.0, which is invisible in the arithmetic and easy to break by tuning one
coefficient -- so `config.py` asserts it at startup rather than trusting the YAML.

**Honest limitation, stated rather than hidden.** 100 is unreachable in practice.
`ml_corroboration` emits at most one ML-001 per entity at weight 10, so the ML tier
cannot exceed 10 and the real ceiling is 0.45(100) + 0.40(100) + 0.15(10) = 86.5. The
score is a comparable ranking scale, not a percentage of anything, and no UI copy may
call it one.

Scores are floats. Rounding to int was rejected: the tier weights produce halves
(56.5, 13.5) and Python's round() is banker's rounding, which would send 56.5 to 56
while sending 13.5 to 14 -- an inconsistency no one reading the breakdown could explain.
"""

from __future__ import annotations

import config

# Tier order is presentation order, highest weight first. Fixed, not sorted at runtime,
# so the breakdown reads the same on every screen and in every run.
TIERS = ("EXECUTION_GAP", "NEGATIVE_SPACE", "ML_CORROBORATION")

TIER_CAP = config.TIER_CAP
TIER_WEIGHTS = config.TIER_WEIGHTS

# The practical ceiling, computed rather than asserted, so it stays true if the ML
# layer ever gains a second rule. Surfaced through the API so UI copy cannot drift
# from it.
MAX_ATTAINABLE_ML = config.WEIGHTS["ML-001"]


def _round(value: float) -> float:
    """Two decimal places. Every attainable score is an exact multiple of 0.05."""
    return round(value + 0.0, 2)


def tier_breakdown(raw_by_tier: dict[str, int]) -> list[dict]:
    """Per-tier raw sum, individual cap, weight, and weighted contribution."""
    out = []
    for tier in TIERS:
        raw = int(raw_by_tier.get(tier, 0))
        capped_value = min(TIER_CAP, raw)
        weight = TIER_WEIGHTS[tier]
        out.append({
            "tier": tier,
            "raw": raw,
            "capped_value": capped_value,
            "capped": raw > TIER_CAP,
            "weight": weight,
            "contribution": _round(weight * capped_value),
        })
    return out


def entity_scores(con) -> dict[str, dict]:
    """Per-entity weighted-tier score, tier breakdown, finding count, record count.

    Findings and records are counted in separate queries on purpose: joining both to
    `entities` at once multiplies the rows and inflates every aggregate.
    """
    tier_rows = con.execute(
        """
        SELECT e.entity_id, f.finding_type, COALESCE(SUM(f.weight), 0)
        FROM entities e
        LEFT JOIN findings f ON f.entity_id = e.entity_id
        GROUP BY e.entity_id, f.finding_type
        """
    ).fetchall()

    raw_by_entity: dict[str, dict[str, int]] = {}
    for entity_id, finding_type, total in tier_rows:
        bucket = raw_by_entity.setdefault(entity_id, {})
        if finding_type is not None:  # LEFT JOIN miss: entity with no findings
            bucket[finding_type] = bucket.get(finding_type, 0) + int(total)

    counts = dict(con.execute(
        """
        SELECT e.entity_id, COUNT(f.finding_id)
        FROM entities e
        LEFT JOIN findings f ON f.entity_id = e.entity_id
        GROUP BY e.entity_id
        """
    ).fetchall())

    record_counts = dict(con.execute(
        """
        SELECT e.entity_id, COUNT(r.record_id)
        FROM entities e
        LEFT JOIN records r ON r.entity_id = e.entity_id
        GROUP BY e.entity_id
        """
    ).fetchall())

    out = {}
    for entity_id, raw_by_tier in raw_by_entity.items():
        tiers = tier_breakdown(raw_by_tier)
        score = _round(sum(t["contribution"] for t in tiers))
        # Belt and braces: the convex-combination proof is only as good as the config
        # invariant behind it, and a score over the cap must never reach a screen.
        assert 0 <= score <= TIER_CAP, f"{entity_id}: {score} outside [0, {TIER_CAP}]"
        out[entity_id] = {
            "risk_score": score,
            "risk_score_raw": sum(t["raw"] for t in tiers),
            "capped": any(t["capped"] for t in tiers),
            "tiers": tiers,
            "finding_count": int(counts.get(entity_id, 0)),
            "record_count": int(record_counts.get(entity_id, 0)),
        }
    return out


def ranked_entities(con) -> list[dict]:
    """Entities sorted by risk, highest first.

    The `entity_id` tiebreak is load-bearing: seven entities score zero, and without a
    stable secondary sort their order could vary between runs -- which would fail the
    determinism check in PRD Section 10, step 5. Weighted tiers happen to break the old
    CSE-02/CSE-03 tie at 40, but the tiebreak is not thereby redundant.
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
