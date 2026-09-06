/** The Overview — how is this population of SOCs performing?
 *
 *  Six panels, each answering one question a supervisor would actually ask, and each
 *  drawn in the form that question deserves rather than the form that fills the space:
 *
 *   1. Where do the scores sit?          -> histogram over fixed bands
 *   2. Is alert volume steady?           -> line over time, day or week
 *   3. How long do alerts stay open?     -> three percentiles on one scale
 *   4. Which rules are firing?           -> ranked bars, coloured by tier
 *   5. What is the severity mix?         -> labelled bar rows
 *   6. How are alerts being dispositioned? -> labelled bar rows
 *
 *  Every number comes from `/api/analytics/overview` already computed. This file
 *  formats and lays out; it does not derive. That is what keeps one definition of the
 *  median in the system, in SQL, where `verify.py` can assert it.
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

import { ApiError, Overview, getOverview } from "../api";
import { BarRow, CHART, ChartTip, Key, Panel } from "../components/charts";
import EmptyState from "../components/EmptyState";
import { useDataset } from "../components/Shell";
import { ErrorState, Loading } from "../components/States";
import { TIER_LABEL, formatScore } from "../workpaper";

/* Validated against the dark surface with the dataviz palette checker: all six checks
   pass, including the all-pairs CVD and normal-vision separation. Do not substitute
   these by eye -- the previous set failed the normal-vision floor at ΔE 9.4, which
   means full-colour readers could not reliably separate two adjacent segments. */
const TIER_COLOR: Record<string, string> = {
  EXECUTION_GAP: "var(--tier-eg)",
  NEGATIVE_SPACE: "var(--tier-ns)",
  ML_CORROBORATION: "var(--tier-ml)",
};

const BAND_COLOR: Record<string, string> = {
  exception: "var(--exception)",
  caution: "var(--caution)",
  clear: "var(--clear)",
};

/** Severity carries the reserved status colours for the two levels a supervisor acts
    on, and text-token ink for the two they do not. Colour marks what matters rather
    than painting every row for decoration. */
const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: "var(--exception)",
  HIGH: "var(--caution)",
  MEDIUM: "var(--mark-2)",
  LOW: "var(--mark-3)",
};

function minutes(v: number | null): string {
  if (v === null) return "—";
  if (v < 90) return `${v.toFixed(0)} min`;
  const h = v / 60;
  return h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`;
}

export default function OverviewPage() {
  const { version, bumpVersion, refreshDataset } = useDataset();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [grain, setGrain] = useState<"day" | "week">("day");

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getOverview());
    } catch (e) {
      setData(null);
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, version]);

  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!data) return <Loading rows={6} label="Loading the overview" />;

  // No data is a screen of its own, not a dashboard of zeros.
  if (data.record_count === 0) {
    return (
      <EmptyState
        onLoaded={async () => {
          await refreshDataset();
          bumpVersion();
        }}
      />
    );
  }

  const series = grain === "day" ? data.volume_by_day : data.volume_by_week;
  const rules = data.findings_by_rule;
  const maxRule = Math.max(...rules.map((r) => r.count), 1);
  const sevTotal = data.severity_mix.reduce((n, s) => n + s.count, 0);
  const maxSev = Math.max(...data.severity_mix.map((s) => s.count), 1);
  const dispTotal = data.disposition_mix.reduce((n, s) => n + s.count, 0);
  const maxDisp = Math.max(...data.disposition_mix.map((s) => s.count), 1);
  const c = data.closure;
  const maxClosure = Math.max(c.mean ?? 0, c.median ?? 0, c.p90 ?? 0, 1);

  return (
    <>
      <div className="head">
        <div>
          <h1 className="hd">Overview</h1>
          <p className="hd__sub">
            The whole population at a glance — how risk is distributed, how alerts
            arrive, how quickly they are closed, and which supervisory rules are
            producing the findings.
          </p>
        </div>
      </div>

      <section className="stats" aria-label="Dataset summary">
        <div className="stat">
          <span className="lbl">Entities under review</span>
          <span className="stat__value">{data.entity_count}</span>
          <span className="stat__sub">
            across <b>{data.sector_count}</b>{" "}
            {data.sector_count === 1 ? "sector" : "sectors"} · <b>{data.clean_count}</b>{" "}
            with no findings
          </span>
        </div>
        <div className="stat">
          <span className="lbl">Alerts analysed</span>
          <span className="stat__value">{data.record_count.toLocaleString()}</span>
          <span className="stat__sub">
            <b>
              {Math.round(data.record_count / data.entity_count).toLocaleString()}
            </b>{" "}
            per entity on average
          </span>
        </div>
        <div className="stat">
          <span className="lbl">Findings raised</span>
          <span className="stat__value">{data.finding_count.toLocaleString()}</span>
          <span className="stat__sub">
            on <b>{data.attention_count}</b> of {data.entity_count} entities
          </span>
        </div>
        <div className="stat">
          <span className="lbl">Median closure</span>
          <span className="stat__value">{minutes(c.median)}</span>
          <span className="stat__sub">
            {c.p90 === null ? (
              "no closed alerts to measure"
            ) : (
              <>
                <b>{minutes(c.p90)}</b> at the 90th percentile
              </>
            )}
          </span>
        </div>
      </section>

      <div className="grid">
        <Panel
          title="Where the scores sit"
          caption="Entities per 10-point band of supervisory risk score, over the attainable 0–86.5 range. Bars carry the same banding the ranking screen colours by."
          table={{
            columns: ["Score band", "Entities", "Supervisory band"],
            rows: data.score_distribution.map((b) => [b.label, b.count, b.band]),
          }}
          actions={
            <Key
              items={[
                { label: "clear", color: "var(--clear)" },
                { label: "caution", color: "var(--caution)" },
                { label: "exception", color: "var(--exception)" },
              ]}
            />
          }
        >
          <ResponsiveContainer width="100%" height={190}>
            <BarChart
              data={data.score_distribution}
              margin={{ top: 4, right: 4, bottom: 0, left: -22 }}
            >
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis
                dataKey="label"
                tick={CHART.axisTick}
                axisLine={{ stroke: CHART.grid }}
                tickLine={false}
              />
              <YAxis
                tick={CHART.axisTick}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <ChartTip labelSuffix=" score band" />
              <Bar dataKey="count" name="Entities" radius={[4, 4, 0, 0]} maxBarSize={28}>
                {data.score_distribution.map((b) => (
                  <Cell key={b.label} fill={BAND_COLOR[b.band]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel
          title="Alert volume over time"
          caption={
            `Alerts opened per ${grain} across the whole population, over ` +
            `${data.volume.days} days. Daily volume runs between ` +
            `${data.volume.per_day_min.toLocaleString()} and ` +
            `${data.volume.per_day_max.toLocaleString()} — a flat line here means a ` +
            `steady intake, not a chart that failed to draw.`
          }
          table={{
            columns: [grain === "day" ? "Day" : "Week beginning", "Alerts"],
            rows: series.map((b) => [b.bucket, b.count]),
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
                dataKey="bucket"
                tick={CHART.axisTick}
                axisLine={{ stroke: CHART.grid }}
                tickLine={false}
                minTickGap={44}
              />
              <YAxis tick={CHART.axisTick} axisLine={false} tickLine={false} />
              <ChartTip />
              <Line
                type="monotone"
                dataKey="count"
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
            c.median === null
              ? "No alert in this dataset carries a closure time, so there is nothing to measure."
              : `Three points on one scale, over ${c.measured_on.toLocaleString()} closed alerts. The gap between the median and the 90th percentile is the tail — the mean alone hides it.`
          }
          table={{
            columns: ["Statistic", "Minutes"],
            rows: [
              ["Mean", c.mean ?? "—"],
              ["Median", c.median ?? "—"],
              ["90th percentile", c.p90 ?? "—"],
            ],
          }}
        >
          {c.median === null ? (
            <p className="panel__none">
              Closure time is derived from <code>closed_at</code> or supplied as{" "}
              <code>closure_time_minutes</code>. This export carries neither, so the
              panel is empty rather than showing zero — which would read as a SOC that
              closes everything instantly.
            </p>
          ) : (
            <div className="brows">
              <BarRow label="Mean" value={c.mean ?? 0} max={maxClosure}
                      color="var(--mark-2)" suffix=" min" />
              <BarRow label="Median" value={c.median ?? 0} max={maxClosure}
                      color="var(--accent)" suffix=" min" />
              <BarRow label="90th percentile" value={c.p90 ?? 0} max={maxClosure}
                      color="var(--caution)" suffix=" min" />
              {c.unclosed > 0 && (
                <p className="panel__foot">
                  {c.unclosed.toLocaleString()} alerts have no closure time and are
                  excluded, not counted as zero.
                </p>
              )}
            </div>
          )}
        </Panel>

        <Panel
          title="Which rules are firing"
          caption="Findings per rule across every entity, ranked. Colour is the scoring tier the rule belongs to."
          table={{
            columns: ["Rule", "Tier", "Findings", "Total weight"],
            rows: rules.map((r) => [
              r.rule_id, TIER_LABEL[r.tier] ?? r.tier, r.count, r.weight,
            ]),
          }}
          actions={
            <Key
              items={[
                { label: "Execution gap", color: "var(--tier-eg)" },
                { label: "Negative space", color: "var(--tier-ns)" },
                { label: "ML corroboration", color: "var(--tier-ml)" },
              ]}
            />
          }
        >
          <div className="brows">
            {rules.map((r) => (
              <BarRow
                key={r.rule_id}
                label={r.rule_id}
                value={r.count}
                max={maxRule}
                color={TIER_COLOR[r.tier]}
              />
            ))}
          </div>
        </Panel>

        <Panel
          title="Severity mix"
          caption="Every alert in the dataset by the severity its SOC assigned. The two levels a supervisor acts on carry the reserved severity colours; the rest are labelled."
          table={{
            columns: ["Severity", "Alerts", "Share"],
            rows: data.severity_mix.map((s) => [
              s.key, s.count, `${((s.count / sevTotal) * 100).toFixed(1)}%`,
            ]),
          }}
        >
          <div className="brows">
            {data.severity_mix.map((s) => (
              <BarRow
                key={s.key}
                label={s.key}
                value={s.count}
                share={(s.count / sevTotal) * 100}
                max={maxSev}
                color={SEVERITY_COLOR[s.key] ?? "var(--ink-faint)"}
              />
            ))}
          </div>
        </Panel>

        <Panel
          title="How alerts are dispositioned"
          caption="The outcome each alert was closed with. A dataset dominated by false positives and benign closures is the pattern the execution-gap rules exist to interrogate."
          table={{
            columns: ["Disposition", "Alerts", "Share"],
            rows: data.disposition_mix.map((s) => [
              s.key, s.count, `${((s.count / dispTotal) * 100).toFixed(1)}%`,
            ]),
          }}
        >
          <div className="brows">
            {data.disposition_mix.map((s) => (
              <BarRow
                key={s.key}
                label={s.key.replace(/_/g, " ").toLowerCase()}
                value={s.count}
                share={(s.count / dispTotal) * 100}
                max={maxDisp}
                color="var(--accent)"
              />
            ))}
          </div>
        </Panel>
      </div>

      <p className="note">
        Every figure on this screen is computed by the backend and served whole, so a
        number here and the same number on an entity's schedule cannot disagree. The
        attainable maximum score is {formatScore(86.5)}, not 100 — the ML tier can
        contribute at most 1.5.
      </p>
    </>
  );
}
