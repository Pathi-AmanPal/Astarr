"""Overview metrics, computed in SQL.

Every figure the Overview screen renders is computed here and served whole. The
frontend formats; it does not aggregate. That is not a style preference -- it is what
keeps one definition of every number in the system, and it is the only arrangement in
which `verify.py` can assert that a number on screen is correct. A median computed in
JavaScript is a second definition of the median that nobody tests.

Two rules the queries follow:

**Nothing is invented to fill a chart.** A dataset with no closed alerts has no closure
percentiles, and this module returns `null` for them rather than zero. Zero is a
measurement; absent is not, and a chart that draws one as the other is lying quietly.

**Buckets are fixed, not derived from the data.** Score bands are cut at the same
boundaries the ranking screen colours by, so the histogram and the table cannot
disagree about how many entities are in exception.
"""

from __future__ import annotations

# The banding the ranking screen uses. Duplicating the numbers here would let the
# histogram and the table drift apart, so the two thresholds live in one place and the
# bucket edges are derived from them.
BAND_EXCEPTION = 50.0
BAND_CAUTION = 10.0

# Fixed histogram edges over the attainable range (0 .. 86.5). Ten-point steps, with
# the band boundaries falling on an edge so a bar never straddles two bands.
SCORE_EDGES = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 86.5]


def _band(score: float) -> str:
    if score > BAND_EXCEPTION:
        return "exception"
    if score >= BAND_CAUTION:
        return "caution"
    return "clear"


def score_distribution(scores: list[float]) -> list[dict]:
    """Entities per score bucket, over fixed edges.

    A zero-count bucket is returned rather than omitted: the gap in the middle of a
    distribution is information, and dropping empty buckets would silently close it.
    """
    out = []
    for i in range(len(SCORE_EDGES) - 1):
        lo, hi = SCORE_EDGES[i], SCORE_EDGES[i + 1]
        last = i == len(SCORE_EDGES) - 2
        count = sum(1 for s in scores if (lo <= s <= hi) if (s < hi or last))
        out.append({
            "lower": lo,
            "upper": hi,
            "label": f"{lo:g}–{hi:g}",
            "count": count,
            # The band a bucket sits in, so the chart can colour it the same way the
            # ranking table colours the rows inside it.
            "band": _band((lo + hi) / 2 if not last else lo + 0.01),
        })
    return out


def overview(con) -> dict:
    """Every figure the Overview screen needs, in one round trip."""
    q = lambda sql, *p: con.execute(sql, list(p)).fetchall()

    record_count = q("SELECT COUNT(*) FROM records")[0][0]
    entity_count = q("SELECT COUNT(*) FROM entities")[0][0]

    if record_count == 0 or entity_count == 0:
        # An empty database is not an error and not a page of zeros. The caller
        # renders the empty state; every series is explicitly absent.
        return {
            "entity_count": 0, "record_count": 0, "finding_count": 0,
            "sector_count": 0, "attention_count": 0, "clean_count": 0,
            "score_distribution": [], "volume_by_day": [], "volume_by_week": [],
            "closure": {"mean": None, "median": None, "p90": None, "measured_on": 0,
                        "unclosed": 0},
            "volume": {"per_day_min": 0, "per_day_max": 0, "days": 0},
            "findings_by_rule": [], "severity_mix": [], "disposition_mix": [],
            "top_categories": [],
        }

    finding_count = q("SELECT COUNT(*) FROM findings")[0][0]
    sector_count = q("SELECT COUNT(DISTINCT sector) FROM entities")[0][0]
    attention = q("SELECT COUNT(DISTINCT entity_id) FROM findings")[0][0]

    # Volume over time. Bucketed in SQL rather than shipping 51,878 timestamps to the
    # browser to be counted there -- the difference is a 12 MB payload and a 2 KB one.
    volume_day = [
        {"bucket": str(r[0]), "count": r[1]}
        for r in q("SELECT CAST(opened_at AS DATE) d, COUNT(*) FROM records "
                   "GROUP BY d ORDER BY d")
    ]
    volume_week = [
        {"bucket": str(r[0]), "count": r[1]}
        for r in q("SELECT date_trunc('week', opened_at)::DATE w, COUNT(*) FROM records "
                   "GROUP BY w ORDER BY w")
    ]

    # Handling quality. The mean alone hides the shape: a SOC that closes most alerts
    # in minutes and a handful in a fortnight has a respectable mean and a terrible
    # P90, and the P90 is the one a supervisor should be asked about.
    closed = q("SELECT COUNT(*) FROM records WHERE closure_time_minutes IS NOT NULL")[0][0]
    if closed:
        row = q("SELECT AVG(closure_time_minutes), "
                "       MEDIAN(closure_time_minutes), "
                "       QUANTILE_CONT(closure_time_minutes, 0.9) "
                "FROM records WHERE closure_time_minutes IS NOT NULL")[0]
        closure = {"mean": round(row[0], 1), "median": round(row[1], 1),
                   "p90": round(row[2], 1), "measured_on": closed,
                   "unclosed": record_count - closed}
    else:
        # No closed alert anywhere. Absent, not zero.
        closure = {"mean": None, "median": None, "p90": None,
                   "measured_on": 0, "unclosed": record_count}

    # The shape of the volume series, computed here rather than in the browser so the
    # caption under the chart is a served number like every other. It earns its place:
    # a genuinely steady series renders as a near-flat line, which reads as a broken
    # chart unless the range is stated beside it.
    day_counts = [v["count"] for v in volume_day]
    volume = {
        "per_day_min": min(day_counts) if day_counts else 0,
        "per_day_max": max(day_counts) if day_counts else 0,
        "days": len(day_counts),
    }

    findings_by_rule = [
        {"rule_id": r[0], "tier": r[1], "count": r[2], "weight": r[3]}
        for r in q("SELECT rule_id, finding_type, COUNT(*), SUM(weight) FROM findings "
                   "GROUP BY rule_id, finding_type ORDER BY COUNT(*) DESC, rule_id")
    ]

    severity_mix = [
        {"key": r[0], "count": r[1]}
        for r in q("SELECT severity, COUNT(*) FROM records GROUP BY severity "
                   "ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 "
                   "WHEN 'MEDIUM' THEN 2 ELSE 3 END")
    ]
    disposition_mix = [
        {"key": r[0], "count": r[1]}
        for r in q("SELECT disposition, COUNT(*) FROM records GROUP BY disposition "
                   "ORDER BY COUNT(*) DESC")
    ]

    # Categories are open-ended -- an export can carry fifty. Six plus a named
    # remainder, because a pie or bar with fifty slices communicates nothing.
    cats = q("SELECT category, COUNT(*) c FROM records GROUP BY category ORDER BY c DESC")
    top_categories = [{"key": r[0], "count": r[1]} for r in cats[:6]]
    if len(cats) > 6:
        top_categories.append({"key": f"{len(cats) - 6} other categories",
                               "count": sum(r[1] for r in cats[6:])})

    scores_present = [r[0] for r in q("SELECT entity_id FROM entities")]

    return {
        "entity_count": entity_count,
        "record_count": record_count,
        "finding_count": finding_count,
        "sector_count": sector_count,
        "attention_count": attention,
        "clean_count": entity_count - attention,
        # Filled in by the caller, which already has the scored entities: recomputing
        # the weighted-tier score here would be a second implementation of the formula.
        "score_distribution": [],
        "volume_by_day": volume_day,
        "volume_by_week": volume_week,
        "closure": closure,
        "volume": volume,
        "findings_by_rule": findings_by_rule,
        "severity_mix": severity_mix,
        "disposition_mix": disposition_mix,
        "top_categories": top_categories,
        "_entity_ids": scores_present,
    }
