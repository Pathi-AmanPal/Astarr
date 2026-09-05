/** Screen 1 — the schedule. Entities ranked by risk, footed like an audit column.
    The leftmost column is the working-paper reference: this sheet is an index,
    and every row points at the schedule that proves its figure. */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, EntitySummary, getEntities, resetDemo, uploadDataset } from "../api";
import { Loading, ErrorState } from "../components/States";
import { WORKPAPER_ID, entityRef, formatScore } from "../workpaper";

/** Severity edge mark. The field stays achromatic; only this edge carries colour. */
/* Band thresholds for the weighted-tier scale (PRD Section 5 amendment).
   These were 60 and 30 on the Phase 1 additive 0-100 scale. They are NOT a naive
   rescale: the old score conflated tiers, so a 40 earned from Negative Space and a 40
   earned from Execution Gap looked identical, and weighting now separates them. 50/10
   is the pair that preserves the existing three-band grouping exactly -- CSE-01 alone
   in exception, CSE-05/CSE-03/CSE-02 in caution, CSE-06 and the zero-scoring entities
   clear -- so no entity silently changes colour as a side effect of the formula change.

   Chosen to preserve intent rather than derived from first principles: banding is a
   supervisory judgement, not arithmetic, and is worth a deliberate review. Note the
   attainable maximum is 86.5, not 100 (the ML tier cannot exceed 10). */
const BAND_EXCEPTION = 50;
const BAND_CAUTION = 10;

function edgeClass(score: number): string {
  if (score > BAND_EXCEPTION) return "edge-exception";
  if (score >= BAND_CAUTION) return "edge-caution";
  return "edge-clear";
}

export default function EntityList() {
  const navigate = useNavigate();
  const [entities, setEntities] = useState<EntitySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setEntities(await getEntities());
    } catch (e) {
      setEntities(null);
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onReset() {
    setResetting(true);
    setResetError(null);
    try {
      await resetDemo();
      await load();
    } catch (e) {
      // The page stays usable: the old list remains on screen behind the banner.
      setResetError(e instanceof ApiError ? e.message : "Reset failed.");
    } finally {
      setResetting(false);
    }
  }

  async function onFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setResetting(true);
    setResetError(null);
    try {
      await uploadDataset(file);
      await load();
    } catch (err) {
      setResetError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setResetting(false);
      e.target.value = "";
    }
  }

  const totalAlerts = entities?.reduce((n, e) => n + e.record_count, 0) ?? 0;
  const totalFindings = entities?.reduce((n, e) => n + e.finding_count, 0) ?? 0;

  return (
    <>
      <div className="masthead">
        <div>
          <h1 className="masthead__title">SAT-SA — Supervisory Analytics</h1>
          <p className="masthead__sub">
            Supervisory Analytics Tool for SOC Assessment
          </p>
          <p className="masthead__ref">
            <span>Working Paper {WORKPAPER_ID}</span>
            <span>Custom / Synthetic Dataset</span>
            <span>Prepared for NCIIPC Supervisory Review</span>
          </p>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <label className="btn" style={{ cursor: "pointer" }}>
            {resetting ? "Processing…" : "Upload CSV / JSON"}
            <input
              type="file"
              accept=".csv,.json"
              style={{ display: "none" }}
              onChange={onFileUpload}
              disabled={resetting}
            />
          </label>
          <button
            type="button"
            className="btn"
            onClick={onReset}
            disabled={resetting}
          >
            {resetting ? "Resetting…" : "Reset Demo Data"}
          </button>
        </div>
      </div>

      {entities && (
        <dl className="summary">
          <div className="summary__cell">
            <dt className="summary__label">Entities</dt>
            <dd className="summary__n">{entities.length}</dd>
          </div>
          <div className="summary__cell">
            <dt className="summary__label">Alerts analysed</dt>
            <dd className="summary__n">{totalAlerts}</dd>
          </div>
          <div className="summary__cell">
            <dt className="summary__label">Findings raised</dt>
            <dd className="summary__n">{totalFindings}</dd>
          </div>
        </dl>
      )}

      {resetError && (
        <div className="banner" role="alert">
          <span>{resetError}</span>
          <button type="button" className="btn" onClick={onReset} disabled={resetting}>
            Retry
          </button>
        </div>
      )}

      <h2 className="section-title">Entities Requiring Supervisory Attention</h2>
      <p className="section-note">
        Ranked by supervisory risk score, highest first. Every score is the sum of the
        findings on that entity’s schedule — follow its reference to see them.
      </p>

      {!entities && !error && <Loading rows={8} label="Loading entities" />}

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      {entities && (
        <div className="sheet">
          <table className="schedule">
            <thead>
              <tr>
                <th className="col-ref" scope="col">W/P</th>
                <th className="col-rank" scope="col">Rank</th>
                <th className="col-entity" scope="col">Entity</th>
                <th className="col-alerts" scope="col">Alerts</th>
                <th className="col-findings" scope="col">Findings</th>
                <th className="col-score" scope="col">Risk score</th>
              </tr>
            </thead>
            <tbody>
              {entities.map((e, i) => (
                <tr
                  key={e.entity_id}
                  onClick={() => navigate(`/entities/${e.entity_id}`)}
                >
                  <td className="col-ref">
                    <span className="cell wp-ref">{entityRef(e.entity_id)}</span>
                  </td>
                  <td className="col-rank">
                    <span className="cell num rank">{i + 1}</span>
                  </td>
                  <td>
                    <span className="cell">
                      <span className="tickmark" aria-hidden="true" />
                      <a
                        className="entity-name"
                        href={`/entities/${e.entity_id}`}
                        onClick={(ev) => {
                          ev.preventDefault();
                          ev.stopPropagation();
                          navigate(`/entities/${e.entity_id}`);
                        }}
                      >
                        {e.entity_name}
                      </a>
                      <span className="entity-id">{e.entity_id}</span>
                      <span className="entity-sector">{e.sector}</span>
                    </span>
                  </td>
                  <td className="col-alerts">
                    <span className="cell num">{e.record_count}</span>
                  </td>
                  <td className="col-findings">
                    <span className="cell num">
                      {e.finding_count === 0 ? (
                        <>
                          <span className="tick-clean" aria-hidden="true" />
                          <span className="sr-only">No findings — clean</span>
                        </>
                      ) : (
                        e.finding_count
                      )}
                    </span>
                  </td>
                  <td className="col-score">
                    <span className={`score-cell ${edgeClass(e.risk_score)}`}>
                      <span className="score-value">{formatScore(e.risk_score)}</span>
                      {/* NOT "Maximum": under weighted tiers a capped tier does not
                          mean a maximum score. CSE-01 caps its Execution Gap tier at
                          100 and still scores 56.50, and labelling that "Maximum" on
                          the ranking screen would be plainly false. */}
                      {e.capped && <span className="score-max">Tier capped</span>}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
