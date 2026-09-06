/** The score, drawn.
 *
 *  Segment order is fixed — execution gap, negative space, corroboration — and
 *  widths are a share of the attainable maximum rather than of this entity's own
 *  total. That is the whole point: normalising per row would make every bar full
 *  and every entity look identical, where scaling to a common maximum lets forty
 *  rows be compared down the column at a glance.
 *
 *  No hue carries meaning on its own. The legend names each tier, the order never
 *  changes, and the tier table on the entity screen repeats the same figures.
 */

import { TierScore } from "../api";
import { ATTAINABLE_MAX } from "../workpaper";

const SEG: Record<string, string> = {
  EXECUTION_GAP: "eg",
  NEGATIVE_SPACE: "ns",
  ML_CORROBORATION: "ml",
};

const ORDER = ["EXECUTION_GAP", "NEGATIVE_SPACE", "ML_CORROBORATION"];

export default function Composition({
  tiers,
  large = false,
}: {
  tiers: TierScore[];
  large?: boolean;
}) {
  const ordered = ORDER.map((t) => tiers.find((x) => x.tier === t)).filter(
    (t): t is TierScore => Boolean(t) && (t as TierScore).contribution > 0,
  );

  return (
    <span className={`bar${large ? " bar--lg" : ""}`} aria-hidden="true">
      {ordered.map((t) => (
        <span
          key={t.tier}
          className={`bar__seg bar__seg--${SEG[t.tier]}`}
          style={{ width: `${(t.contribution / ATTAINABLE_MAX) * 100}%` }}
        />
      ))}
    </span>
  );
}

/** The key that makes the bar readable. Rendered wherever a bar is. */
export function CompositionLegend({ note }: { note?: string }) {
  return (
    <p className="bar__legend">
      <span>
        <span className="swatch swatch--eg" aria-hidden="true" />
        Execution gap (×0.45)
      </span>
      <span>
        <span className="swatch swatch--ns" aria-hidden="true" />
        Negative space (×0.40)
      </span>
      <span>
        <span className="swatch swatch--ml" aria-hidden="true" />
        ML corroboration (×0.15)
      </span>
      {note && <span>{note}</span>}
    </p>
  );
}
