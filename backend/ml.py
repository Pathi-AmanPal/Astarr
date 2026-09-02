"""ML corroboration layer — ML-001 (scope amendment 2026-09-02).

PRD Section 9 originally deferred all ML to Phase 2. Isolation Forest and SHAP are
pulled forward by explicit instruction, as a CORROBORATING signal only.

Two properties matter more than the model itself:

1. **It can never originate a finding.** Corroboration is evaluated only for entities
   that already carry an Execution Gap or Negative Space finding from the deterministic
   engine. An entity the model considers anomalous but the rules found clean gets
   nothing. Rules and statistics stay primary; this is the small secondary signal.

2. **It is deterministic.** `random_state=42` is mandatory, not stylistic — PRD
   Section 10 step 5 requires repeated resets to produce identical findings and scores,
   and an unseeded forest would break that on stage.

Honest limitation, stated rather than hidden: the peer group is small, so this is a
weak statistical signal by construction. That is precisely why it carries the lowest
weight in the system and cannot fire alone.
"""

from __future__ import annotations

import warnings

ML_RULE_ID = "ML-001"
ML_FINDING_TYPE = "ML_CORROBORATION"
ML_WEIGHT = 10
ML_TITLE = "Statistically unusual profile (ML corroboration)"

RANDOM_STATE = 42
N_ESTIMATORS = 100

FEATURES = [
    ("alert_count", "alert volume"),
    ("avg_closure_time_minutes", "average closure time"),
    ("escalation_rate", "escalation rate"),
    ("pct_high_critical", "share of high/critical alerts"),
]


def build_features(con) -> tuple[list[str], list[list[float]]]:
    """One aggregate feature vector per entity, ordered by entity_id.

    Computed in SQL from the same records the rules read, so the model sees exactly
    the dataset the deterministic engine saw.
    """
    rows = con.execute(
        """
        SELECT e.entity_id,
               COUNT(r.record_id)                                   AS alert_count,
               COALESCE(AVG(r.closure_time_minutes), 0.0)           AS avg_closure,
               COALESCE(AVG(CASE WHEN r.escalated THEN 1.0 ELSE 0.0 END), 0.0) AS esc_rate,
               COALESCE(AVG(CASE WHEN r.severity IN ('HIGH', 'CRITICAL')
                                 THEN 1.0 ELSE 0.0 END), 0.0)       AS pct_hc
        FROM entities e
        LEFT JOIN records r ON r.entity_id = e.entity_id
        GROUP BY e.entity_id
        ORDER BY e.entity_id
        """
    ).fetchall()

    entity_ids = [r[0] for r in rows]
    matrix = [[float(r[1]), float(r[2]), float(r[3]), float(r[4])] for r in rows]
    return entity_ids, matrix


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pstdev(values: list[float]) -> float:
    if not values:
        return 0.0
    mu = _mean(values)
    return (sum((v - mu) ** 2 for v in values) / len(values)) ** 0.5


def _zscores(matrix: list[list[float]], row: int) -> list[float]:
    """Per-feature deviation from the dataset mean, in population sigmas."""
    out = []
    for col in range(len(FEATURES)):
        column = [r[col] for r in matrix]
        sd = _pstdev(column)
        out.append(0.0 if sd == 0 else (matrix[row][col] - _mean(column)) / sd)
    return out


def _attributions(model, matrix: list[list[float]]) -> tuple[list[list[float]], str]:
    """Per-feature contributions from SHAP, falling back to z-scores.

    The fallback is not a lesser explanation: a feature's deviation from the dataset
    mean is exactly the kind of auditable reasoning NS-001 already gives a supervisor.
    """
    try:
        import numpy as np
        import shap

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            explainer = shap.TreeExplainer(model)
            values = np.asarray(explainer.shap_values(np.asarray(matrix, dtype=float)))
        if values.shape == (len(matrix), len(FEATURES)):
            return values.tolist(), "shap"
    except Exception:
        # SHAP support for IsolationForest can be version-dependent; never let an
        # explainability nicety take down the detection pipeline.
        pass

    return [_zscores(matrix, i) for i in range(len(matrix))], "zscore"


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _phrase(feature_index: int, entity_value: float, dataset_mean: float) -> str:
    _key, label = FEATURES[feature_index]
    direction = "above" if entity_value > dataset_mean else "below"
    return f"{label} ({_fmt(entity_value)} vs a dataset average of {_fmt(dataset_mean)}, {direction} average)"


def ml_corroboration(con, flagged_entity_ids: set[str]) -> list[dict]:
    """ML-001 findings, only for entities the deterministic engine already flagged.

    `flagged_entity_ids` is the gate: it carries the entities that already have an
    EG or NS finding. An empty set produces no findings at all.
    """
    entity_ids, matrix = build_features(con)
    if len(matrix) < 2:
        return []

    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        # The layer is corroboration only; its absence must never break detection.
        return []

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = IsolationForest(
            n_estimators=N_ESTIMATORS,
            contamination="auto",
            random_state=RANDOM_STATE,
        ).fit(matrix)
        predictions = model.predict(matrix)

    contributions, method = _attributions(model, matrix)
    means = [_mean([r[c] for r in matrix]) for c in range(len(FEATURES))]

    out: list[dict] = []
    for i, entity_id in enumerate(entity_ids):
        if predictions[i] != -1:
            continue
        if entity_id not in flagged_entity_ids:
            # The model finds this entity unusual, but no rule or statistic did.
            # Corroboration only: it never speaks first.
            continue

        ranked = sorted(
            range(len(FEATURES)),
            key=lambda c: (-abs(contributions[i][c]), c),
        )[:2]
        drivers = " and ".join(
            _phrase(c, matrix[i][c], means[c]) for c in ranked
        )
        basis = (
            "SHAP feature attribution"
            if method == "shap"
            else "per-feature deviation from the dataset mean"
        )

        ids = sorted(
            r[0] for r in con.execute(
                "SELECT record_id FROM records WHERE entity_id = ?", [entity_id]
            ).fetchall()
        )

        out.append({
            "entity_id": entity_id,
            "rule_id": ML_RULE_ID,
            "finding_type": ML_FINDING_TYPE,
            "title": ML_TITLE,
            "explanation": (
                f"An unsupervised Isolation Forest reading all {len(entity_ids)} entities "
                f"places this one outside the normal profile, driven by {drivers} "
                f"({basis}). This corroborates the rule-based findings already raised for "
                f"this entity - it does not raise a finding of its own, and never fires "
                f"where the deterministic rules found nothing."
            ),
            "evidence_record_ids": ids,
        })
    return out
