/** Screen 2 — the footed total and its grouped breakdown.
    Findings group by rule_id: one card per rule, count and summed weight visible,
    expanding to the individual instances that each keep their own evidence link.
    Every contributing weight stays on screen, which is what PRD Section 5 requires. */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ApiError,
  EntityDetail as Detail,
  Finding,
  MlProfile,
  TierScore,
  getEntity,
  getMlProfile,
} from "../api";
import { Loading, ErrorState, NotFound, Empty } from "../components/States";
import { TIER_LABEL, entityRef, findingRef, formatScore } from "../workpaper";

interface RuleGroup {
  rule_id: string;
  title: string;
  weight: number;
  instances: Finding[];
}

function groupByRule(findings: Finding[]): RuleGroup[] {
  const order: string[] = [];
  const groups = new Map<string, RuleGroup>();

  for (const f of findings) {
    let g = groups.get(f.rule_id);
    if (!g) {
      g = { rule_id: f.rule_id, title: f.title, weight: 0, instances: [] };
      groups.set(f.rule_id, g);
      order.push(f.rule_id);
    }
    g.weight += f.weight;
    g.instances.push(f);
  }
  return order.map((id) => groups.get(id)!);
}

/** The score's arithmetic, shown so a reader can foot it themselves.

    PRD Section 5 requires the score to appear as a visible breakdown rather than a
    bare number. Under the additive formula that was satisfied by listing the finding
    weights, because they summed to the score. Weighted tiers break that: the weights
    below no longer add up to the number in the hero. These rows carry the missing
    arithmetic -- each tier's raw sum, its individual cap, its weight, and the product
    -- and the products foot to the total. */
function TierCalc({ tiers, total }: { tiers: TierScore[]; total: number }) {
  return (
    <table className="tier-calc">
      <caption className="sr-only">
        Weighted-tier score calculation. Each tier is capped at 100 individually, then
        multiplied by its weight; the products are summed.
      </caption>
      <tbody>
        {tiers.map((t) => (
          <tr key={t.tier} className={t.raw === 0 ? "tier-calc__row is-empty" : "tier-calc__row"}>
            <th scope="row" className="tier-calc__name">{TIER_LABEL[t.tier] ?? t.tier}</th>
            <td className="tier-calc__raw">
              {t.capped ? (
                <>
                  <s>{t.raw}</s>
                  <span className="sr-only"> capped to </span>
                  <span className="tier-calc__cap"> {t.capped_value}</span>
                </>
              ) : (
                t.raw
              )}
            </td>
            <td className="tier-calc__op">×</td>
            <td className="tier-calc__weight">{t.weight.toFixed(2)}</td>
            <td className="tier-calc__eq">=</td>
            <td className="tier-calc__contrib">{formatScore(t.contribution)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" className="tier-calc__name">Supervisory risk score</th>
          <td colSpan={4} />
          <td className="tier-calc__total">{formatScore(total)}</td>
        </tr>
      </tfoot>
    </table>
  );
}

function RuleCard({ group, entityId }: { group: RuleGroup; entityId: string }) {
  const [open, setOpen] = useState(false);
  const bodyId = `rule-${group.rule_id}`;

  return (
    <section className={`rule-card${open ? " rule-card--open" : ""}`}>
      <button
        type="button"
        className="rule-card__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={bodyId}
      >
        <span className="rule-card__ref">{findingRef(entityId, group.rule_id)}</span>
        <span className="rule-card__rule">{group.rule_id}</span>
        <span className="rule-card__title">{group.title}</span>
        {group.instances.length > 1 && (
          <span className="rule-card__count">×{group.instances.length}</span>
        )}
        <span className="rule-card__weight">{group.weight} pts</span>
        <span className="chevron" aria-hidden="true" />
      </button>

      <div className="rule-card__body" id={bodyId}>
        <div className="rule-card__inner">
        {group.instances.map((f) => (
          <div className="instance" key={f.finding_id}>
            <p className="instance__text">
              <span className="instance__ref">
                {findingRef(entityId, f.rule_id)} · {f.finding_id} · {f.weight} pts
              </span>
              {f.explanation}
            </p>
            <Link className="btn btn--link instance__link" to={`/findings/${f.finding_id}`}>
              View Evidence
            </Link>
          </div>
        ))}
        </div>
      </div>
    </section>
  );
}

/** The corroboration layer's working, made readable.
 *
 *  ML-001's explanation names its top two drivers in a sentence. That justifies the
 *  finding but cannot be interrogated: a supervisor's next question is "compared with
 *  what?", and prose cannot answer it. This panel puts the whole feature vector on the
 *  page — each figure against the peer-group mean it was judged against, and how far
 *  from it in population sigmas.
 *
 *  It renders for entities the model did NOT flag too. "The model considered this
 *  entity normal" is a supervisory statement, and it is only worth anything if the
 *  figures behind it are visible.
 */
function MlPanel({ profile }: { profile: MlProfile }) {
  if (!profile.available) {
    return (
      <p className="ml-panel__none">
        The corroboration layer did not run for this dataset — it needs at least two
        entities to have a peer group to compare against.
      </p>
    );
  }

  // Scale the bars off the largest deviation on this entity, with a 1.5-sigma floor so
  // a set of small, unremarkable deviations does not get magnified into drama.
  const scale = Math.max(1.5, ...profile.features.map((f) => Math.abs(f.deviation)));

  // The two features the model leaned on hardest. Marked in exception ink because they
  // are the reason for the claim — the same red pen that circles a triggering value in
  // an evidence table, not a severity colour.
  const drivers = new Set(
    [...profile.features]
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
      .slice(0, 2)
      .map((f) => f.feature),
  );

  return (
    <div className="ml-panel">
      <p className="ml-panel__caption">
        Isolation Forest over {profile.peer_count} entities ·{" "}
        {profile.method === "shap"
          ? "SHAP feature attribution"
          : "per-feature deviation from the dataset mean"}{" "}
        ·{" "}
        {profile.anomalous
          ? "this entity sits outside the normal profile"
          : "this entity sits inside the normal profile"}
        {profile.anomalous && !profile.corroborated && (
          <> — but no deterministic rule fired, so no finding was raised</>
        )}
      </p>

      <div className="sheet">
        <table className="ml-table">
          <thead>
            <tr>
              <th scope="col">Feature</th>
              <th scope="col" className="ml-table__num">This entity</th>
              <th scope="col" className="ml-table__num">Peer mean</th>
              <th scope="col" className="ml-table__num">Deviation</th>
              {/* Without this column the driver marks look arbitrary: a feature can be
                  marked at +0.82σ while an unmarked one sits at +0.72σ, because the
                  ranking is by attribution, not by raw deviation. Showing the number
                  the ranking actually uses is what makes the mark legible. */}
              <th scope="col" className="ml-table__num">
                {profile.method === "shap" ? "SHAP" : "Weight"}
              </th>
              <th scope="col" className="ml-table__plot">
                <span className="sr-only">Deviation from the peer mean</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {profile.features.map((f) => {
              const driver = drivers.has(f.feature) && profile.anomalous;
              const width = `${(Math.abs(f.deviation) / scale) * 50}%`;
              return (
                <tr key={f.feature} className={driver ? "is-driver" : undefined}>
                  <th scope="row" className="ml-table__label">
                    {f.label}
                  </th>
                  <td className="ml-table__num num">{fmt(f.value)}</td>
                  <td className="ml-table__num num ml-table__mean">
                    {fmt(f.dataset_mean)}
                  </td>
                  <td className="ml-table__num num">
                    {f.deviation >= 0 ? "+" : "−"}
                    {fmt(Math.abs(f.deviation))}σ
                  </td>
                  <td
                    className={`ml-table__num num${driver ? "" : " ml-table__mean"}`}
                  >
                    {fmt(Math.abs(f.contribution))}
                  </td>
                  <td className="ml-table__plot">
                    {/* A plotted mark, not a filled cell: a centre rule for the peer
                        mean and a bar showing which side of it this entity falls. */}
                    <span className="dev" aria-hidden="true">
                      <span className="dev__axis" />
                      <span
                        className={`dev__bar ${f.deviation >= 0 ? "dev__bar--pos" : "dev__bar--neg"}`}
                        style={{ width }}
                      />
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Two decimals, trailing zeros trimmed — the backend formats its prose the same way. */
function fmt(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, "") || "0";
}

function Section({
  title,
  tab,
  groups,
  entityId,
}: {
  title: string;
  tab: string;
  groups: RuleGroup[];
  entityId: string;
}) {
  return (
    <>
      <h2 className="section-title section-title--tabbed">
        <span className="index-tab" aria-hidden="true">{tab}</span>
        {title}
      </h2>
      {groups.length === 0 ? (
        <div className="findings">
          <Empty>No findings of this type.</Empty>
        </div>
      ) : (
        <div className="findings">
          {groups.map((g) => (
            <RuleCard group={g} entityId={entityId} key={g.rule_id} />
          ))}
        </div>
      )}
    </>
  );
}

export default function EntityDetailPage() {
  const { id = "" } = useParams();
  const [entity, setEntity] = useState<Detail | null>(null);
  const [ml, setMl] = useState<MlProfile | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setEntity(await getEntity(id));
    } catch (e) {
      setEntity(null);
      setError(e instanceof ApiError ? e : new ApiError("Something went wrong.", 500));
      return;
    }
    // The corroboration profile is supporting detail. If it fails, the findings and
    // the footed total still render — the panel simply does not appear, which is the
    // correct degradation for a layer the product calls subordinate.
    try {
      setMl(await getMlProfile(id));
    } catch {
      setMl(null);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error?.status === 404) {
    return (
      <>
        <Link className="crumb" to="/">← All entities</Link>
        <NotFound message="Entity not found" />
      </>
    );
  }

  if (error) {
    return (
      <>
        <Link className="crumb" to="/">← All entities</Link>
        <ErrorState message={error.message} onRetry={() => void load()} backTo />
      </>
    );
  }

  if (!entity) {
    return (
      <>
        <Link className="crumb" to="/">← All entities</Link>
        <div style={{ marginTop: 18 }}>
          <Loading rows={4} label="Loading entity" />
        </div>
      </>
    );
  }

  const groups = groupByRule(entity.findings);
  const gaps = groups.filter((g) => g.rule_id.startsWith("EG"));
  const spaces = groups.filter((g) => g.rule_id.startsWith("NS"));
  // Corroboration sits below both, never between them: it supports the findings
  // above rather than standing as a peer category.
  const corroboration = groups.filter((g) => g.rule_id.startsWith("ML"));

  return (
    <>
      <Link className="crumb" to="/">← All entities</Link>

      <div className="detail-head">
        <div>
          <h1 className="detail-title">{entity.entity_name}</h1>
          <p className="detail-meta">
            <span className="wp-ref wp-ref--lead">{entityRef(entity.entity_id)}</span>
            <span className="entity-id">{entity.entity_id}</span> · {entity.sector}
          </p>
        </div>

      </div>

      {/* DESIGN.md: "a document body on the left and a score block on the right, so the
          total and its per-tier calculation sit beside the findings that produce them."
          The rail is first in the DOM so that on a narrow screen the score is read
          before the findings; grid places it right on desktop. */}
      <div className="detail-body">
        <aside className="detail-body__rail">
          <div className="total">
            <div className="total__label">Supervisory Risk Score</div>
          <div className="total__value">
            <span>{formatScore(entity.risk_score)}</span>
          </div>
          <div className="total__rule" />
          {entity.findings.length > 0 && (
            <TierCalc tiers={entity.tiers} total={entity.risk_score} />
          )}
          <p className="total__note">
            {entity.capped ? (
              <>
                Weighted across three tiers. The{" "}
                {entity.tiers
                  .filter((t) => t.capped)
                  .map((t) => TIER_LABEL[t.tier] ?? t.tier)
                  .join(" and ")}{" "}
                tier reached its individual 100-point cap before weighting, so its raw
                total of {entity.tiers.filter((t) => t.capped).map((t) => t.raw).join(" and ")}{" "}
                is shown struck above. Not an error — every contributing weight is listed
                below, and the raw total across all findings is {entity.risk_score_raw}.
              </>
            ) : entity.findings.length === 0 ? (
              <>
                No findings recorded — nothing in this entity’s alert history met the
                threshold for any supervisory rule.
              </>
            ) : (
              <>
                Footed from {entity.findings.length}{" "}
                {entity.findings.length === 1 ? "finding" : "findings"} listed below,
                weighted across three tiers. The score is a comparable ranking scale,
                not a percentage.
              </>
            )}
            </p>
          </div>
        </aside>

        <div className="detail-body__main">
          <Section
            title="Execution Gap Findings"
            tab="EG"
            groups={gaps}
            entityId={entity.entity_id}
          />
          <Section
            title="Negative Space Findings"
            tab="NS"
            groups={spaces}
            entityId={entity.entity_id}
          />
          {/* The subordinate block stays subordinate whether or not a finding was
              raised: below both detection sections, behind a rule, dashed tab, smaller
              heading. What changes is that the layer can now be read rather than only
              believed. */}
          {(corroboration.length > 0 || ml) && (
            <div className="subordinate">
              {corroboration.length > 0 ? (
                <Section
                  title="ML Corroboration"
                  tab="ML"
                  groups={corroboration}
                  entityId={entity.entity_id}
                />
              ) : (
                <h2 className="section-title section-title--tabbed">
                  <span className="index-tab" aria-hidden="true">ML</span>
                  ML Corroboration
                </h2>
              )}

              {ml && <MlPanel profile={ml} />}

              <p className="subordinate__note">
                Supporting signal only. An unsupervised Isolation Forest is evaluated
                solely for entities the deterministic rules already flagged, so it can
                never raise a finding on its own. It carries the smallest weight in the
                system.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
