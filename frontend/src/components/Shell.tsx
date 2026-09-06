/** The application shell.
 *
 *  v1 had a masthead on the ranking screen and nothing on the other two, so the
 *  detail and evidence screens rendered as loose documents with a back-link
 *  floating above them. This is a workspace: the same bar is present on every
 *  screen, it always says which dataset the figures were computed over, and the
 *  data actions are reachable from wherever you happen to be.
 *
 *  Holding the dataset here means the pages no longer own it. `version` bumps on
 *  every load, and a page watching it refetches — which is why uploading from
 *  the evidence screen still leaves a correct ranking behind you.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  ApiError,
  DatasetInfo,
  TEMPLATE_URL,
  getDataset,
  resetDemo,
  uploadDataset,
} from "../api";
import LineSidebar from "./LineSidebar";

interface DatasetState {
  dataset: DatasetInfo | null;
  /** Bumps whenever the loaded dataset changes. Pages refetch on a change. */
  version: number;
  busy: boolean;
  openPicker: () => void;
  /** For a page that changed the data itself -- the Data screen's clear action --
      so every other screen refetches without it needing to know who they are. */
  bumpVersion: () => void;
  /** Refetch provenance after a change made elsewhere. */
  refreshDataset: () => Promise<void>;
  /** Restore the built-in seed. Lives here rather than on the Data screen because
      it shares the shell's busy state and its error banner. */
  resetDemo: () => Promise<void>;
}

const DatasetContext = createContext<DatasetState>({
  dataset: null,
  version: 0,
  busy: false,
  openPicker: () => {},
  bumpVersion: () => {},
  refreshDataset: async () => {},
  resetDemo: async () => {},
});

export const useDataset = () => useContext(DatasetContext);

/** Three measures of unequal length against a baseline: the ranking screen as a
    glyph. Not a shield and not a rocket — it draws what the tool actually does. */
function Mark() {
  return (
    <svg className="brand__mark" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M2 2v16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path
        d="M4.5 5.5h12M4.5 10h7.5M4.5 14.5h4"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        opacity="0.9"
      />
    </svg>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const [dataset, setDataset] = useState<DatasetInfo | null>(null);
  const [version, setVersion] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [resetting, setResetting] = useState(false);
  // A rejected upload reports every problem it found at once, so the operator
  // fixes the file in one pass instead of re-uploading to discover the next one.
  const [uploadError, setUploadError] =
    useState<{ message: string; details: string[] } | null>(null);
  // An accepted upload whose columns had to be translated. Shown, never
  // swallowed: the operator is the only one who can tell us we read 'status' as
  // the wrong field, and a mapping they cannot see is one they cannot correct.
  const [mappingNotes, setMappingNotes] = useState<string[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const busy = uploading || resetting;

  const refreshDataset = useCallback(async () => {
    try {
      setDataset(await getDataset());
    } catch {
      // Provenance is secondary. A schedule that renders while /api/dataset
      // fails is still a correct schedule; it simply loses its caption.
      setDataset(null);
    }
  }, []);

  useEffect(() => {
    void refreshDataset();
  }, [refreshDataset]);

  async function onFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Cleared immediately so re-picking the same file after a fix still fires.
    event.target.value = "";
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setMappingNotes([]);
    try {
      const result = await uploadDataset(file);
      setMappingNotes(result.mapping_notes ?? []);
      await refreshDataset();
      setVersion((v) => v + 1);
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      setUploadError({
        message: err?.message ?? "Upload failed.",
        details: err?.details ?? [],
      });
    } finally {
      setUploading(false);
    }
  }

  async function onReset() {
    setResetting(true);
    setUploadError(null);
    setMappingNotes([]);
    try {
      await resetDemo();
      await refreshDataset();
      setVersion((v) => v + 1);
    } catch (e) {
      setUploadError({
        message: e instanceof ApiError ? e.message : "Reset failed.",
        details: [],
      });
    } finally {
      setResetting(false);
    }
  }

  const openPicker = useCallback(() => fileInput.current?.click(), []);
  const bumpVersion = useCallback(() => setVersion((v) => v + 1), []);

  return (
    <DatasetContext.Provider
      value={{
        dataset, version, busy, openPicker, bumpVersion, refreshDataset,
        resetDemo: onReset,
      }}
    >
      <a className="skip" href="#main">Skip to content</a>

      <header className="topbar">
        <div className="topbar__inner">
          <div className="brand">
            <Mark />
            <span className="brand__name">SAT-SA</span>
            <span className="brand__desc">
              Supervisory Analytics for SOC Assessment
            </span>
          </div>

          <span className="topbar__spacer" />

          {dataset && (
            <span
              className={`source${dataset.source === "upload" ? "" : " source--seed"}`}
              title={`${dataset.entity_count} entities · ${dataset.record_count.toLocaleString()} records`}
            >
              <span className="source__dot" aria-hidden="true" />
              <span className="sr-only">Dataset in use: </span>
              <span className="source__label">
                {dataset.source === "upload" ? dataset.label : "demo seed"}
              </span>
              <span className="source__n">
                {dataset.record_count.toLocaleString()} rec
              </span>
            </span>
          )}

          <div className="topbar__actions">
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.json,text/csv,application/json"
              className="sr-only"
              onChange={onFileChosen}
            />
            <button
              type="button"
              className="btn btn--primary"
              onClick={openPicker}
              disabled={busy}
            >
              {uploading ? "Loading…" : "Load alert export"}
            </button>
          </div>
        </div>
      </header>

      <div className="shell">
        <LineSidebar />
        <main className="page" id="main">
        <div className="notices">
          {mappingNotes.length > 0 && (
            <div className="banner banner--stack banner--info" role="status">
              <div className="banner__head">
                <span>
                  Loaded. This file did not use the standard column names, so it was
                  read as follows — check this before trusting the schedule.
                </span>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setMappingNotes([])}
                >
                  Dismiss
                </button>
              </div>
              <ul className="banner__list">
                {mappingNotes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </div>
          )}

          {uploadError && (
            <div className="banner banner--stack" role="alert">
              <div className="banner__head">
                <span>{uploadError.message}</span>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setUploadError(null)}
                >
                  Dismiss
                </button>
              </div>
              {uploadError.details.length > 0 && (
                <ul className="banner__list">
                  {uploadError.details.map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
              )}
              <p className="banner__note">
                Required fields: record_id, entity_id, entity_name, sector, asset_id,
                severity, category, opened_at, disposition — plus optional closed_at,
                escalated, investigation_notes, closure_time_minutes. Your export need
                not use these exact names: common spellings (alert_id, org_id,
                priority, created_at, resolution, TTR…) are recognised, and the
                translation is shown to you after loading.{" "}
                <a className="btn--link" href={TEMPLATE_URL}>
                  Download a template
                </a>
                .
              </p>
            </div>
          )}
        </div>

          {children}
        </main>
      </div>
    </DatasetContext.Provider>
  );
}
