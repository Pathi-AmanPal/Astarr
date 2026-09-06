/** Screen 2 — one entity's schedule, and the arithmetic behind its score.
 *
 *  The readout on the left is the claim; the findings on the right are the
 *  evidence for it. Under weighted tiers the finding weights no longer sum to the
 *  headline figure, so the readout carries the step in between — each tier's raw
 *  sum, its individual cap, its weight, and the product — and the products foot
 *  to the total. A supervisory score a reader cannot foot is a score they have to
 *  take on trust, which is the opposite of what this tool is for.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Link } from "react-router-dom";

import {
  ApiError,
  EntityDetail as Detail,
  Finding,
  MlProfile,
  TierScore,
  getEntity,
  getMlProfile,
} from "../api";
import Composition, { CompositionLegend } from "../components/Composition";
import Crumbs from "../components/Crumbs";
import { useDataset } from "../components/Shell";
import { Loading, ErrorState, NotFound, Empty } from "../components/States";
import {
  ATTAINABLE_MAX,
  TIER_LABEL,
  entityRef,
  findingRef,
  formatScore,
} from "../workpaper";

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

function TierCalc({ tiers, total }: { tiers: TierScore[]; total: number }) {
  return (
    <table className="calc">
      <caption className="sr-only">
        Weighted-tier score calculation. Each tier is capped at 100 individually,
        then multiplied by its weight; the products are summed.
      </caption>
      <tbody>
        {tiers.map((t) => (
          <tr
            key={t.tier}
            className={t.raw === 0 ? "calc__row is-empty" : "calc__row"}
          >
            <th scope="row" className="calc__name">
              {TIER_LABEL[t.tier] ?? t.tier}
            </th>
            <td className="calc__raw">
              {t.capped ? (
                <>
                  <s>{t.raw}</s>
                  <span className="sr-only"> capped to </span>
                  <span className="calc__arrow" aria-hidden="true">→</span>
                  <span className="calc__cap">{t.capped_value}</span>
                </>
              ) : (
                t.raw
              )}
            </td>
            <td className="calc__op">×</td>
            <td className="calc__weight">{t.weight.toFixed(2)}</td>
            <td className="calc__eq">=</td>
            <td className="calc__contrib">{formatScore(t.contribution)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" className="calc__name">
            Supervisory risk score
          </th>
          <td colSpan={4} />
          <td className="calc__total">{formatScore(total)}</td>
        </tr>
      </tfoot>
    </table>
  );
}

function FindingRow({ group, entityId }: { group: RuleGroup; entityId: string }) {
  const [open, setOpen] = useState(false);
  const bodyId = `rule-${group.rule_id}`;

  return (
    <section className={`finding${open ? " finding--open" : ""}`}>
      <button
        type="button"
        className="finding__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={bodyId}
      >
        <span className="tag">{group.rule_id}</span>
        <span className="finding__title">{group.title}</span>
        {group.instances.length > 1 && (
          <span className="finding__count">×{group.instances.length}</span>
        )}
        <span className="finding__weight">{group.weight} pts</span>
        <span className="finding__chev" aria-hidden="true" />
      </button>

      <div className="finding__body" id={bodyId}>
        <div className="finding__inner">
          {group.instances.map((f) => (
            <article className="inst" key={f.finding_id}>
              <p className="inst__text">{f.explanation}</p>
              <div className="inst__foot">
                <span className="inst__ref">
                  {findingRef(entityId, f.rule_id)} · {f.finding_id} · {f.weight} pts
                </span>
                <Link className="btn--link" to={`/findings/${f.finding_id}`}>
                  View evidence →
                </Link>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

/** The corroboration layer's working, made readable.
 *
 *  ML-001's explanation names its top two drivers in a sentence. That justifies
 *  the finding but cannot be interrogated: the supervisor's next question is
 *  "compared with what?", and prose cannot answer it. This puts the whole feature
 *  vector on the page — each figure against the peer mean it was judged against,
 *  and how far from it in population sigmas.
 *
 *  It renders for entities the model did NOT flag too. "The model considered this
 *  entity normal" is a supervisory statement, and it is worth something only if
 *  the figures behind it are visible.
 */
function MlPanel({ profile }: { profile: MlProfile }) {
  if (!profile.available) {
    return (
      <p className="ml__none">
        The corroboration layer did not run for this dataset — it needs at least
        two entities to have a peer group to compare against.
      </p>
    );
  }

  // Scaled off the largest deviation on this entity, with a 1.5σ floor so a set
  // of small, unremarkable deviations is not magnified into drama.
  const scale = Math.max(1.5, ...profile.features.map((f) => Math.abs(f.deviation)));

  const drivers = new Set(
    [...profile.features]
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
      .slice(0, 2)
      .map((f) => f.feature),
  );

  return (
    <div className="ml">
      <p className="ml__caption">
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

      <div className="sheet sheet--scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Feature</th>
              <th scope="col" className="n">This entity</th>
              <th scope="col" className="n">Peer mean</th>
              <th scope="col" className="n">Deviation</th>
              {/* Without this column the driver marks look arbitrary: a feature
                  can be marked at +0.82σ while an unmarked one sits at +0.72σ,
                  because the ranking is by attribution, not by raw deviation. */}
              <th scope="col" className="n">
                {profile.method === "shap" ? "SHAP" : "Weight"}
              </th>
              <th scope="col" className="ml__plot">
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
                  <th scope="row" className="ml__label">
                    {f.label}
                  </th>
                  <td className="n num">{fmt(f.value)}</td>
                  <td className="n num ml__mean">{fmt(f.dataset_mean)}</td>
                  <td className="n num">
                    {f.deviation >= 0 ? "+" : "−"}
                    {fmt(Math.abs(f.deviation))}σ
                  </td>
                  <td className={`n num${driver ? "" : " ml__mean"}`}>
                    {fmt(Math.abs(f.contribution))}
                  </td>
                  <td className="ml__plot">
                    <span className="dev" aria-hidden="true">
                      <span className="dev__axis" />
                      <span
                        className={`dev__bar ${
                          f.deviation >= 0 ? "dev__bar--pos" : "dev__bar--neg"
                        }`}
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

/** Two decimals, trailing zeros trimmed — the backend formats its prose the same. */
function fmt(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, "") || "0";
}

function Section({
  title,
  groups,
  entityId,
}: {
  title: string;
  groups: RuleGroup[];
  entityId: string;
}) {
  const instances = groups.reduce((n, g) => n + g.instances.length, 0);
  return (
    <>
      <div className="sect">
        <h2 className="sect__title">{title}</h2>
        <span className="sect__n">
          {instances === 0
            ? "none"
            : `${instances} ${instances === 1 ? "finding" : "findings"}`}
        </span>
      </div>
      {groups.length === 0 ? (
        <Empty>Nothing in this entity's alert history met a rule of this type.</Empty>
      ) : (
        <div className="findings">
          {groups.map((g) => (
            <FindingRow group={g} entityId={entityId} key={g.rule_id} />
          ))}
        </div>
      )}
    </>
  );
}

export default function EntityDetailPage() {
  const { id = "" } = useParams();
  const { version } = useDataset();
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
    // Supporting detail. If it fails, the findings and the footed total still
    // render and the panel simply does not appear — the correct degradation for
    // a layer the product itself calls subordinate.
    try {
      setMl(await getMlProfile(id));
    } catch {
      setMl(null);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load, version]);

  if (error?.status === 404) {
    return (
      <>
        <Crumbs trail={[{ label: "Ranking", to: "/" }, { label: "Not found" }]} />
        <NotFound message="No such entity" />
      </>
    );
  }

  if (error) {
    return (
      <>
        <Crumbs trail={[{ label: "Ranking", to: "/" }, { label: "Entity" }]} />
        <ErrorState message={error.message} onRetry={() => void load()} backTo />
      </>
    );
  }

  if (!entity) {
    return (
      <>
        <Crumbs trail={[{ label: "Ranking", to: "/" }, { label: "Entity" }]} />
        <Loading rows={5} label="Loading entity" />
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
      <Crumbs
        trail={[{ label: "Ranking", to: "/" }, { label: entity.entity_name }]}
      />

      <div className="head">
        <div>
          <h1 className="hd">{entity.entity_name}</h1>
          <p className="head__meta">
            <span className="tag tag--ref">{entityRef(entity.entity_id)}</span>
            <span className="tag">{entity.entity_id}</span>
            {entity.sector}
          </p>
        </div>
      </div>

      <div className="detail">
        {/* First in the DOM so a narrow screen reads the score before the
            findings; grid places it left on desktop. */}
        <aside className="readout">
          <span className="lbl">Supervisory risk score</span>
          <div className="readout__value">
            <span>{formatScore(entity.risk_score)}</span>
            <span className="readout__of">of {ATTAINABLE_MAX} attainable</span>
          </div>

          {entity.findings.length > 0 && (
            <>
              <Composition tiers={entity.tiers} large />
              <CompositionLegend />
              <TierCalc tiers={entity.tiers} total={entity.risk_score} />
            </>
          )}

          <p className="readout__note">
            {entity.capped ? (
              <>
                Weighted across three tiers. The{" "}
                {entity.tiers
                  .filter((t) => t.capped)
                  .map((t) => TIER_LABEL[t.tier] ?? t.tier)
                  .join(" and ")}{" "}
                tier reached its individual 100-point cap before weighting, so its
                raw total of{" "}
                {entity.tiers.filter((t) => t.capped).map((t) => t.raw).join(" and ")}{" "}
                is shown struck above. Not an error — every contributing weight is
                listed alongside, and the raw total across all findings is{" "}
                {entity.risk_score_raw}.
              </>
            ) : entity.findings.length === 0 ? (
              <>
                No findings recorded. Nothing in this entity's alert history met the
                threshold for any supervisory rule — which is a result, not a gap in
                the analysis.
              </>
            ) : (
              <>
                Footed from {entity.findings.length}{" "}
                {entity.findings.length === 1 ? "finding" : "findings"} listed
                alongside, weighted across three tiers. The score is a comparable
                ranking scale, not a percentage.
              </>
            )}
          </p>
        </aside>

        <div>
          <Section
            title="Execution gap"
            groups={gaps}
            entityId={entity.entity_id}
          />
          <Section
            title="Negative space"
            groups={spaces}
            entityId={entity.entity_id}
          />

          {/* The subordinate block stays subordinate whether or not a finding was
              raised: below both detection sections, behind a rule. What changed in
              v2 is that the layer can be read rather than only believed. */}
          {(corroboration.length > 0 || ml) && (
            <div className="sub">
              {corroboration.length > 0 ? (
                <Section
                  title="ML corroboration"
                  groups={corroboration}
                  entityId={entity.entity_id}
                />
              ) : (
                <div className="sect">
                  <h2 className="sect__title">ML corroboration</h2>
                  <span className="sect__n">no finding raised</span>
                </div>
              )}

              {ml && <MlPanel profile={ml} />}

              <p className="sub__note">
                Supporting signal only. An unsupervised Isolation Forest is
                evaluated solely for entities the deterministic rules already
                flagged, so it can never raise a finding on its own, and it carries
                the smallest weight in the system.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
