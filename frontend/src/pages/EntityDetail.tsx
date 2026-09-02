/** Screen 2 — the footed total and its grouped breakdown.
    Findings group by rule_id: one card per rule, count and summed weight visible,
    expanding to the individual instances that each keep their own evidence link.
    Every contributing weight stays on screen, which is what PRD Section 5 requires. */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, EntityDetail as Detail, Finding, getEntity } from "../api";
import { Loading, ErrorState, NotFound, Empty } from "../components/States";
import { entityRef, findingRef } from "../workpaper";

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

        <div className="total">
          <div className="total__label">Supervisory Risk Score</div>
          <div className="total__value">
            {entity.capped && (
              <span className="total__struck">
                {entity.risk_score_raw}
                <span className="sr-only"> struck to </span>
              </span>
            )}
            <span>{entity.risk_score}</span>
            {entity.capped && <span className="total__max">· Maximum</span>}
          </div>
          <div className="total__rule" />
          <p className="total__note">
            {entity.capped ? (
              <>
                Raw total {entity.risk_score_raw} struck to the 100-point cap, which keeps
                the scale comparable across all entities. Not an error — every
                contributing weight is listed below.
              </>
            ) : entity.findings.length === 0 ? (
              <>
                No findings recorded — nothing in this entity’s alert history met the
                threshold for any supervisory rule.
              </>
            ) : (
              <>
                Footed from {entity.findings.length}{" "}
                {entity.findings.length === 1 ? "finding" : "findings"} listed below.
              </>
            )}
          </p>
        </div>
      </div>

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
            Supporting signal only. An unsupervised Isolation Forest is evaluated solely
            for entities the deterministic rules already flagged, so it can never raise a
            finding on its own. It carries the smallest weight in the system.
          </p>
        </div>
      )}
    </>
  );
}
