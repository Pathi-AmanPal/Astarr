/** Data management — what is loaded, where it came from, and how to get rid of it.
 *
 *  Provenance is the point. Every figure in this tool is an assertion about somebody's
 *  SOC, and an assertion whose source cannot be named is not evidence. This screen is
 *  where "which file produced these 224 findings, and when" is answered.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  DatasetInfo,
  TEMPLATE_URL,
  clearDataset,
  getDataset,
} from "../api";
import Crumbs from "../components/Crumbs";
import { useDataset } from "../components/Shell";
import { ErrorState, Loading } from "../components/States";

function when(iso: string | null): string {
  if (!iso) return "—";
  // The server stamps a naive local timestamp; render it as written rather than
  // shifting it through a timezone the operator never mentioned.
  return iso.replace("T", " ").slice(0, 19);
}

export default function DataPage() {
  const { version, bumpVersion, openPicker, refreshDataset } = useDataset();
  const [dataset, setDataset] = useState<DatasetInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [clearing, setClearing] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const info = await getDataset();
      // The endpoint reports the empty state in the body rather than as a 404, so
      // "nothing loaded" arrives as a successful response and has to be read, not
      // caught. A 404 is still handled below in case an older backend answers.
      setDataset(info.source === "empty" || !info.loaded_at ? null : info);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setDataset(null);
      else setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, version]);

  // Focus moves into the dialog when it opens, and Escape closes it. Without this a
  // keyboard user is left behind on the page while a modal covers it.
  useEffect(() => {
    if (!confirming) return;
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setConfirming(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirming]);

  async function onClear() {
    setClearing(true);
    try {
      await clearDataset();
      setConfirming(false);
      // Both: `refreshDataset` clears the provenance chip in the top bar, which is
      // shell state this page does not own, and `bumpVersion` makes every other
      // screen refetch. Without the first, the bar goes on naming a file that is no
      // longer loaded -- provenance that is wrong is worse than none.
      await refreshDataset();
      bumpVersion();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Clear failed.");
      setConfirming(false);
    } finally {
      setClearing(false);
    }
  }

  return (
    <>
      <Crumbs trail={[{ label: "Overview", to: "/" }, { label: "Data" }]} />

      <div className="head">
        <div>
          <h1 className="hd">Data</h1>
          <p className="hd__sub">
            The dataset every figure in this tool was computed from, and the controls
            that change it.
          </p>
        </div>
      </div>

      {loading && <Loading rows={3} label="Loading dataset provenance" />}

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      {!loading && !error && (
        <>
          <div className="sect">
            <h2 className="sect__title">Loaded dataset</h2>
            <span className="sect__n">{dataset ? "in use" : "none"}</span>
          </div>

          {dataset ? (
            <div className="prov">
              <dl className="prov__grid">
                <div>
                  <dt className="lbl">Source</dt>
                  <dd>
                    {dataset.source === "upload" ? "Uploaded file" : "Built-in demo seed"}
                  </dd>
                </div>
                <div>
                  <dt className="lbl">Name</dt>
                  <dd className="mono">{dataset.label}</dd>
                </div>
                <div>
                  <dt className="lbl">Loaded at</dt>
                  <dd className="mono">{when(dataset.loaded_at)}</dd>
                </div>
                <div>
                  <dt className="lbl">Entities</dt>
                  <dd className="mono">{dataset.entity_count.toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="lbl">Records</dt>
                  <dd className="mono">{dataset.record_count.toLocaleString()}</dd>
                </div>
              </dl>

              <div className="prov__actions">
                <button type="button" className="btn btn--primary" onClick={openPicker}>
                  Replace with another export
                </button>
                <button
                  type="button"
                  className="btn btn--danger"
                  onClick={() => setConfirming(true)}
                >
                  Clear dataset
                </button>
              </div>
            </div>
          ) : (
            <p className="sect__note">
              Nothing is loaded. The Overview screen has the upload control.
            </p>
          )}

          <div className="sect">
            <h2 className="sect__title">Files</h2>
          </div>
          <ul className="files">
            <li>
              <a className="btn--link" href={TEMPLATE_URL}>
                sat-sa-template.csv
              </a>
              <span>
                Three rows and a header. A column reference, not a dataset — download
                it to see exactly what shape the parser expects.
              </span>
            </li>
            <li>
              <span className="mono">samples/soc-dataset.csv</span>
              <span>
                The demonstration export: 51,878 alerts across 40 entities in 8
                sectors. It ships in the repository rather than through this screen,
                deliberately — a one-click sample loader invites the question the
                empty start exists to pre-empt.
              </span>
            </li>
          </ul>
        </>
      )}

      {confirming && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="clear-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) setConfirming(false);
          }}
        >
          <div className="modal__box">
            <h2 className="modal__title" id="clear-title">
              Clear the loaded dataset?
            </h2>
            <p className="modal__body">
              This removes{" "}
              <b className="mono">{dataset?.record_count.toLocaleString() ?? 0}</b>{" "}
              records,{" "}
              <b className="mono">{dataset?.entity_count.toLocaleString() ?? 0}</b>{" "}
              entities and every finding computed from them. It cannot be undone from
              here — you would re-upload the file.
            </p>
            <div className="modal__actions">
              <button
                type="button"
                className="btn"
                onClick={() => setConfirming(false)}
                disabled={clearing}
              >
                Keep it
              </button>
              <button
                ref={confirmRef}
                type="button"
                className="btn btn--danger"
                onClick={onClear}
                disabled={clearing}
              >
                {clearing ? "Clearing…" : "Clear dataset"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
