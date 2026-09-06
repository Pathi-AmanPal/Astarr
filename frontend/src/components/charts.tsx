/** Chart primitives, so every panel on the Overview reads as one instrument.
 *
 *  Decisions that apply to all of them, made once here rather than argued per chart:
 *
 *  - **Recessive grid and axes.** The data is the ink; the frame is scaffolding.
 *  - **No second y-axis, ever.** Two measures of different scale get two charts.
 *  - **Text wears text tokens.** A value or a label is never painted in its series
 *    colour — the mark beside it carries the identity.
 *  - **A hover layer by default.** These are SVG in a browser; a chart you cannot
 *    interrogate is a picture of a chart.
 *  - **A table view for every chart.** Visually hidden, so the figures are reachable
 *    without sight of the plot rather than merely described.
 */

import { ReactNode } from "react";
import { Tooltip } from "recharts";

/** Read a design token, so the charts cannot drift from the stylesheet. */
export function token(name: string, fallback = "#888"): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export const CHART = {
  grid: "rgba(232, 238, 234, 0.07)",
  axis: "#7b8981",
  axisTick: { fill: "#7b8981", fontSize: 10.5, fontFamily: "var(--mono)" },
};

/** One panel: a title that says what the chart answers, a caption that says what the
    numbers are, the plot, and the same figures as a table for anyone who cannot see
    it. The caption is not decoration -- a chart whose units are unstated is unreadable
    however pretty the bars are. */
export function Panel({
  title,
  caption,
  wide,
  children,
  table,
  actions,
}: {
  title: string;
  caption: string;
  wide?: boolean;
  children: ReactNode;
  table: { columns: string[]; rows: (string | number)[][] };
  actions?: ReactNode;
}) {
  return (
    <section className={`panel${wide ? " panel--wide" : ""}`}>
      <header className="panel__head">
        <div>
          <h3 className="panel__title">{title}</h3>
          <p className="panel__caption">{caption}</p>
        </div>
        {actions}
      </header>
      <div className="panel__plot">{children}</div>
      <table className="sr-only">
        <caption>{title}. {caption}</caption>
        <thead>
          <tr>
            {table.columns.map((c) => (
              <th scope="col" key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i}>
              {r.map((cell, j) =>
                j === 0 ? <th scope="row" key={j}>{cell}</th> : <td key={j}>{cell}</td>,
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** One tooltip treatment everywhere. Recharts' default is a white card with a black
    border, which on this ground looks like a browser dialog landed on the page. */
export function ChartTip({
  unit = "",
  labelSuffix = "",
}: {
  unit?: string;
  labelSuffix?: string;
}) {
  return (
    <Tooltip
      cursor={{ fill: "rgba(232, 238, 234, 0.05)", stroke: "transparent" }}
      contentStyle={{
        background: "#1c2421",
        border: "1px solid #36423d",
        borderRadius: 6,
        fontSize: 12,
        padding: "8px 10px",
        boxShadow: "0 8px 24px -8px rgba(4, 8, 6, 0.7)",
      }}
      labelStyle={{ color: "#e8eeea", fontWeight: 600, marginBottom: 4 }}
      itemStyle={{ color: "#a3b0aa" }}
      formatter={(value, name) =>
        [`${Number(value ?? 0).toLocaleString()}${unit}`, String(name ?? "")] as [
          string,
          string,
        ]
      }
      labelFormatter={(label) => `${String(label ?? "")}${labelSuffix}`}
    />
  );
}

/** A legend is present whenever there are two or more series, and it is markup rather
    than a Recharts legend so it sits where the layout wants it and wears text tokens. */
export function Key({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="key">
      {items.map((i) => (
        <li key={i.label}>
          <span
            className="key__swatch"
            style={{ background: i.color }}
            aria-hidden="true"
          />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

/** A labelled horizontal bar row.
 *
 *  Used instead of a pie for every "mix of one categorical field" panel. A pie makes
 *  the reader compare angles; a bar row lets them compare lengths against a shared
 *  left edge, and it carries the count and the share as text without a callout.
 */
export function BarRow({
  label,
  value,
  share,
  max,
  color,
  suffix = "",
}: {
  label: string;
  value: number;
  share?: number;
  max: number;
  color: string;
  suffix?: string;
}) {
  return (
    <div className="brow">
      <span className="brow__label">{label}</span>
      <span className="brow__track">
        <span
          className="brow__fill"
          style={{ width: `${max ? (value / max) * 100 : 0}%`, background: color }}
        />
      </span>
      <span className="brow__value num">
        {value.toLocaleString()}
        {suffix}
      </span>
      {share !== undefined && (
        <span className="brow__share num">{share.toFixed(1)}%</span>
      )}
    </div>
  );
}
