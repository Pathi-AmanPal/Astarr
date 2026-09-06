/** The Overview — how is this population of SOCs performing?
 *
 *  Six panels, each answering a question a supervisor would actually ask, and each
 *  drawn in the form that question deserves rather than the form that fills the space:
 *
 *   1. Where do the scores sit?            -> bars over the supervisory bands
 *   2. Is alert volume steady?             -> line over time, day or week
 *   3. How long do alerts stay open?       -> three percentiles on one scale
 *   4. What is the severity mix?           -> labelled bar rows
 *   5. How are alerts dispositioned?       -> labelled bar rows
 *   6. What is the handling risk?          -> four rates, each with its denominator
 *
 *  Every number is computed by the backend. This file lays out and formats; it derives
 *  nothing. That is what keeps one definition of the median in the system, in SQL,
 *  where verify.py can assert it.
 *
 *  The four analytics endpoints are fetched together and the screen renders nothing
 *  until all four resolve. Rendering them as they arrive would let two panels show
 *  different datasets for a moment after a load — briefly, and wrongly.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

import {
  ApiError,
  Distribution,
  HandlingQuality,
  OverviewMetrics,
  TimeBucket,
  getDistribution,
  getHandling,
  getOverview,
  getTimeseries,
} from "../api";
import { BarRow, CHART, ChartTip, Key, Panel } from "../components/charts";
import EmptyState from "../components/EmptyState";
import { useDataset } from "../components/Shell";
import { ErrorState, Loading } from "../components/States";
import { ATTAINABLE_MAX } from "../workpaper";

/** Band colours, matched to the ranking screen's chips. The backend now bands at the
    same thresholds the table does — they disagreed until 2026-09-06, and verify.py
    pins them together — so these names are the backend's, not a second vocabulary. */
const BAND_COLOR: Record<string, string> = {
  "Exception (> 50)": "var(--exception)",
  "Caution (10 - 50)": "var(--caution)",
  "Clear (< 10)": "var(--clear)",
};

/** Severity carries the reserved status colours for the two levels a supervisor acts
    on, and measured neutral ink for the two they do not. Colour marks what matters
    instead of painting every row for decoration. */
const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: "var(--exception)",
  HIGH: "var(--caution)",
  MEDIUM: "var(--mark-2)",
  LOW: "var(--mark-3)",
};

function minutes(v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (v < 90) return `${v.toFixed(0)} min`;
  const h = v / 60;
  return h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`;
}

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

interface Bundle {
  overview: OverviewMetrics;
  series: TimeBucket[];
  score: Distribution;
  severity: Distribution;
  disposition: Distribution;
  handling: HandlingQuality;
}

export default function OverviewPage() {
  const { version, bumpVersion, refreshDataset } = useDataset();
  const [data, setData] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [grain, setGrain] = useState<"day" | "week">("day");

  const load = useCallback(async (bucket: "day" | "week") => {
    setError(null);
    try {
      const [overview, series, score, severity, disposition, handling] =
        await Promise.all([
          getOverview(),
          getTimeseries(bucket),
          getDistribution("score"),
          getDistribution("severity"),
          getDistribution("disposition"),
          getHandling(),
        ]);
      setData({ overview, series, score, severity, disposition, handling });
    } catch (e) {
      setData(null);
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    }
  }, []);

  useEffect(() => {
    void load(grain);
  }, [load, version, grain]);

  if (error) return <ErrorState message={error} onRetry={() => void load(grain)} />;
  if (!data) return <Loading rows={6} label="Loading the overview" />;

  const { overview: o, series, score, severity, disposition, handling: h } = data;

  // Nothing loaded is a screen of its own, not a dashboard of zeros.
  if (o.alerts_count === 0) {
    return (
      <EmptyState
        onLoaded={async () => {
          await refreshDataset();
          bumpVersion();
        }}
      />
    );
  }

  const maxSev = Math.max(...severity.items.map((s) => s.count), 1);
  const maxDisp = Math.max(...disposition.items.map((s) => s.count), 1);
  const maxClosure = Math.max(
    h.mean_closure_minutes ?? 0,
    h.median_closure_minutes ?? 0,
    h.p90_closure_minutes ?? 0,
    1,
  );
  const volumes = series.map((s) => s.total);
  const lo = volumes.length ? Math.min(...volumes) : 0;
  const hi = volumes.length ? Math.max(...volumes) : 0;

  /* Three rates where lower is better, and they are the only things in the bar list.
     `critical_escalation_rate` is COVERAGE -- criticals escalated over all criticals
     -- so higher is better, and it is reported separately below rather than as a
     fourth bar. It sat in this list labelled "Critical unescalated" and coloured
     amber above 5%, which turned a SOC escalating 99.1% of its CRITICALs into a
     warning. A panel that mixes directions cannot be read: the eye takes a long bar
     as a bad bar, and here one long bar was the best number on the screen. */
  const risks = [
    {
      label: "Rapid closure",
      rate: h.rapid_closure_rate,
      of: "of HIGH and CRITICAL alerts closed inside the two-minute threshold EG-001 keys on",
    },
    {
      label: "Undocumented dismissal",
      rate: h.undocumented_dismissal_rate,
      of: "of HIGH and CRITICAL alerts dismissed with no investigation note — EG-004",
    },
    {
      label: "Duplicated notes",
      rate: h.note_duplication_rate,
      of: "of all records carrying a note repeated across unrelated cases — EG-003",
    },
  ];

  return (
    <>
      <div className="head">
        <div>
          <h1 className="hd">Overview</h1>
          <p className="hd__sub">
            The whole population at a glance — how risk is distributed, how alerts
            arrive, how quickly they are closed, and where handling quality is thin.
          </p>
        </div>
      </div>

      <section className="stats" aria-label="Dataset summary">
        <div className="stat">
          <span className="lbl">Entities under review</span>
          <span className="stat__value">{o.entities_count}</span>
          <span className="stat__sub">
            <b>{o.entities_count - o.attention_entities_count}</b> with no findings
          </span>
        </div>
        <div className="stat">
          <span className="lbl">Alerts analysed</span>
          <span className="stat__value">{o.alerts_count.toLocaleString()}</span>
          <span className="stat__sub">
            <b>
              {o.entities_count
                ? Math.round(o.alerts_count / o.entities_count).toLocaleString()
                : 0}
            </b>{" "}
            per entity on average
          </span>
        </div>
        <div className="stat">
          <span className="lbl">Findings raised</span>
          <span className="stat__value">{o.findings_count.toLocaleString()}</span>
          <span className="stat__sub">
            on <b>{o.attention_entities_count}</b> of {o.entities_count} entities
          </span>
        </div>
        <div className="stat">
          <span className="lbl">Median closure</span>
          <span className="stat__value">{minutes(o.median_closure_minutes)}</span>
          <span className="stat__sub">
            {o.p90_closure_minutes === null ? (
              "no closed alerts to measure"
            ) : (
              <>
                <b>{minutes(o.p90_closure_minutes)}</b> at the 90th percentile
              </>
            )}
          </span>
        </div>
      </section>

      <div className="grid">
        <Panel
          title="Where the scores sit"
          caption={`Entities per supervisory band. The scale runs to ${ATTAINABLE_MAX}, not 100, and these are the same bands at the same thresholds that colour the ranking screen — they disagreed until the two were pinned together.`}
          table={{
            columns: ["Band", "Entities", "Share"],
            rows: score.items.map((i) => [i.name, i.count, `${i.percentage}%`]),
          }}
        >
          <ResponsiveContainer width="100%" height={190}>
            <BarChart
              data={score.items}
              margin={{ top: 4, right: 4, bottom: 0, left: -22 }}
            >
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ ...CHART.axisTick, fontSize: 10 }}
                axisLine={{ stroke: CHART.grid }}
                tickLine={false}
              />
              <YAxis
                tick={CHART.axisTick}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <ChartTip />
              <Bar dataKey="count" name="Entities" radius={[4, 4, 0, 0]} maxBarSize={54}>
                {score.items.map((i) => (
                  <Cell key={i.name} fill={BAND_COLOR[i.name] ?? "var(--mark-2)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel
          title="Alert volume over time"
          caption={
            `Alerts opened per ${grain} across the whole population, over ` +
            `${series.length} ${grain === "day" ? "days" : "weeks"}. Volume runs ` +
            `between ${lo.toLocaleString()} and ${hi.toLocaleString()} — a flat line ` +
            `here means a steady intake, not a chart that failed to draw.`
          }
          table={{
            columns: [grain === "day" ? "Day" : "Week beginning", "Alerts"],
            rows: series.map((b) => [b.period, b.total]),
          }}
          actions={
            <div className="toggle" role="group" aria-label="Time grain">
              {(["day", "week"] as const).map((g) => (
                <button
                  key={g}
                  type="button"
                  className={`toggle__btn${grain === g ? " is-on" : ""}`}
                  aria-pressed={grain === g}
                  onClick={() => setGrain(g)}
                >
                  {g === "day" ? "Daily" : "Weekly"}
                </button>
              ))}
            </div>
          }
        >
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={series} margin={{ top: 4, right: 6, bottom: 0, left: -18 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis
                dataKey="period"
                tick={CHART.axisTick}
                axisLine={{ stroke: CHART.grid }}
                tickLine={false}
                minTickGap={44}
              />
              <YAxis tick={CHART.axisTick} axisLine={false} tickLine={false} />
              <ChartTip />
              {/* One series. A second, on its own scale, would need its own panel —
                  never a second y-axis. */}
              <Line
                type="monotone"
                dataKey="total"
                name="Alerts opened"
                stroke="var(--accent)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </Panel>

        <Panel
          title="How long alerts stay open"
          caption={
            h.median_closure_minutes === null
              ? "No alert in this dataset carries a closure time, so there is nothing to measure."
              : `Three points on one scale, over ${h.total_records.toLocaleString()} records. The gap between the median and the 90th percentile is the tail — the mean alone hides it.`
          }
          table={{
            columns: ["Statistic", "Minutes"],
            rows: [
              ["Mean", h.mean_closure_minutes ?? "—"],
              ["Median", h.median_closure_minutes ?? "—"],
              ["90th percentile", h.p90_closure_minutes ?? "—"],
            ],
          }}
        >
          {h.median_closure_minutes === null ? (
            <p className="panel__none">
              Closure time is derived from <code>closed_at</code>, or supplied as{" "}
              <code>closure_time_minutes</code>. This export carries neither, so the
              panel says so rather than drawing zero — which would read as a SOC that
              closes everything instantly.
            </p>
          ) : (
            <div className="brows">
              <BarRow label="Mean" value={h.mean_closure_minutes ?? 0}
                      max={maxClosure} color="var(--mark-2)" suffix=" min" />
              <BarRow label="Median" value={h.median_closure_minutes}
                      max={maxClosure} color="var(--accent)" suffix=" min" />
              <BarRow label="90th percentile" value={h.p90_closure_minutes ?? 0}
                      max={maxClosure} color="var(--caution)" suffix=" min" />
            </div>
          )}
        </Panel>

        <Panel
          title="Handling quality"
          caption="Three conditions the execution-gap rules key on, as a share of the alerts each could apply to. Lower is better for all three — a rate without its denominator is not a measurement, and a panel that mixes directions cannot be read at a glance."
          table={{
            columns: ["Indicator", "Rate", "Denominator and rule"],
            rows: [
              ...risks.map((r) => [r.label, pct(r.rate), r.of]),
              [
                "Critical escalation coverage",
                pct(h.critical_escalation_rate),
                "of CRITICAL alerts escalated — higher is better",
              ],
            ],
          }}
        >
          <div className="brows">
            {risks.map((r) => (
              <BarRow
                key={r.label}
                label={r.label}
                value={Number((r.rate * 100).toFixed(1))}
                // Scaled against a fixed 25% rather than the largest of three near-zero
                // rates, which would magnify 0.3% into a full bar and make a clean
                // population look alarming.
                max={25}
                color={r.rate > 0.05 ? "var(--caution)" : "var(--mark-2)"}
                suffix="%"
              />
            ))}
          </div>
          <p className="panel__foot">
            Bars are drawn against a fixed 25% so a low rate reads as low. Separately,
            and pointing the other way:{" "}
            <b className="num">{pct(h.critical_escalation_rate)}</b> of CRITICAL alerts
            were escalated — coverage, where higher is better. Measured over{" "}
            {h.total_records.toLocaleString()} records.
          </p>
        </Panel>

        <Panel
          title="Severity mix"
          caption="Every alert by the severity its SOC assigned. The two levels a supervisor acts on carry the reserved severity colours; the rest are labelled."
          table={{
            columns: ["Severity", "Alerts", "Share"],
            rows: severity.items.map((s) => [s.name, s.count, `${s.percentage}%`]),
          }}
          actions={
            <Key
              items={[
                { label: "critical", color: "var(--exception)" },
                { label: "high", color: "var(--caution)" },
              ]}
            />
          }
        >
          <div className="brows">
            {severity.items.map((s) => (
              <BarRow
                key={s.name}
                label={s.name}
                value={s.count}
                share={s.percentage}
                max={maxSev}
                color={SEVERITY_COLOR[s.name] ?? "var(--mark-2)"}
              />
            ))}
          </div>
        </Panel>

        <Panel
          title="How alerts are dispositioned"
          caption="The outcome each alert was closed with. A population dominated by false positives and benign closures is the pattern the execution-gap rules exist to interrogate."
          table={{
            columns: ["Disposition", "Alerts", "Share"],
            rows: disposition.items.map((s) => [s.name, s.count, `${s.percentage}%`]),
          }}
        >
          <div className="brows">
            {disposition.items.map((s) => (
              <BarRow
                key={s.name}
                label={s.name.replace(/_/g, " ").toLowerCase()}
                value={s.count}
                share={s.percentage}
                max={maxDisp}
                color="var(--accent)"
              />
            ))}
          </div>
        </Panel>
      </div>

      <p className="note">
        Every figure here is computed by the backend and served whole, so a number on
        this screen and the same number on an entity's schedule cannot disagree. The
        attainable maximum score is {ATTAINABLE_MAX}, not 100 — the ML tier can
        contribute at most 1.5.
      </p>
    </>
  );
}
