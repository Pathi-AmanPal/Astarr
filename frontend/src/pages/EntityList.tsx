/** Screen 1 — the schedule. Entities ranked by risk, footed like an audit column.
    The leftmost column is the working-paper reference: this sheet is an index,
    and every row points at the schedule that proves its figure. */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, EntitySummary, getEntities, resetDemo } from "../api";
import { Loading, ErrorState } from "../components/States";
import { WORKPAPER_ID, entityRef } from "../workpaper";

/** Severity edge mark. The field stays achromatic; only this edge carries colour. */
function edgeClass(score: number): string {
  if (score > 60) return "edge-exception";
  if (score >= 30) return "edge-caution";
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
            <span>Synthetic demo dataset</span>
            <span>Prepared for NCIIPC Supervisory Review</span>
          </p>
        </div>
        <button
          type="button"
          className="btn"
          onClick={onReset}
          disabled={resetting}
        >
          {resetting ? "Resetting…" : "Reset Demo Data"}
        </button>
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
                      <span className="score-value">{e.risk_score}</span>
                      {e.capped && <span className="score-max">Maximum</span>}
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
