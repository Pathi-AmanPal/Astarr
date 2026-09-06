"""Server-side analytics aggregation engine (PRD Section 5).

All metrics are computed in DuckDB SQL and exposed through Pydantic models.
Zero raw record fetches into Python for aggregations (NFR 12.5).
"""

from __future__ import annotations

import duckdb


def get_overview_metrics(con: duckdb.DuckDBPyConnection) -> dict:
    """Headline metrics for the dataset."""
    entity_count = con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    if entity_count == 0:
        return {
            "entities_count": 0,
            "alerts_count": 0,
            "findings_count": 0,
            "attention_entities_count": 0,
            "clean_entity_share": 0.0,
            "mean_closure_minutes": None,
            "median_closure_minutes": None,
            "p90_closure_minutes": None,
            "mean_median_gap_minutes": None,
            "confidence": "unavailable",
        }

    alert_count = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    finding_count = con.execute("SELECT COUNT(*) FROM findings").fetchone()[0]

    attention_count = con.execute(
        "SELECT COUNT(DISTINCT entity_id) FROM findings"
    ).fetchone()[0]

    clean_share = round((entity_count - attention_count) / entity_count, 4) if entity_count > 0 else 0.0

    closure_row = con.execute(
        """
        SELECT 
            AVG(closure_time_minutes),
            MEDIAN(closure_time_minutes),
            QUANTILE_CONT(closure_time_minutes, 0.90)
        FROM records 
        WHERE closure_time_minutes IS NOT NULL
        """
    ).fetchone()

    mean_c = round(closure_row[0], 2) if closure_row[0] is not None else None
    med_c = round(closure_row[1], 2) if closure_row[1] is not None else None
    p90_c = round(closure_row[2], 2) if closure_row[2] is not None else None

    gap_c = round(mean_c - med_c, 2) if (mean_c is not None and med_c is not None) else None

    confidence = "ok" if (entity_count >= 5 and alert_count >= 20) else "low"

    return {
        "entities_count": entity_count,
        "alerts_count": alert_count,
        "findings_count": finding_count,
        "attention_entities_count": attention_count,
        "clean_entity_share": clean_share,
        "mean_closure_minutes": mean_c,
        "median_closure_minutes": med_c,
        "p90_closure_minutes": p90_c,
        "mean_median_gap_minutes": gap_c,
        "confidence": confidence,
    }


def get_timeseries_metrics(con: duckdb.DuckDBPyConnection, bucket: str = "day") -> list[dict]:
    """Alert volume over time, bucketed by day or week."""
    date_trunc = "day" if bucket == "day" else "week"
    rows = con.execute(
        f"""
        SELECT 
            DATE_TRUNC('{date_trunc}', opened_at) AS period,
            COUNT(*) AS total_alerts,
            COUNT(CASE WHEN severity = 'CRITICAL' THEN 1 END) AS critical_count,
            COUNT(CASE WHEN severity = 'HIGH' THEN 1 END) AS high_count,
            COUNT(CASE WHEN severity = 'MEDIUM' THEN 1 END) AS medium_count,
            COUNT(CASE WHEN severity = 'LOW' THEN 1 END) AS low_count
        FROM records
        GROUP BY period
        ORDER BY period ASC
        """
    ).fetchall()

    return [
        {
            "period": r[0].strftime("%Y-%m-%d") if hasattr(r[0], "strftime") else str(r[0]),
            "total": r[1],
            "critical": r[2],
            "high": r[3],
            "medium": r[4],
            "low": r[5],
        }
        for r in rows
    ]


def get_distribution_metrics(con: duckdb.DuckDBPyConnection, by: str) -> dict:
    """Distribution breakdown by severity, category, disposition, or score."""
    total_records = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    if by == "severity":
        rows = con.execute(
            """
            SELECT severity, COUNT(*) 
            FROM records 
            GROUP BY severity
            """
        ).fetchall()
        counts = {r[0]: r[1] for r in rows}
        items = []
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            c = counts.get(sev, 0)
            pct = round(c / total_records * 100, 1) if total_records > 0 else 0.0
            items.append({"name": sev, "count": c, "percentage": pct})
        return {"by": "severity", "total": total_records, "items": items}

    elif by == "category":
        rows = con.execute(
            """
            SELECT category, COUNT(*) 
            FROM records 
            GROUP BY category 
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()
        items = [
            {
                "name": r[0],
                "count": r[1],
                "percentage": round(r[1] / total_records * 100, 1) if total_records > 0 else 0.0,
            }
            for r in rows
        ]
        return {"by": "category", "total": total_records, "items": items}

    elif by == "disposition":
        rows = con.execute(
            """
            SELECT disposition, COUNT(*) 
            FROM records 
            GROUP BY disposition
            """
        ).fetchall()
        items = [
            {
                "name": r[0],
                "count": r[1],
                "percentage": round(r[1] / total_records * 100, 1) if total_records > 0 else 0.0,
            }
            for r in rows
        ]
        return {"by": "disposition", "total": total_records, "items": items}

    elif by == "score":
        from scoring import ranked_entities
        entities = ranked_entities(con)
        bands = {"Exception (>= 40)": 0, "Caution (15 - 39)": 0, "Clear (< 15)": 0}
        for e in entities:
            score = e["risk_score"]
            if score >= 40.0:
                bands["Exception (>= 40)"] += 1
            elif score >= 15.0:
                bands["Caution (15 - 39)"] += 1
            else:
                bands["Clear (< 15)"] += 1
        items = [
            {
                "name": k,
                "count": v,
                "percentage": round(v / len(entities) * 100, 1) if len(entities) > 0 else 0.0,
            }
            for k, v in bands.items()
        ]
        return {"by": "score", "total": len(entities), "items": items}

    raise ValueError(f"Invalid distribution type: {by}")


def get_handling_quality(con: duckdb.DuckDBPyConnection) -> dict:
    """Handling quality percentiles and risk rates."""
    total_records = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    if total_records == 0:
        return {
            "total_records": 0,
            "mean_closure_minutes": None,
            "median_closure_minutes": None,
            "p90_closure_minutes": None,
            "rapid_closure_rate": 0.0,
            "critical_escalation_rate": 0.0,
            "undocumented_dismissal_rate": 0.0,
            "note_duplication_rate": 0.0,
        }

    closure_row = con.execute(
        """
        SELECT 
            AVG(closure_time_minutes),
            MEDIAN(closure_time_minutes),
            QUANTILE_CONT(closure_time_minutes, 0.90)
        FROM records 
        WHERE closure_time_minutes IS NOT NULL
        """
    ).fetchone()

    # EG-001 count
    rapid_count = con.execute(
        """
        SELECT COUNT(*) FROM records
        WHERE severity IN ('HIGH', 'CRITICAL')
          AND closure_time_minutes IS NOT NULL
          AND closure_time_minutes < 2.0
          AND escalated = False
        """
    ).fetchone()[0]

    # Critical escalation rate
    crit_total = con.execute("SELECT COUNT(*) FROM records WHERE severity = 'CRITICAL'").fetchone()[0]
    crit_esc = con.execute("SELECT COUNT(*) FROM records WHERE severity = 'CRITICAL' AND escalated = True").fetchone()[0]
    crit_esc_rate = round(crit_esc / crit_total, 4) if crit_total > 0 else 1.0

    # EG-004 count (HIGH/CRITICAL dismissed FALSE_POSITIVE/BENIGN with empty notes)
    undoc_count = con.execute(
        """
        SELECT COUNT(*) FROM records
        WHERE severity IN ('HIGH', 'CRITICAL')
          AND disposition IN ('FALSE_POSITIVE', 'BENIGN')
          AND (investigation_notes IS NULL OR TRIM(investigation_notes) = '')
        """
    ).fetchone()[0]

    high_crit_total = con.execute("SELECT COUNT(*) FROM records WHERE severity IN ('HIGH', 'CRITICAL')").fetchone()[0]
    rapid_rate = round(rapid_count / high_crit_total, 4) if high_crit_total > 0 else 0.0
    undoc_rate = round(undoc_count / high_crit_total, 4) if high_crit_total > 0 else 0.0

    # EG-003 duplicated notes count
    dup_notes_count = con.execute(
        """
        WITH dupes AS (
            SELECT entity_id, investigation_notes, COUNT(*) as cnt
            FROM records
            WHERE investigation_notes IS NOT NULL AND TRIM(investigation_notes) != ''
            GROUP BY entity_id, investigation_notes
            HAVING COUNT(*) >= 3
        )
        SELECT COALESCE(SUM(r.cnt), 0) FROM dupes r
        """
    ).fetchone()[0]

    dup_rate = round(dup_notes_count / total_records, 4) if total_records > 0 else 0.0

    return {
        "total_records": total_records,
        "mean_closure_minutes": round(closure_row[0], 2) if closure_row[0] is not None else None,
        "median_closure_minutes": round(closure_row[1], 2) if closure_row[1] is not None else None,
        "p90_closure_minutes": round(closure_row[2], 2) if closure_row[2] is not None else None,
        "rapid_closure_rate": rapid_rate,
        "critical_escalation_rate": crit_esc_rate,
        "undocumented_dismissal_rate": undoc_rate,
        "note_duplication_rate": dup_rate,
    }


def get_case_tree(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """5-level case tree: Entity -> Tier -> Rule -> Instance -> Records."""
    from scoring import ranked_entities
    entities = ranked_entities(con)
    tree = []

    for entity in entities:
        eid = entity["entity_id"]
        findings = con.execute(
            """
            SELECT finding_id, rule_id, finding_type, weight, title, explanation, evidence_record_ids
            FROM findings
            WHERE entity_id = ?
            ORDER BY finding_id
            """,
            [eid],
        ).fetchall()

        if not findings:
            continue

        tier_nodes = {}
        for f in findings:
            fid, rule_id, ftype, weight, title, explanation, ev_ids_str = f
            ev_ids = [x.strip() for x in ev_ids_str.split(",") if x.strip()]
            
            records = []
            if ev_ids:
                placeholders = ",".join(["?"] * len(ev_ids))
                r_rows = con.execute(
                    f"""
                    SELECT record_id, asset_id, severity, category, opened_at, closed_at, escalated, disposition, investigation_notes, closure_time_minutes
                    FROM records
                    WHERE record_id IN ({placeholders})
                    """,
                    ev_ids,
                ).fetchall()
                for r in r_rows:
                    records.append({
                        "record_id": r[0],
                        "asset_id": r[1],
                        "severity": r[2],
                        "category": r[3],
                        "opened_at": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
                        "closed_at": r[5].isoformat() if r[5] and hasattr(r[5], "isoformat") else str(r[5]) if r[5] else None,
                        "escalated": bool(r[6]),
                        "disposition": r[7],
                        "investigation_notes": r[8],
                        "closure_time_minutes": r[9],
                    })

            instance_node = {
                "id": fid,
                "label": f"{title} ({weight} pts)",
                "type": "instance",
                "finding_id": fid,
                "rule_id": rule_id,
                "title": title,
                "weight": weight,
                "explanation": explanation,
                "records": records,
            }

            if ftype not in tier_nodes:
                tier_nodes[ftype] = {
                    "id": f"{eid}-{ftype}",
                    "label": ftype.replace("_", " ").title(),
                    "type": "tier",
                    "finding_type": ftype,
                    "count": 0,
                    "weight_sum": 0,
                    "children": {},
                }

            if rule_id not in tier_nodes[ftype]["children"]:
                tier_nodes[ftype]["children"][rule_id] = {
                    "id": f"{eid}-{rule_id}",
                    "label": f"{rule_id}",
                    "type": "rule",
                    "rule_id": rule_id,
                    "count": 0,
                    "weight_sum": 0,
                    "children": [],
                }

            tier_nodes[ftype]["count"] += 1
            tier_nodes[ftype]["weight_sum"] += weight
            tier_nodes[ftype]["children"][rule_id]["count"] += 1
            tier_nodes[ftype]["children"][rule_id]["weight_sum"] += weight
            tier_nodes[ftype]["children"][rule_id]["children"].append(instance_node)

        tier_list = []
        for ftype, tnode in tier_nodes.items():
            rule_list = list(tnode["children"].values())
            tnode["children"] = rule_list
            tier_list.append(tnode)

        entity_node = {
            "id": eid,
            "label": f"{eid} · {entity['entity_name']} (score {entity['risk_score']:.2f})",
            "type": "entity",
            "entity_id": eid,
            "entity_name": entity["entity_name"],
            "sector": entity["sector"],
            "risk_score": entity["risk_score"],
            "finding_count": entity["finding_count"],
            "children": tier_list,
        }
        tree.append(entity_node)

    return tree
