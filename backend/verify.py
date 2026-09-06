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
import ingest
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

    print("\nML profile persistence (the corroboration layer's working)")
    profile = con.execute(
        "SELECT entity_id, feature, value, dataset_mean, deviation, contribution, "
        "method, anomalous, corroborated FROM ml_profile"
    ).fetchall()
    check("a profile row per entity per feature", len(profile) == 12 * 4,
          f"got {len(profile)}")
    check("profiles are written for clean entities too, not only flagged ones",
          len({p[0] for p in profile}) == 12, f"{len({p[0] for p in profile})} entities")

    # The profile explains the finding, so the two must agree about who was flagged.
    ml_entities = set(entities_for(con, ML_RULE_ID))
    corroborated = {p[0] for p in profile if p[8]}
    check("profile's corroborated set equals the ML findings' entities",
          corroborated == ml_entities, f"{sorted(corroborated)} vs {sorted(ml_entities)}")

    # Prove the negative: an entity the model calls anomalous but no rule flagged must
    # be recorded as anomalous-but-not-corroborated, never promoted into a finding.
    anomalous = {p[0] for p in profile if p[7]}
    check("every corroborated entity is also anomalous",
          corroborated <= anomalous, f"{sorted(corroborated - anomalous)} not anomalous")
    check("no entity is corroborated without a deterministic finding",
          all(con.execute(
              "SELECT COUNT(*) FROM findings WHERE entity_id = ? AND rule_id <> ?",
              [e, ML_RULE_ID]).fetchone()[0] > 0 for e in corroborated))

    means = {(p[1], round(p[3], 9)) for p in profile}
    check("the dataset mean for a feature is the same for every entity",
          len(means) == 4, f"{len(means)} distinct (feature, mean) pairs for 4 features")

    print("\nCSV ingestion (upload path)")
    entities_in, records_in = ingest.parse_csv(ingest.TEMPLATE_CSV)
    check("the downloadable template is itself a valid upload",
          len(entities_in) == 2 and len(records_in) == 3,
          f"{len(entities_in)} entities, {len(records_in)} records")

    derived = [r for r in records_in if r[0] == "ALT-0002"][0]
    check("closure_time_minutes is honoured when supplied", derived[10] == 148.0,
          f"got {derived[10]}")

    no_closure_col = "\n".join(
        line.rsplit(",", 1)[0] for line in ingest.TEMPLATE_CSV.strip().split("\n")
    )
    _e, derived_records = ingest.parse_csv(no_closure_col)
    check("closure_time_minutes is derived from the timestamps when omitted",
          [r for r in derived_records if r[0] == "ALT-0002"][0][10] == 148.0)

    def rejects(label: str, text: str, expect_substring: str) -> None:
        try:
            ingest.parse_csv(text)
        except ingest.IngestError as exc:
            joined = " | ".join(exc.errors)
            check(label, expect_substring in joined, joined[:110])
        else:
            check(label, False, "accepted a file it should have rejected")

    rejects("a missing required column is refused",
            "record_id,entity_id\nA-1,E-1\n", "Missing required column")
    rejects("an unknown severity is refused",
            ingest.TEMPLATE_CSV.replace("HIGH,Malware", "EXTREME,Malware"),
            "severity 'EXTREME'")
    rejects("an unreadable timestamp is refused",
            ingest.TEMPLATE_CSV.replace("2026-01-05T08:00:00,2026", "yesterday,2026"),
            "not a readable date/time")
    rejects("a duplicate record_id is refused",
            ingest.TEMPLATE_CSV + ingest.TEMPLATE_CSV.strip().split("\n")[1] + "\n",
            "duplicate record_id")
    rejects("closed_at before opened_at is refused",
            ingest.TEMPLATE_CSV.replace(
                "2026-01-05T08:00:00,2026-01-05T08:01:00", "2026-01-05T08:00:00,2026-01-04T08:00:00"),
            "before opened_at")
    rejects("a single-entity file is refused (peer rules need a population)",
            "\n".join(ingest.TEMPLATE_CSV.strip().split("\n")[:3]) + "\n",
            "at least 2 entities")
    rejects("a header with no data rows is refused",
            ingest.TEMPLATE_CSV.strip().split("\n")[0] + "\n", "no data rows")
    rejects("an empty file is refused", "   ", "empty")

    # Every problem in one pass: a validator that stops at the first error turns fixing
    # an export into one upload per mistake.
    multi = ingest.TEMPLATE_CSV.replace("HIGH,Malware", "EXTREME,Malware").replace(
        "CRITICAL,Unauthorized", "SEVERE,Unauthorized")
    try:
        ingest.parse_csv(multi)
        check("all problems are reported in one pass", False, "accepted an invalid file")
    except ingest.IngestError as exc:
        check("all problems are reported in one pass", len(exc.errors) == 2,
              f"reported {len(exc.errors)}")

    print("\nJSON ingestion shares the CSV validator")
    # Two parsers would mean two definitions of a valid file, drifting apart. JSON is
    # normalised into the CSV validator instead, and these checks are what hold that.
    import json as _json

    csv_entities, csv_records = ingest.parse_csv(ingest.TEMPLATE_CSV)
    header = ingest.TEMPLATE_CSV.strip().split("\n")[0].split(",")
    as_objects = [
        dict(zip(header, line.split(",")))
        for line in ingest.TEMPLATE_CSV.strip().split("\n")[1:]
    ]
    json_entities, json_records = ingest.parse(_json.dumps(as_objects), "x.json")
    check("the same data as JSON yields identical rows to CSV",
          (json_entities, json_records) == (csv_entities, csv_records))

    wrapped = ingest.parse(_json.dumps({"records": as_objects}), "x.json")
    check('a {"records": [...]} wrapper is accepted', wrapped[1] == csv_records)

    check("a JSON body is detected without a .json extension",
          ingest.parse(_json.dumps(as_objects), "")[1] == csv_records)

    def rejects_json(label: str, payload: str, expect: str) -> None:
        try:
            ingest.parse(payload, "x.json")
        except ingest.IngestError as exc:
            joined = " | ".join(exc.errors)
            check(label, expect in joined, joined[:110])
        else:
            check(label, False, "accepted a payload it should have rejected")

    rejects_json("malformed JSON is refused", "[{,}]", "Not valid JSON")
    rejects_json("a JSON array of non-objects is refused", "[1, 2, 3]",
                 "must be an object")
    rejects_json("an empty JSON array is refused", "[]", "no records")
    rejects_json("JSON with a bad severity is refused by the SAME rule as CSV",
                 _json.dumps([{**as_objects[0], "severity": "EXTREME"}, as_objects[2]]),
                 "severity 'EXTREME'")

    print("\nUploaded data runs the same pipeline as the seed")
    con3 = db.connect(os.path.join(tempfile.mkdtemp(), "verify3.duckdb"))
    up_entities, up_records = ingest.parse_csv(ingest.TEMPLATE_CSV)
    ingest.load(con3, up_entities, up_records, "template.csv")
    upload_findings = run_detection(con3)
    check("detection runs over uploaded records without error", upload_findings >= 0,
          f"{upload_findings} findings")
    check("provenance records the upload, not the demo seed",
          db.dataset_meta(con3)["source"] == "upload")
    check("an upload replaces the previous dataset rather than appending",
          con3.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 3)

    # Loading the demo seed over an upload must restore it completely.
    seed(con3)
    db.set_dataset_meta(con3, source="demo_seed", label="Synthetic demo dataset",
                        entity_count=12, record_count=248)
    run_detection(con3)
    check("the demo seed can be restored over an upload",
          con3.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 248
          and db.dataset_meta(con3)["source"] == "demo_seed")
    check("restored demo findings match the reference build",
          con3.execute(snapshot).fetchall() == con.execute(snapshot).fetchall())

    print("\nThe SQL engine and the Python rules agree exactly")
    # detection.run_detection is set-based; run_detection_python is the same rules with
    # every record in memory. The Python one is the specification, and these assert the
    # SQL one has not drifted from it -- not "equivalent", identical: same finding ids,
    # same order, same explanation strings, same evidence lists.
    import detection as _det

    snap = ("SELECT finding_id, entity_id, rule_id, finding_type, weight, title, "
            "explanation, evidence_record_ids FROM findings ORDER BY finding_id")

    con_py = db.connect(os.path.join(tempfile.mkdtemp(), "engine_py.duckdb"))
    seed(con_py)
    n_py = _det.run_detection_python(con_py)
    con_sql = db.connect(os.path.join(tempfile.mkdtemp(), "engine_sql.duckdb"))
    seed(con_sql)
    n_sql = _det.run_detection(con_sql)

    check("both engines generate the same number of findings", n_py == n_sql,
          f"python {n_py}, sql {n_sql}")
    rows_py = con_py.execute(snap).fetchall()
    rows_sql = con_sql.execute(snap).fetchall()
    check("every finding is byte-identical between the two engines", rows_py == rows_sql,
          f"{sum(1 for a, b in zip(rows_py, rows_sql) if a != b)} rows differ")
    check("both engines rank entities identically",
          ranked_entities(con_py) == ranked_entities(con_sql))

    # The finding-id sequence crosses 9,999, where DuckDB's lpad truncates a longer
    # string and Python's :04d does not. That collided on the primary key at 10,000
    # findings and was invisible on any small dataset.
    wide = ["record_id,entity_id,entity_name,sector,asset_id,severity,category,"
            "opened_at,closed_at,escalated,disposition,investigation_notes"]
    from datetime import datetime as _dt, timedelta as _td
    base = _dt(2026, 5, 1, 8, 0, 0)
    for i in range(12000):
        eid = f"E-{i % 3}"
        op = base + _td(minutes=i)
        # every row is a CRITICAL with no escalation, so EG-002 fires on all of them
        wide.append(f"W-{i:06d},{eid},Ent {i % 3},Sector,A-1,CRITICAL,Malware,"
                    f"{op.isoformat()},{(op + _td(minutes=30)).isoformat()},false,"
                    f"TRUE_POSITIVE,note {i}")
    con_wide = db.connect(os.path.join(tempfile.mkdtemp(), "wide.duckdb"))
    ew, rw = ingest.parse_csv("\n".join(wide) + "\n")
    ingest.load(con_wide, ew, rw, "wide.csv")
    n_wide = _det.run_detection(con_wide)
    check("finding ids stay unique past 9,999 (lpad truncation)",
          con_wide.execute("SELECT COUNT(DISTINCT finding_id) FROM findings").fetchone()[0]
          == n_wide, f"{n_wide} findings")
    # Compared as a set, not in query order: finding_id sorts lexicographically, so
    # F-10000 precedes F-1001 and an ordered comparison would fail on a correct sequence.
    all_ids = {r[0] for r in con_wide.execute("SELECT finding_id FROM findings").fetchall()}
    check("...and the sequence is exactly F-0001..F-N with no gaps or repeats",
          all_ids == {f"F-{i:04d}" for i in range(1, n_wide + 1)},
          f"{len(all_ids)} distinct of {n_wide}")

    print("\nStreaming ingestion matches materialised ingestion")
    # stage_csv validates one row at a time and writes straight to disk; parse_csv holds
    # the dataset. They must accept and reject exactly the same files.
    staged_path = os.path.join(tempfile.mkdtemp(), "staged.csv")
    ents_stream, n_stream = ingest.stage_csv(ingest.TEMPLATE_CSV, staged_path)
    ents_mat, recs_mat = ingest.parse_csv(ingest.TEMPLATE_CSV)
    check("streaming finds the same entities", ents_stream == ents_mat)
    check("streaming finds the same record count", n_stream == len(recs_mat))

    con_stream = db.connect(os.path.join(tempfile.mkdtemp(), "stream.duckdb"))
    ingest.load_streaming(con_stream, ingest.TEMPLATE_CSV, "template.csv")
    con_mat = db.connect(os.path.join(tempfile.mkdtemp(), "mat.duckdb"))
    ingest.load(con_mat, ents_mat, recs_mat, "template.csv")
    cols = ", ".join(ingest.RECORD_COLUMNS)
    check("the loaded rows are identical either way",
          con_stream.execute(f"SELECT {cols} FROM records ORDER BY record_id").fetchall()
          == con_mat.execute(f"SELECT {cols} FROM records ORDER BY record_id").fetchall())

    # A handle, not a string: the path that keeps peak memory flat.
    handle_path = os.path.join(tempfile.mkdtemp(), "from_handle.csv")
    with open(handle_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(ingest.TEMPLATE_CSV)
    con_handle = db.connect(os.path.join(tempfile.mkdtemp(), "handle.duckdb"))
    with open(handle_path, "r", encoding="utf-8-sig", newline="") as fh:
        ingest.load_streaming(con_handle, fh, "from_handle.csv")
    check("streaming from a file handle loads identically",
          con_handle.execute(f"SELECT {cols} FROM records ORDER BY record_id").fetchall()
          == con_mat.execute(f"SELECT {cols} FROM records ORDER BY record_id").fetchall())

    # The property that makes streaming safe: a file rejected halfway must leave the
    # previously loaded dataset untouched, not half-replaced.
    before_rows = con_mat.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    bad = ingest.TEMPLATE_CSV + ("BAD-1,CSE-01,One,Energy,A-1,NOTASEVERITY,Malware,"
                                 "2026-01-05T08:00:00,,false,TRUE_POSITIVE,,\n")
    try:
        ingest.load_streaming(con_mat, bad, "bad.csv")
        check("a rejected streaming upload leaves the dataset intact", False,
              "the bad file was accepted")
    except ingest.IngestError:
        check("a rejected streaming upload leaves the dataset intact",
              con_mat.execute("SELECT COUNT(*) FROM records").fetchone()[0] == before_rows
              and db.dataset_meta(con_mat) is not None)

    print("\nBulk insert preserves types and NULLs")
    # Records reach DuckDB through a staged CSV rather than one INSERT per row (198x
    # faster, measured). CSV has no type system, so the risk this trades for speed is
    # a value arriving as the wrong type or an empty string arriving as "" instead of
    # NULL. These assert the round-trip, not the speed.
    con4 = db.connect(os.path.join(tempfile.mkdtemp(), "verify4.duckdb"))
    typed = (
        "record_id,entity_id,entity_name,sector,asset_id,severity,category,opened_at,"
        "closed_at,escalated,disposition,investigation_notes,closure_time_minutes\n"
        # closed, escalated, notes present
        "R-1,E-1,One,Energy,A-1,HIGH,Malware,2026-01-05T08:00:00,2026-01-05T10:30:00,true,TRUE_POSITIVE,Checked.,150\n"
        # still open: no closed_at, no notes, not escalated
        "R-2,E-2,Two,Telecom,A-2,LOW,Phishing,2026-01-05T09:00:00,,false,BENIGN,,\n"
    )
    e4, r4 = ingest.parse_csv(typed)
    ingest.load(con4, e4, r4, "typed.csv")

    row = con4.execute(
        "SELECT opened_at, closed_at, escalated, investigation_notes, "
        "closure_time_minutes FROM records WHERE record_id = 'R-1'"
    ).fetchone()
    check("a timestamp survives as TIMESTAMP, not text",
          isinstance(row[0], _dt) and row[0] == _dt(2026, 1, 5, 8, 0), str(row[0]))
    check("a boolean survives as BOOLEAN", row[2] is True, repr(row[2]))
    check("a float survives as DOUBLE", row[4] == 150.0, repr(row[4]))

    open_row = con4.execute(
        "SELECT closed_at, investigation_notes, closure_time_minutes FROM records "
        "WHERE record_id = 'R-2'"
    ).fetchone()
    check("an absent closed_at is NULL, not an empty string", open_row[0] is None,
          repr(open_row[0]))
    check("absent notes are NULL, not an empty string", open_row[1] is None,
          repr(open_row[1]))
    check("an underivable closure time is NULL, not 0", open_row[2] is None,
          repr(open_row[2]))
    check("an unescalated row reads False, not NULL",
          con4.execute("SELECT escalated FROM records WHERE record_id='R-2'"
                       ).fetchone()[0] is False)

    # A comma and a quote in free text are the classic staging bug: written unescaped,
    # they shift every following column by one.
    tricky = typed + ('R-3,E-1,One,Energy,A-3,LOW,Malware,2026-01-06T08:00:00,'
                      '2026-01-06T09:00:00,false,BENIGN,"Comma, and ""quotes"" inside",60\n')
    e5, r5 = ingest.parse_csv(tricky)
    con5 = db.connect(os.path.join(tempfile.mkdtemp(), "verify5.duckdb"))
    ingest.load(con5, e5, r5, "tricky.csv")
    check("a comma and quotes inside free text do not shift columns",
          con5.execute("SELECT investigation_notes, closure_time_minutes FROM records "
                       "WHERE record_id='R-3'").fetchone()
          == ('Comma, and "quotes" inside', 60.0))

    # A newline inside a quoted field is the same bug one level nastier.
    multiline = typed + ('R-4,E-1,One,Energy,A-4,LOW,Malware,2026-01-07T08:00:00,'
                         '2026-01-07T09:00:00,false,BENIGN,"Line one\nline two",60\n')
    e6, r6 = ingest.parse_csv(multiline)
    con6 = db.connect(os.path.join(tempfile.mkdtemp(), "verify6.duckdb"))
    ingest.load(con6, e6, r6, "multiline.csv")
    check("a newline inside a quoted field survives the round-trip",
          con6.execute("SELECT investigation_notes FROM records WHERE record_id='R-4'"
                       ).fetchone()[0] == "Line one\nline two")
    check("...and the row count is still correct",
          con6.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 3)

    print("\nSchema normalisation: a messy export loads identically")
    # The tool ingests exports from many CSEs, and no two of them name their columns the
    # same way. The parser maps them onto the canonical schema -- but a mapping that is
    # silent is worse than a rejection, because a column read as the wrong field produces
    # findings that are confidently wrong. So: same rows in, same rows out, and every
    # substitution reported.
    canonical_rows = ingest.TEMPLATE_CSV.strip().split("\n")
    messy_header = ("Alert ID,Org_ID,Organisation,Industry,Hostname,Priority,Alert Type,"
                    "Created At,Resolved At,Escalated?,Resolution,Analyst Notes,TTR,"
                    "weird_extra")
    messy = [messy_header] + [row + ",junk" for row in canonical_rows[1:]]
    notes_messy: list[str] = []
    e_messy, r_messy = ingest.parse_csv("\n".join(messy) + "\n", notes_messy)
    e_canon, r_canon = ingest.parse_csv(ingest.TEMPLATE_CSV)
    check("a file with 13 non-standard headers loads the same records",
          r_messy == r_canon, f"{len(r_messy)} vs {len(r_canon)} rows")
    check("...and the same entities", e_messy == e_canon)
    check("...and every substitution is reported",
          len(notes_messy) >= 13, f"{len(notes_messy)} notes")
    check("...including the column it ignored",
          any("weird_extra" in n for n in notes_messy),
          "; ".join(notes_messy[-1:]))

    # A canonical file must report nothing. A banner that appears on every upload is a
    # banner nobody reads, which defeats the point of reporting the mapping at all.
    notes_clean: list[str] = []
    ingest.parse_csv(ingest.TEMPLATE_CSV, notes_clean)
    check("a canonical file reports no substitutions", notes_clean == [],
          "; ".join(notes_clean))

    # Vendor severity and disposition scales. P1/Sev1/1 all mean CRITICAL to a
    # supervisor, and refusing them means refusing most real exports.
    scales = ("record_id,entity_id,entity_name,sector,asset_id,priority,category,"
              "opened_at,resolution\n"
              "S-1,E-1,One,Energy,A-1,P1,Malware,2026-01-05T08:00:00,TP\n"
              "S-2,E-1,One,Energy,A-1,Sev 3,Malware,2026-01-05T09:00:00,FP\n"
              "S-3,E-2,Two,Energy,A-2,low,Malware,2026-01-05T10:00:00,No Action Required\n"
              "S-4,E-2,Two,Energy,A-2,4,Malware,2026-01-05T11:00:00,Confirmed\n")
    _es, rs = ingest.parse_csv(scales)
    check("vendor severity scales map onto the four the rules use",
          [r[3] for r in rs] == ["CRITICAL", "MEDIUM", "LOW", "HIGH"],
          str([r[3] for r in rs]))
    check("vendor resolution codes map onto the three EG-004 tests",
          [r[8] for r in rs] == ["TRUE_POSITIVE", "FALSE_POSITIVE", "BENIGN",
                                 "TRUE_POSITIVE"],
          str([r[8] for r in rs]))

    # Two columns claiming one field is the case where guessing would be indefensible:
    # either could be right and the tool has no way to tell. It stops and names both.
    ambiguous = ("record_id,entity_id,entity_name,sector,asset_id,severity,priority,"
                 "category,opened_at,disposition\n"
                 "A-1,E-1,One,Energy,A-1,HIGH,P1,Malware,2026-01-05T08:00:00,BENIGN\n")
    try:
        ingest.parse_csv(ambiguous)
        check("two columns claiming 'severity' is refused", False, "it was accepted")
    except ingest.IngestError as exc:
        check("two columns claiming 'severity' is refused", True)
        check("...and the error names both columns",
              "severity" in exc.errors[0] and "priority" in exc.errors[0],
              exc.errors[0])

    # A column that maps to nothing is still a missing required column, and the error
    # has to say which spellings would have worked -- otherwise the operator is guessing
    # at the guesser.
    unmappable = ("record_id,entity_id,entity_name,sector,asset_id,severity,category,"
                  "opened_at,xyzzy\n"
                  "U-1,E-1,One,Energy,A-1,HIGH,Malware,2026-01-05T08:00:00,BENIGN\n")
    try:
        ingest.parse_csv(unmappable)
        check("an unmappable required column is still refused", False, "it was accepted")
    except ingest.IngestError as exc:
        joined = " | ".join(exc.errors)
        check("an unmappable required column is still refused",
              "disposition" in exc.errors[0])
        check("...and the error lists spellings that would have worked",
              "verdict" in joined or "outcome" in joined, joined[:120])

    # Streaming must map identically. It shares iter_validated_rows, and this asserts
    # that it keeps sharing it.
    messy_staged = os.path.join(tempfile.mkdtemp(), "messy.csv")
    notes_stream: list[str] = []
    ents_messy_s, n_messy_s = ingest.stage_csv("\n".join(messy) + "\n", messy_staged,
                                               notes_stream)
    check("streaming ingestion maps columns identically",
          ents_messy_s == e_canon and n_messy_s == len(r_canon))
    check("...and reports the same substitutions", notes_stream == notes_messy)

    print("\nConcurrent reads on the shared connection")
    # The detail screen fetches its findings and its ML profile at the same time, and
    # FastAPI runs sync endpoints on a threadpool -- so two requests hit one DuckDB
    # connection concurrently. Unguarded, that interleaved reads and produced a
    # corrupted result (a ValueError out of scoring.py) and a spurious 404, both
    # intermittently. The endpoints hold a lock; this is the test that they keep doing so.
    import threading

    import main as api

    api.app.state.con = con
    errors: list[str] = []
    observed: list[tuple[str, str]] = []
    lock = threading.Lock()
    ids = ["CSE-01", "CSE-02", "CSE-03", "CSE-04", "CSE-05", "CSE-06"]

    def hammer(entity_id: str) -> None:
        try:
            for _ in range(6):
                detail = api.entity_detail(entity_id)
                profile = api.entity_ml_profile(entity_id)
                api.list_entities()
                with lock:
                    observed.append((detail["entity_id"], profile["entity_id"]))
        except Exception as exc:  # the failure mode was an exception, so catch broadly
            with lock:
                errors.append(f"{entity_id}: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=hammer, args=(e,)) for e in ids * 3]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check("concurrent detail + ML reads raise nothing",
          not errors, "; ".join(errors[:2]) if errors else "")
    check("every concurrent response is for the entity that was asked for",
          all(a == b for a, b in observed) and len(observed) == len(ids) * 3 * 6,
          f"{len(observed)} responses, "
          f"{sum(1 for a, b in observed if a != b)} mismatched")

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
