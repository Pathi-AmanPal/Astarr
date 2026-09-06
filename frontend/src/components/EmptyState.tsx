/** The screen before any data exists.
 *
 *  A first-class screen, not a blank area with a button. It is also the first thing
 *  anyone sees in a demo, so it has to answer three questions without being asked:
 *  what does this tool want, what will it do with it, and what happens if my file is
 *  wrong.
 *
 *  The drop zone is a <label> wrapping a real <input type="file">, which is what
 *  makes it work from the keyboard without a single key handler: the input is
 *  focusable, Space and Enter open the picker, and the label is its accessible name.
 *  Drag-and-drop is added on top for pointer users and is never the only way in.
 */

import { useCallback, useRef, useState } from "react";

import { ApiError, TEMPLATE_URL, uploadDataset } from "../api";

const REQUIRED = [
  "record_id", "entity_id", "entity_name", "sector", "asset_id",
  "severity", "category", "opened_at", "disposition",
];
const OPTIONAL = ["closed_at", "escalated", "investigation_notes", "closure_time_minutes"];

export default function EmptyState({
  onLoaded,
}: {
  /** Called once the dataset is in and detection has run. */
  onLoaded: (notes: string[]) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; details: string[] } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const send = useCallback(
    async (file: File) => {
      setBusy(true);
      setError(null);
      try {
        const result = await uploadDataset(file);
        onLoaded(result.mapping_notes ?? []);
      } catch (e) {
        const err = e instanceof ApiError ? e : null;
        setError({
          message: err?.message ?? "Upload failed.",
          details: err?.details ?? [],
        });
      } finally {
        setBusy(false);
      }
    },
    [onLoaded],
  );

  return (
    <div className="onboard">
      <div className="onboard__lead">
        <h1 className="hd">Load a SOC alert export</h1>
        <p className="hd__sub">
          This tool ships with no data of its own. Give it an export of alert records
          and it validates every row, runs eight supervisory rules across the entities
          it finds, and ranks them — with every score traceable back to the records
          that produced it.
        </p>
      </div>

      <label
        className={`drop${dragging ? " is-dragging" : ""}${busy ? " is-busy" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file && !busy) void send(file);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.json,text/csv,application/json"
          className="sr-only"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void send(file);
          }}
        />
        <svg className="drop__icon" viewBox="0 0 32 32" aria-hidden="true">
          <path
            d="M16 22V6m0 0-6 6m6-6 6 6M5 22v3a2 2 0 0 0 2 2h18a2 2 0 0 0 2-2v-3"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="drop__title">
          {busy ? "Validating and loading…" : "Drop a CSV or JSON file here"}
        </span>
        <span className="drop__sub">
          {busy ? "Large exports take a few seconds" : "or select one — up to a million rows"}
        </span>
      </label>

      {error && (
        <div className="banner banner--stack" role="alert">
          <div className="banner__head">
            <span>{error.message}</span>
            <button type="button" className="btn" onClick={() => setError(null)}>
              Dismiss
            </button>
          </div>
          {/* Every problem at once, with its line number. One pass to fix the file
              rather than one upload per mistake. */}
          {error.details.length > 0 && (
            <ul className="banner__list">
              {error.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="onboard__schema">
        <div className="sect">
          <h2 className="sect__title">What the file needs</h2>
          <a className="btn" href={TEMPLATE_URL}>
            Download a 3-row template
          </a>
        </div>
        <dl className="schema">
          <div>
            <dt className="lbl">Required</dt>
            <dd>
              {REQUIRED.map((c) => (
                <code className="tag" key={c}>{c}</code>
              ))}
            </dd>
          </div>
          <div>
            <dt className="lbl">Optional</dt>
            <dd>
              {OPTIONAL.map((c) => (
                <code className="tag" key={c}>{c}</code>
              ))}
            </dd>
          </div>
        </dl>
        <p className="sect__note">
          Your export does not need these exact names. Common spellings —{" "}
          <code>alert_id</code>, <code>Org_ID</code>, <code>Priority</code>,{" "}
          <code>Created At</code>, <code>Resolution</code>, <code>TTR</code> — are
          recognised, along with vendor severity scales (P1, Sev 3) and resolution
          codes (TP, FP, No Action Required). Whatever the parser translates is
          reported back to you after loading, so you can check it read your columns
          the way you meant them.
        </p>
      </div>
    </div>
  );
}
