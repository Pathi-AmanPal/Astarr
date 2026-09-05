/** Screen 2 — the footed total and its grouped breakdown.
    Findings group by rule_id: one card per rule, count and summed weight visible,
    expanding to the individual instances that each keep their own evidence link.
    Every contributing weight stays on screen, which is what PRD Section 5 requires. */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, EntityDetail as Detail, Finding, TierScore, getEntity } from "../api";
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
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setEntity(await getEntity(id));
    } catch (e) {
      setEntity(null);
      setError(e instanceof ApiError ? e : new ApiError("Something went wrong.", 500));
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
          {corroboration.length > 0 && (
            <div className="subordinate">
              <Section
                title="ML Corroboration"
                tab="ML"
                groups={corroboration}
                entityId={entity.entity_id}
              />
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
