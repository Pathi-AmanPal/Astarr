/** Screen 1 — the ranking.
 *
 *  Forty entities, one score each, and the supervisor's question is "who first?".
 *  That makes this a comparison screen before it is a list, so every row carries
 *  the same three things in the same place: a figure that aligns on its digits, a
 *  bar drawn against the attainable maximum rather than against the row above it,
 *  and a written band. Colour reinforces the band; it never carries it alone.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, EntitySummary, getEntities } from "../api";
import Composition, { CompositionLegend } from "../components/Composition";
import { useDataset } from "../components/Shell";
import { Loading, ErrorState } from "../components/States";
import { ATTAINABLE_MAX, entityRef, formatScore } from "../workpaper";

/* Band thresholds for the weighted-tier scale (PRD Section 5 amendment).
   These were 60 and 30 on the Phase 1 additive scale. They are NOT a rescale: the
   old score conflated tiers, so 40 earned from Negative Space and 40 earned from
   Execution Gap looked identical, and weighting now separates them. 50/10 is the
   pair that preserves the previous three-band grouping exactly, so no entity
   silently changes band as a side effect of the formula change.

   Banding is a supervisory judgement, not arithmetic. */
const BAND_EXCEPTION = 50;
const BAND_CAUTION = 10;

function band(score: number): { key: string; label: string } {
  if (score > BAND_EXCEPTION) return { key: "exception", label: "exception" };
  if (score >= BAND_CAUTION) return { key: "caution", label: "caution" };
  return { key: "clear", label: "clear" };
}

export default function EntityList() {
  const navigate = useNavigate();
  const { version, openPicker } = useDataset();
  const [entities, setEntities] = useState<EntitySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setEntities(await getEntities());
    } catch (e) {
      setEntities(null);
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    }
  }, []);

  // `version` bumps when the shell loads a new dataset, from any screen.
  useEffect(() => {
    void load();
  }, [load, version]);

  const total = entities?.length ?? 0;
  const alerts = entities?.reduce((n, e) => n + e.record_count, 0) ?? 0;
  const findings = entities?.reduce((n, e) => n + e.finding_count, 0) ?? 0;
  const flagged = entities?.filter((e) => e.finding_count > 0).length ?? 0;
  const sectors = new Set(entities?.map((e) => e.sector)).size;
  const top = entities?.[0]?.risk_score ?? 0;

  return (
    <>
      <div className="head">
        <div>
          <h1 className="hd">Supervisory ranking</h1>
          <p className="hd__sub">
            Every entity in the loaded dataset, ordered by supervisory risk. The
            score is a comparable scale, not a percentage — follow any row to the
            findings that produce its figure, and from there to the alert records
            those findings were computed from.
          </p>
        </div>
      </div>

      {entities && entities.length > 0 && (
        <section className="stats" aria-label="Dataset summary">
          <div className="stat">
            <span className="lbl">Entities under review</span>
            <span className="stat__value">{total}</span>
            <span className="stat__sub">
              across <b>{sectors}</b> {sectors === 1 ? "sector" : "sectors"} ·{" "}
              <b>{total - flagged}</b> with no findings
            </span>
          </div>
          <div className="stat">
            <span className="lbl">Alerts analysed</span>
            <span className="stat__value">{alerts.toLocaleString()}</span>
            <span className="stat__sub">
              <b>{total ? Math.round(alerts / total).toLocaleString() : 0}</b> per
              entity on average
            </span>
          </div>
          <div className="stat">
            <span className="lbl">Findings raised</span>
            <span className="stat__value">{findings.toLocaleString()}</span>
            <span className="stat__sub">
              on <b>{flagged}</b> of {total} entities
            </span>
          </div>
          <div className="stat">
            <span className="lbl">Highest score</span>
            <span className="stat__value">{formatScore(top)}</span>
            <span className="stat__sub">
              of <b>{ATTAINABLE_MAX}</b> attainable
            </span>
          </div>
        </section>
      )}

      <div className="sect">
        <h2 className="sect__title">Entities requiring supervisory attention</h2>
        {entities && <span className="sect__n">{total} rows</span>}
      </div>

      {!entities && !error && <Loading rows={8} label="Loading the ranking" />}

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      {entities && entities.length === 0 && (
        <div className="empty-screen">
          <h2 className="empty-screen__title">No dataset loaded</h2>
          <p className="empty-screen__body">
            This tool ships with no data of its own. Load a SOC alert export — CSV
            or JSON — and it will validate every row, run the eight supervisory
            rules across the entities it finds, and rank them. Your export does not
            need this tool's column names; common spellings are recognised and the
            translation is reported back to you.
          </p>
          <div className="empty-screen__actions">
            <button type="button" className="btn btn--primary" onClick={openPicker}>
              Load alert export
            </button>
          </div>
        </div>
      )}

      {entities && entities.length > 0 && (
        <>
          <div className="sheet">
            <table className="rank">
              <caption className="sr-only">
                Entities ranked by supervisory risk score, highest first. Each row
                gives the alert count, finding count, the score's composition by
                tier, and the score with its supervisory band.
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="c-rank">#</th>
                  <th scope="col">Entity</th>
                  <th scope="col" className="c-n n">Alerts</th>
                  <th scope="col" className="c-n n">Findings</th>
                  <th scope="col" className="c-comp">Composition</th>
                  <th scope="col" className="c-score n">Risk score</th>
                </tr>
              </thead>
              <tbody>
                {entities.map((e, i) => {
                  const b = band(e.risk_score);
                  return (
                    <tr
                      key={e.entity_id}
                      style={{ "--i": Math.min(i, 8) } as React.CSSProperties}
                      onClick={() => navigate(`/entities/${e.entity_id}`)}
                    >
                      <td className="c-rank">
                        <span className="rank__n">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                      </td>
                      <td>
                        <a
                          className="ent__name"
                          href={`/entities/${e.entity_id}`}
                          onClick={(ev) => {
                            ev.preventDefault();
                            ev.stopPropagation();
                            navigate(`/entities/${e.entity_id}`);
                          }}
                        >
                          {e.entity_name}
                        </a>
                        <span className="ent__meta">
                          <span className="mono">{e.entity_id}</span>
                          <i aria-hidden="true">·</i>
                          {e.sector}
                          <i aria-hidden="true">·</i>
                          <span className="mono">{entityRef(e.entity_id)}</span>
                        </span>
                      </td>
                      <td className="c-n">
                        <span className="num">
                          {e.record_count.toLocaleString()}
                        </span>
                      </td>
                      <td className="c-n">
                        {e.finding_count === 0 ? (
                          <span className="none">none</span>
                        ) : (
                          <span className="num">{e.finding_count}</span>
                        )}
                      </td>
                      <td className="c-comp">
                        <Composition tiers={e.tiers} />
                      </td>
                      <td className="c-score">
                        <span
                          className={`score${e.risk_score === 0 ? " score--zero" : ""}`}
                        >
                          {formatScore(e.risk_score)}
                        </span>
                        {/* NOT "maximum": under weighted tiers a capped tier does
                            not mean a maximum score. An entity can cap its
                            Execution Gap tier and still score 56.50. */}
                        {/* The denominator stays on every row. A capped tier
                            does NOT mean a maximum score — an entity can cap its
                            execution-gap tier and still score 56.50 — so the cap
                            is noted beside the scale, never in place of it. */}
                        <span className="score__of">
                          of {ATTAINABLE_MAX}
                          {e.capped && " · capped"}
                        </span>
                        <span className={`chip chip--${b.key}`}>{b.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <CompositionLegend note="Bars are drawn to the same scale on every row." />
        </>
      )}
    </>
  );
}
