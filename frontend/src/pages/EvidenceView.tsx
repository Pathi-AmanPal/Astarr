/** Screen 3 — the source records behind one finding, on its own route so that
    browser back serves PRD Section 10 step 4. The full record set renders at
    scale rather than paginating: for a Negative Space finding, the shortness of
    the table is the evidence. */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AlertRecord, ApiError, Evidence, getEvidence } from "../api";
import { Loading, ErrorState, NotFound } from "../components/States";
import { findingRef } from "../workpaper";

function timestamp(value: string | null): string {
  if (!value) return "—";
  return value.replace("T", " ").slice(0, 16);
}

function minutes(value: number | null): string {
  return value === null ? "—" : String(value);
}

/** Flags the fields a judge is asked to eyeball — but only for the rules that
    actually key on them. A red mark on `escalated` under a volume finding would
    imply a fault the finding does not claim. */
function Row({ record, ruleId }: { record: AlertRecord; ruleId: string }) {
  const flagsClosure = ruleId === "EG-001";
  const flagsEscalation = ruleId === "EG-001" || ruleId === "EG-002";

  const fastClose =
    flagsClosure &&
    record.closure_time_minutes !== null &&
    record.closure_time_minutes < 2;

  return (
    <tr>
      <td className="num">{record.record_id}</td>
      <td>{record.severity}</td>
      <td>{record.category}</td>
      <td className="num">{timestamp(record.opened_at)}</td>
      <td className="num">{timestamp(record.closed_at)}</td>
      <td className="num">
        {fastClose ? (
          <span className="ringed">{minutes(record.closure_time_minutes)}</span>
        ) : (
          minutes(record.closure_time_minutes)
        )}
      </td>
      <td>
        {!record.escalated && flagsEscalation ? (
          <span className="ringed">No</span>
        ) : (
          record.escalated ? "Yes" : "No"
        )}
      </td>
      <td>{record.disposition}</td>
      <td className="notes">
        {record.investigation_notes ?? <span className="muted">— none recorded —</span>}
      </td>
    </tr>
  );
}

export default function EvidenceView() {
  const { id = "" } = useParams();
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setEvidence(await getEvidence(id));
    } catch (e) {
      setEvidence(null);
      setError(e instanceof ApiError ? e : new ApiError("Something went wrong.", 500));
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const backLink = evidence ? `/entities/${evidence.entity_id}` : "/";

  if (error?.status === 404) {
    return (
      <>
        <Link className="crumb" to="/">← All entities</Link>
        <NotFound message="Finding not found" />
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

  if (!evidence) {
    return (
      <>
        <Link className="crumb" to="/">← All entities</Link>
        <div style={{ marginTop: 18 }}>
          <Loading rows={5} label="Loading evidence" />
        </div>
      </>
    );
  }

  return (
    <>
      <Link className="crumb" to={backLink}>← {evidence.entity_name}</Link>

      <div className="detail-head">
        <div>
          <h1 className="detail-title">{evidence.title}</h1>
          <p className="detail-meta">
            <span className="wp-ref wp-ref--lead">
              {findingRef(evidence.entity_id, evidence.rule_id)}
            </span>
            <span className="entity-id">{evidence.rule_id}</span> ·{" "}
            {evidence.finding_id} · {evidence.weight} pts · {evidence.entity_name}
          </p>
        </div>
      </div>

      <p className="evidence-lead">{evidence.explanation}</p>

      <h2 className="section-title">
        Source records
        <span className="rule-card__count"> ({evidence.records.length})</span>
      </h2>
      <p className="section-note">
        Every record the finding was computed from, exactly as held in the dataset.
      </p>

      <div className="table-scroll">
        <table className="records">
          <thead>
            <tr>
              <th scope="col">Record</th>
              <th scope="col">Severity</th>
              <th scope="col">Category</th>
              <th scope="col">Opened</th>
              <th scope="col">Closed</th>
              <th scope="col">Closure (min)</th>
              <th scope="col">Escalated</th>
              <th scope="col">Disposition</th>
              <th scope="col">Investigation notes</th>
            </tr>
          </thead>
          <tbody>
            {evidence.records.map((r) => (
              <Row record={r} ruleId={evidence.rule_id} key={r.record_id} />
            ))}
          </tbody>
        </table>
      </div>

      <div className="stamp-row">
        <span className="stamp">
          <span className="stamp__main">Verified against source records</span>
          <span className="stamp__sub">
            SAT-SA · {findingRef(evidence.entity_id, evidence.rule_id)} ·{" "}
            {evidence.records.length}{" "}
            {evidence.records.length === 1 ? "record" : "records"}
          </span>
        </span>
      </div>

      {evidence.rule_id === "ML-001" && (
        <p className="footnote">
          Corroborating signal only — evaluated solely because deterministic rules already
          raised a finding for this entity, and never the sole basis for one. The model is
          an unsupervised Isolation Forest over a small peer group; it has not been
          validated or measured for accuracy, and the records below are the entity’s full
          alert history rather than a model-selected subset.
        </p>
      )}
      {/* NS-001 now performs a peer-cohort comparison where the cohort is
          statistically valid, and says in its own explanation which baseline it used
          and why. This footnote must not contradict that sentence on the same screen,
          so it explains the gate rather than claiming the feature is absent. */}
      {evidence.rule_id === "NS-001" && (
        <p className="footnote">
          Peer-cohort comparison is used only where a cohort is large enough to support
          it (at least 5 entities). Where it is not, the rule falls back to the global
          dataset baseline and states so above — a cohort of one has no spread to
          measure against, so a threshold drawn from it would be arithmetic rather than
          evidence.
        </p>
      )}
      {evidence.rule_id === "NS-002" && (
        <p className="footnote">
          Category coverage is compared against the other entities in this dataset only —
          peer-cohort grouping planned for next phase.
        </p>
      )}
    </>
  );
}
