/** Screen 3 — the records one finding was computed from.
 *
 *  On its own route, so browser-back is the way out and the trail from score to
 *  finding to record is a real navigation history rather than a disclosure state.
 *  The full record set renders rather than paginating: for a negative-space
 *  finding, the shortness of the table is the evidence.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { AlertRecord, ApiError, Evidence, getEvidence } from "../api";
import Crumbs from "../components/Crumbs";
import { Loading, ErrorState, NotFound } from "../components/States";
import { findingRef } from "../workpaper";

function timestamp(value: string | null): string {
  if (!value) return "—";
  return value.replace("T", " ").slice(0, 16);
}

function minutes(value: number | null): string {
  return value === null ? "—" : String(value);
}

/** Marks the fields a reader is being asked to eyeball — but only for the rules
    that actually key on them. A mark on `escalated` under a volume finding would
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
          <span className="flag">{minutes(record.closure_time_minutes)}</span>
        ) : (
          minutes(record.closure_time_minutes)
        )}
      </td>
      <td>
        {!record.escalated && flagsEscalation ? (
          <span className="flag">No</span>
        ) : record.escalated ? (
          "Yes"
        ) : (
          "No"
        )}
      </td>
      <td>{record.disposition}</td>
      <td className="notes">
        {record.investigation_notes ?? (
          <span className="muted">none recorded</span>
        )}
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

  if (error?.status === 404) {
    return (
      <>
        <Crumbs trail={[{ label: "Ranking", to: "/" }, { label: "Not found" }]} />
        <NotFound message="No such finding" />
      </>
    );
  }

  if (error) {
    return (
      <>
        <Crumbs trail={[{ label: "Ranking", to: "/" }, { label: "Evidence" }]} />
        <ErrorState message={error.message} onRetry={() => void load()} backTo />
      </>
    );
  }

  if (!evidence) {
    return (
      <>
        <Crumbs trail={[{ label: "Ranking", to: "/" }, { label: "Evidence" }]} />
        <Loading rows={5} label="Loading evidence" />
      </>
    );
  }

  return (
    <>
      <Crumbs
        trail={[
          { label: "Ranking", to: "/" },
          { label: evidence.entity_name, to: `/entities/${evidence.entity_id}` },
          { label: evidence.finding_id },
        ]}
      />

      <div className="head">
        <div>
          <h1 className="hd">{evidence.title}</h1>
          <p className="head__meta">
            <span className="tag tag--ref">
              {findingRef(evidence.entity_id, evidence.rule_id)}
            </span>
            <span className="tag">{evidence.rule_id}</span>
            <span className="tag">{evidence.finding_id}</span>
            {evidence.weight} pts · {evidence.entity_name}
          </p>
        </div>
      </div>

      <p className="lead">{evidence.explanation}</p>

      <div className="sect">
        <h2 className="sect__title">Source records</h2>
        <span className="sect__n">
          {evidence.records.length}{" "}
          {evidence.records.length === 1 ? "record" : "records"}
        </span>
      </div>
      <p className="sect__note">
        Every record the finding was computed from, exactly as held in the dataset.
        Where a rule keys on a particular field, that field is marked on the rows it
        read.
      </p>

      <div className="sheet sheet--scroll">
        <table className="records">
          <caption className="sr-only">
            Alert records underlying finding {evidence.finding_id}.
          </caption>
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

      <p className="foot">
        <span className="foot__mark">✓ verified against source records</span>
        <span>
          SAT-SA · {findingRef(evidence.entity_id, evidence.rule_id)} ·{" "}
          {evidence.records.length}{" "}
          {evidence.records.length === 1 ? "record" : "records"}
        </span>
      </p>

      {evidence.rule_id === "ML-001" && (
        <p className="note">
          Corroborating signal only — evaluated solely because deterministic rules
          already raised a finding for this entity, and never the sole basis for
          one. The model is an unsupervised Isolation Forest over a small peer
          group; it has not been validated or measured for accuracy, and the records
          above are the entity's full alert history rather than a model-selected
          subset.
        </p>
      )}
      {/* NS-001 performs a peer-cohort comparison where the cohort is statistically
          valid, and says in its own explanation which baseline it used. This note
          must not contradict that sentence on the same screen, so it explains the
          gate rather than claiming the feature is absent. */}
      {evidence.rule_id === "NS-001" && (
        <p className="note">
          Peer-cohort comparison is used only where a cohort is large enough to
          support it (at least 5 entities). Where it is not, the rule falls back to
          the global dataset baseline and says so above — a cohort of one has no
          spread to measure against, so a threshold drawn from it would be
          arithmetic rather than evidence.
        </p>
      )}
      {evidence.rule_id === "NS-002" && (
        <p className="note">
          Category coverage is compared against the other entities in this dataset
          only — peer-cohort grouping is planned for the next phase.
        </p>
      )}
    </>
  );
}
