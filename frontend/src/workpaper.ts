/** The cross-reference system.
 *
 * Every figure on screen carries the reference that resolves to the document
 * proving it, the way an audit file has always worked: an entity is a schedule
 * (WP-01), a rule is a numbered section within it (WP-01.3), and the evidence
 * page repeats that same reference so a reader traces score → finding →
 * records by one number rather than by remembering where they clicked.
 *
 * Section numbers are FIXED per rule rather than assigned by display order, so
 * a reference means the same thing on every entity and never shifts when a
 * finding appears or disappears. Gaps in the sequence are correct and expected:
 * a schedule that has no WP-01.5 simply has no bulk-closure finding.
 */

export const RULE_SECTION: Record<string, number> = {
  "EG-001": 1,
  "EG-002": 2,
  "EG-003": 3,
  "EG-004": 4,
  "EG-005": 5,
  "NS-001": 6,
  "NS-002": 7,
  "ML-001": 8,
};

/** The working paper this run produces. Fixed: the dataset is fixed. */
export const WORKPAPER_ID = "WP-2026-01";

/** CSE-01 → WP-01. Falls back to the raw id if it carries no trailing number. */
export function entityRef(entityId: string): string {
  const match = /(\d+)\s*$/.exec(entityId);
  return match ? `WP-${match[1]}` : `WP-${entityId}`;
}

/** CSE-01 + EG-003 → WP-01.3 */
export function findingRef(entityId: string, ruleId: string): string {
  const section = RULE_SECTION[ruleId];
  return section === undefined
    ? `${entityRef(entityId)}.—`
    : `${entityRef(entityId)}.${section}`;
}
