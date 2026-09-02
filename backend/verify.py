"""Seed and detection verification (PRD Section 12's mandated check, generalised).

Every rule must be confirmed to fire exactly where it was planted, and nowhere else,
before it is ever relied on in a demo. Run:

    python verify.py

Exits non-zero on the first failure.
"""

from __future__ import annotations

import os
import statistics
import sys
import tempfile
from collections import Counter

import db
from detection import (NS001_MIN_COHORT_SIZE, NS001_STDDEV_MULTIPLIER, ns001,
                       ns002_min_reporting, run_detection)
from ml import ML_RULE_ID, build_features, ml_corroboration
from scoring import TIER_CAP, TIER_WEIGHTS, ranked_entities, tier_breakdown
from seed import BLIND_SPOT_CATEGORY, seed

PASS, FAIL = "PASS", "FAIL"
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    line = f"  [{status}] {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    if not condition:
        _failures.append(label)


def findings_by_rule(con, rule_id: str) -> list[tuple]:
    return con.execute(
        "SELECT finding_id, entity_id, evidence_record_ids FROM findings "
        "WHERE rule_id = ? ORDER BY finding_id",
        [rule_id],
    ).fetchall()


def entities_for(con, rule_id: str) -> list[str]:
    return sorted(r[1] for r in findings_by_rule(con, rule_id))


def main() -> int:
    con = db.connect(os.path.join(tempfile.mkdtemp(), "verify.duckdb"))
    entities_loaded, records_loaded = seed(con)
    findings_generated = run_detection(con)

    print("\n1. Dataset shape")
    check("12 entities loaded", entities_loaded == 12, f"got {entities_loaded}")
    check("248 records loaded", records_loaded == 248, f"got {records_loaded}")
    counts = dict(con.execute(
        "SELECT entity_id, COUNT(*) FROM records GROUP BY entity_id ORDER BY entity_id"
    ).fetchall())
    expected_counts = {
        "CSE-01": 25, "CSE-02": 4, "CSE-03": 24, "CSE-04": 22,
        "CSE-05": 23, "CSE-06": 20, "CSE-07": 21, "CSE-08": 19,
        "CSE-09": 22, "CSE-10": 24, "CSE-11": 21, "CSE-12": 23,
    }
    check("per-entity counts match PRD Section 12", counts == expected_counts, str(counts))

    print("\n2. NS-001 threshold (PRD Section 12's mandated check)")
    values = [counts[k] for k in sorted(counts)]
    mean = statistics.fmean(values)
    std = statistics.pstdev(values)
    threshold = mean - NS001_STDDEV_MULTIPLIER * std
    print(f"      mean={mean:.4f}  pstdev={std:.4f}  threshold={threshold:.4f}")
    # Direction 1: the intended low-volume entity is still caught.
    check("CSE-02 is below the threshold", counts["CSE-02"] < threshold,
          f"4 < {threshold:.2f}, margin {threshold - counts['CSE-02']:.2f}")

    # Direction 2: no CLEAN entity has crossed from the other side. Adding entities
    # near the mean shrinks sigma and raises this threshold, so this is the margin
    # that erodes as the dataset grows -- and the one an expansion check forgets.
    next_lowest = min(v for k, v in counts.items() if k != "CSE-02")
    others_above = all(counts[e] >= threshold for e in counts if e != "CSE-02")
    check("no other entity is below the threshold", others_above,
          f"next lowest = {next_lowest}, margin {next_lowest - threshold:.2f}")
    check("clean-entity margin is comfortable (>= 3.0)",
          next_lowest - threshold >= 3.0,
          f"{next_lowest - threshold:.2f} above threshold")

    print("\n2b. NS-001 peer-cohort validity gate (Phase 2 Day 2)")
    # The gate decides whether a peer comparison is defensible at all. At 12 entities
    # across 12 distinct sectors every cohort holds one member, so nothing qualifies and
    # every entity uses the global baseline -- identical to Phase 1 behaviour.
    sectors = dict(con.execute("SELECT entity_id, sector FROM entities").fetchall())
    sizes = Counter(sectors.values())
    print(f"      {len(sectors)} entities across {len(sizes)} distinct sectors; "
          f"cohort sizes = {sorted(sizes.values())}")
    check("every sector cohort is below the minimum, so all fall back to global",
          all(n < NS001_MIN_COHORT_SIZE for n in sizes.values()),
          f"largest cohort = {max(sizes.values())}, minimum = {NS001_MIN_COHORT_SIZE}")
    check("the minimum is at least 2 (at n=1, sigma=0 turns the test into "
          "'count < count' and the rule silently stops firing)",
          NS001_MIN_COHORT_SIZE >= 2, f"min_cohort_size = {NS001_MIN_COHORT_SIZE}")

    ns001_rows = con.execute(
        "SELECT explanation FROM findings WHERE rule_id = 'NS-001'").fetchall()
    check("the finding states in words that it fell back to the global baseline",
          all("global baseline was used" in r[0] for r in ns001_rows),
          "a global comparison must never read as a peer one")
    check("...and names the cohort it could not use, with its size",
          all("holds 1 entity" in r[0] for r in ns001_rows))

    # The gate must be live code, not decoration. Rerun the rule against a synthetic
    # cohort assignment where sectors DO repeat, and confirm it switches baselines.
    records = con.execute(
        "SELECT record_id, entity_id FROM records ORDER BY record_id").fetchall()
    recs = [{"record_id": r[0], "entity_id": r[1]} for r in records]
    eids = sorted(sectors)

    # (a) all twelve in one qualifying cohort -> cohort baseline, not global
    one_cohort = {e: "Shared" for e in eids}
    got = ns001(recs, eids, one_cohort)
    check("with a qualifying cohort the rule uses the cohort baseline",
          len(got) == 1 and "Shared peer cohort (12 entities" in got[0]["explanation"],
          got[0]["explanation"][:70] if got else "no finding")
    check("...and stops claiming it fell back",
          got and "global baseline was used" not in got[0]["explanation"])

    # (b) a cohort one member short of the bar -> must still fall back
    short = {e: ("Small" if e in eids[:NS001_MIN_COHORT_SIZE - 1] else "Rest")
             for e in eids}
    got_short = ns001(recs, eids, short)
    cse02 = [f for f in got_short if f["entity_id"] == "CSE-02"]
    check(f"a cohort of {NS001_MIN_COHORT_SIZE - 1} (one short) still falls back",
          bool(cse02) and "global baseline was used" in cse02[0]["explanation"]
          if any(short[e] == "Small" for e in ["CSE-02"]) else True,
          f"CSE-02 cohort = {short['CSE-02']}, "
          f"size = {sum(1 for e in eids if short[e] == short['CSE-02'])}")

    # (c) the degenerate case the gate exists to prevent: without it, one-member
    #     cohorts give sigma=0 and NS-001 would find nothing at all.
    import detection as _d
    _saved = _d.NS001_MIN_COHORT_SIZE
    try:
        _d.NS001_MIN_COHORT_SIZE = 1          # disable the gate
        ungated = _d.ns001(recs, eids, sectors)
    finally:
        _d.NS001_MIN_COHORT_SIZE = _saved
    check("without the gate, one-member cohorts silence NS-001 entirely "
          "(this is what the gate prevents)",
          ungated == [], f"{len(ungated)} findings with the gate disabled")
    check("with the gate, NS-001 still fires on CSE-02", len(ns001_rows) == 1)

    print("\n3. Each rule fires exactly where planted")
    check("EG-001: 3 findings, all CSE-01", entities_for(con, "EG-001") == ["CSE-01"] * 3)
    check("EG-002: 4 findings (3x CSE-01, 1x CSE-05)",
          entities_for(con, "EG-002") == ["CSE-01"] * 3 + ["CSE-05"])
    check("EG-003: 1 finding on CSE-01", entities_for(con, "EG-003") == ["CSE-01"])
    check("EG-004: 5 findings (CSE-01, CSE-03, CSE-05 x2, CSE-06)",
          entities_for(con, "EG-004") == ["CSE-01", "CSE-03", "CSE-05", "CSE-05", "CSE-06"])
    check("EG-005: 1 finding on CSE-03", entities_for(con, "EG-005") == ["CSE-03"])
    check("NS-001: 1 finding on CSE-02", entities_for(con, "NS-001") == ["CSE-02"])
    check("NS-002: 1 finding on CSE-01", entities_for(con, "NS-002") == ["CSE-01"])

    print("\n4. Evidence matches each rule's stated condition")
    for _fid, _eid, ids in findings_by_rule(con, "EG-001"):
        row = con.execute(
            "SELECT closure_time_minutes, escalated, severity FROM records WHERE record_id = ?",
            [ids],
        ).fetchone()
        check(f"EG-001 evidence {ids}: <2 min, unescalated, HIGH/CRITICAL",
              row[0] < 2 and not row[1] and row[2] in ("HIGH", "CRITICAL"), str(row))

    eg003 = findings_by_rule(con, "EG-003")[0]
    eg003_ids = eg003[2].split(",")
    distinct_notes = con.execute(
        f"SELECT COUNT(DISTINCT LOWER(TRIM(investigation_notes))) FROM records "
        f"WHERE record_id IN ({','.join('?' for _ in eg003_ids)})", eg003_ids
    ).fetchone()[0]
    check("EG-003 evidence: 4 records sharing one exact notes string",
          len(eg003_ids) == 4 and distinct_notes == 1, f"{len(eg003_ids)} records")

    eg005_ids = findings_by_rule(con, "EG-005")[0][2].split(",")
    distinct_closed = con.execute(
        f"SELECT COUNT(DISTINCT closed_at) FROM records "
        f"WHERE record_id IN ({','.join('?' for _ in eg005_ids)})", eg005_ids
    ).fetchone()[0]
    check("EG-005 evidence: 5 records sharing one closed_at",
          len(eg005_ids) == 5 and distinct_closed == 1,
          f"{len(eg005_ids)} records, {distinct_closed} distinct timestamps")

    print("\n5. NS-002 baseline integrity")
    reporting = con.execute(
        "SELECT COUNT(DISTINCT entity_id) FROM records WHERE category = ?",
        [BLIND_SPOT_CATEGORY],
    ).fetchone()[0]
    entity_total = con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    bar = ns002_min_reporting(entity_total)
    print(f"      entities={entity_total}  proportional bar=ceil(0.75*{entity_total})={bar}")
    check(f"'{BLIND_SPOT_CATEGORY}' reported by 11 of {entity_total} entities",
          reporting == 11, f"got {reporting}")
    check(f"...which clears the proportional >={bar} expected-category bar",
          reporting >= bar, f"{reporting} >= {bar}")
    check("the bar is proportional, not the old absolute 6",
          ns002_min_reporting(8) == 6 and ns002_min_reporting(12) == 9,
          "ceil(.75*8)=6 preserves old behaviour; ceil(.75*12)=9")
    cse01_has = con.execute(
        "SELECT COUNT(*) FROM records WHERE entity_id = 'CSE-01' AND category = ?",
        [BLIND_SPOT_CATEGORY],
    ).fetchone()[0]
    check("CSE-01 filed zero records in that category", cse01_has == 0)

    print("\n5b. Added entities CSE-09..CSE-12 are clean and purely additive")
    NEW = ["CSE-09", "CSE-10", "CSE-11", "CSE-12"]
    for entity_id in NEW:
        n = con.execute(
            "SELECT COUNT(*) FROM findings WHERE entity_id = ?", [entity_id]
        ).fetchone()[0]
        check(f"{entity_id} has zero findings", n == 0, f"got {n}")

    # Existing records must be untouched: same ids, same content, same order.
    first_158 = con.execute(
        "SELECT COUNT(*) FROM records WHERE entity_id <= 'CSE-08'"
    ).fetchone()[0]
    check("CSE-01..CSE-08 still hold exactly 158 records", first_158 == 158,
          f"got {first_158}")
    max_old_id = con.execute(
        "SELECT MAX(record_id) FROM records WHERE entity_id <= 'CSE-08'"
    ).fetchone()[0]
    min_new_id = con.execute(
        "SELECT MIN(record_id) FROM records WHERE entity_id > 'CSE-08'"
    ).fetchone()[0]
    check("existing record ids unchanged; new ids appended after them",
          max_old_id == "ALT-0158" and min_new_id == "ALT-0159",
          f"{max_old_id} -> {min_new_id}")

    # No accidental EG-005 burst among the new filler records.
    worst = con.execute(
        """
        SELECT COALESCE(MAX(n), 0) FROM (
            SELECT COUNT(*) AS n FROM records
            WHERE entity_id > 'CSE-08' AND closed_at IS NOT NULL
            GROUP BY entity_id, DATE_TRUNC('minute', closed_at)
        )
        """
    ).fetchone()[0]
    check("no accidental bulk-closure burst in new entities", worst < 5,
          f"max {worst} records share a closed-minute (EG-005 needs 5)")

    print("\n6. Rule isolation (planted records trip only their own rule)")
    overlap = con.execute(
        """
        SELECT COUNT(*) FROM findings a JOIN findings b
          ON a.evidence_record_ids = b.evidence_record_ids
        WHERE a.rule_id IN ('EG-004', 'EG-005')
          AND b.rule_id IN ('EG-001', 'EG-002', 'EG-003')
        """
    ).fetchone()[0]
    check("no EG-004/EG-005 evidence also trips EG-001/002/003", overlap == 0,
          f"{overlap} overlaps")

    print("\n7. Exact score vector (weighted-tier formula, PRD Section 5 amendment)")
    # 0.45*EG + 0.40*NS + 0.15*ML, each tier capped at 100 individually first.
    expected_scores = {
        "CSE-01": 56.5,   # EG 215->100, NS 25, ML 10
        "CSE-05": 24.75,  # EG 55
        "CSE-03": 18.0,   # EG 40
        "CSE-02": 13.5,   # NS 30, ML 10
        "CSE-06": 6.75,   # EG 15
        "CSE-04": 0.0, "CSE-07": 0.0, "CSE-08": 0.0,
        "CSE-09": 0.0, "CSE-10": 0.0, "CSE-11": 0.0, "CSE-12": 0.0,
    }
    ranked = ranked_entities(con)
    actual = {e["entity_id"]: e["risk_score"] for e in ranked}
    check("scores match the confirmed plan", actual == expected_scores, str(actual))
    check("every score is a float, not an int",
          all(isinstance(e["risk_score"], float) for e in ranked))
    check("CSE-01 ranks first", ranked[0]["entity_id"] == "CSE-01")
    check("CSE-01 is strictly highest (no tie)",
          ranked[0]["risk_score"] > ranked[1]["risk_score"],
          f"{ranked[0]['risk_score']} vs {ranked[1]['risk_score']}")
    check("CSE-01 raw sum is still 250 and a tier is flagged capped",
          ranked[0]["risk_score_raw"] == 250 and ranked[0]["capped"],
          f"raw={ranked[0]['risk_score_raw']}")

    print("\n7b. The cap-free <= 100 guarantee")
    # The proof is a convex-combination argument and holds only while the tier weights
    # sum to 1.0. config.py asserts this at import; assert it again here so the
    # verification stands on its own rather than trusting the module it checks.
    total_weight = sum(TIER_WEIGHTS.values())
    check("tier weights sum to exactly 1.0", abs(total_weight - 1.0) < 1e-9,
          f"{TIER_WEIGHTS} -> {total_weight}")
    check("every score lies within [0, 100] with no outer cap applied",
          all(0 <= e["risk_score"] <= TIER_CAP for e in ranked))
    # Saturate all three tiers on paper: the formula must land exactly on the cap.
    saturated = tier_breakdown({t: 10_000 for t in TIER_WEIGHTS})
    check("all three tiers saturated gives exactly 100, never more",
          sum(t["contribution"] for t in saturated) == float(TIER_CAP),
          f"{sum(t['contribution'] for t in saturated)}")

    print("\n7c. Ranking consequences of the amendment (stated, not incidental)")
    # CSE-02 and CSE-03 both scored 40 under the additive formula and were separated
    # only by the entity_id tiebreak. Tier weighting separates them on merit: CSE-03's
    # 40 is all Execution Gap (x0.45), CSE-02's is Negative Space plus ML (x0.40/x0.15).
    order = [e["entity_id"] for e in ranked]
    check("CSE-03 now outranks CSE-02 (the one intended ranking change)",
          order.index("CSE-03") < order.index("CSE-02"),
          f"CSE-03 at #{order.index('CSE-03')+1}, CSE-02 at #{order.index('CSE-02')+1}")
    check("the old 40-point tie is gone",
          ranked[order.index("CSE-03")]["risk_score"]
          != ranked[order.index("CSE-02")]["risk_score"], "18.0 vs 13.5")
    check("ranking is otherwise unchanged from the additive formula",
          [order[i] for i in (0, 1, 4)] == ["CSE-01", "CSE-05", "CSE-06"],
          f"1st/2nd/5th = {[order[i] for i in (0, 1, 4)]}")

    # Seven entities still score zero, so the tiebreak stayed load-bearing even though
    # weighting happened to break the 40-point tie.
    dupes = {v: k for k, v in Counter(e["risk_score"] for e in ranked).items() if v > 1}
    check("the only remaining tie is the seven zero-scoring entities", dupes == {7: 0.0},
          str(dupes))
    zeros = [e["entity_id"] for e in ranked if e["risk_score"] == 0.0]
    check("tied entities order by entity_id ascending", zeros == sorted(zeros), str(zeros))
    check("full ranking is stable across a refetch",
          order == [e["entity_id"] for e in ranked_entities(con)])

    print("\n7d. Tier breakdown is footable (PRD Section 5 explainability)")
    # Under tier weighting the score no longer equals the sum of the finding weights on
    # screen, so the tier rows are what make Section 5's "visible breakdown" true.
    for e in ranked:
        check(f"{e['entity_id']}: tier contributions sum to the score",
              round(sum(t["contribution"] for t in e["tiers"]), 2) == e["risk_score"],
              " + ".join(str(t["contribution"]) for t in e["tiers"])
              + f" = {e['risk_score']}")
    cse01 = next(e for e in ranked if e["entity_id"] == "CSE-01")
    eg = next(t for t in cse01["tiers"] if t["tier"] == "EXECUTION_GAP")
    check("CSE-01's Execution Gap tier is the one that capped (215 -> 100)",
          eg["raw"] == 215 and eg["capped_value"] == 100 and eg["capped"],
          f"raw={eg['raw']} capped_value={eg['capped_value']}")
    check("raw total still equals the sum of every finding weight",
          sum(t["raw"] for t in cse01["tiers"]) == cse01["risk_score_raw"] == 250)

    print("\n8. PRD Section 10 step 2 (highest-risk entity shows both finding types)")
    top_types = set(r[0] for r in con.execute(
        "SELECT DISTINCT finding_type FROM findings WHERE entity_id = ?",
        [ranked[0]["entity_id"]],
    ).fetchall())
    # Superset, not equality: ML_CORROBORATION is a legitimate third type on this
    # entity. Section 10 step 2 requires at least one of each, not exactly two.
    check("top entity has both EXECUTION_GAP and NEGATIVE_SPACE findings",
          top_types >= {"EXECUTION_GAP", "NEGATIVE_SPACE"}, str(sorted(top_types)))

    print("\n9. ML corroboration (ML-001)")
    ids, matrix = build_features(con)
    check("one feature vector per entity", len(matrix) == 12 and len(matrix[0]) == 4,
          f"{len(matrix)}x{len(matrix[0]) if matrix else 0}")

    ml_entities = sorted(r[1] for r in findings_by_rule(con, ML_RULE_ID))
    rule_flagged = {r[0] for r in con.execute(
        "SELECT DISTINCT entity_id FROM findings WHERE rule_id <> ?", [ML_RULE_ID]
    ).fetchall()}
    print(f"      model raised ML-001 on : {ml_entities}")
    print(f"      rule/stat flagged      : {sorted(rule_flagged)}")

    check("ML-001 never appears on an entity without an EG/NS finding",
          all(e in rule_flagged for e in ml_entities))
    check("ML-001 weight is 10 (smallest in the system)",
          [r[0] for r in con.execute(
              "SELECT DISTINCT weight FROM findings WHERE rule_id = ?", [ML_RULE_ID]
          ).fetchall()] == [10])
    check("ML-001 uses its own finding_type",
          [r[0] for r in con.execute(
              "SELECT DISTINCT finding_type FROM findings WHERE rule_id = ?", [ML_RULE_ID]
          ).fetchall()] == ["ML_CORROBORATION"])

    # Exercise the gate directly rather than trusting that this dataset happened to
    # satisfy it: with nothing rule-flagged, the model must produce nothing at all.
    check("gate suppresses all ML output when no rule flagged anything",
          ml_corroboration(con, set()) == [], "empty flagged set -> no findings")
    check("the gate, not the model, is what limits output",
          len(ml_corroboration(con, set(ids))) >= len(ml_entities),
          "unrestricted gate yields at least as many")

    print("\n10. Determinism (two independent builds must be identical)")
    con2 = db.connect(os.path.join(tempfile.mkdtemp(), "verify2.duckdb"))
    seed(con2)
    run_detection(con2)
    snapshot = ("SELECT finding_id, entity_id, rule_id, weight, explanation, "
                "evidence_record_ids FROM findings ORDER BY finding_id")
    check("findings identical across builds",
          con.execute(snapshot).fetchall() == con2.execute(snapshot).fetchall())
    check("scores identical across builds",
          ranked_entities(con) == ranked_entities(con2))
    check("float scores are bit-identical across builds, not merely close",
          [e["risk_score"] for e in ranked_entities(con)]
          == [e["risk_score"] for e in ranked_entities(con2)])
    # 3 EG-001 + 4 EG-002 + 1 EG-003 + 5 EG-004 + 1 EG-005 + 1 NS-001 + 1 NS-002
    # 16 deterministic + 2 ML corroboration
    check("18 findings generated", findings_generated == 18, f"got {findings_generated}")

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} check(s)")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
