#!/usr/bin/env python3
"""Generate a realistic, deterministic SOC alert dataset for SAT-SA.

    python scripts/make-soc-dataset.py --out samples/soc-dataset.csv

Why this exists rather than a random generator:

**Every entity's weaknesses are designed, not sampled.** A supervisory tool is only
demonstrable if you know what the right answer is. Each entity is given an explicit
profile -- which rules should fire on it and how many times -- so the resulting schedule
can be checked against intent rather than admired.

**Healthy behaviour is genuinely healthy.** CRITICAL alerts are escalated, notes are
written and varied, closure times are plausible, every expected category is reported.
Without that, EG-002 fires on essentially every record and the tool produces a quarter of
a million findings that mean nothing. Noise is not realism.

**Sectors repeat.** The previous dataset had 12 entities across 12 distinct sectors, so
every peer cohort held exactly one member and NS-001's cohort baseline never ran -- the
rule silently fell back to the global comparison on every entity, and one of the tool's
headline capabilities was invisible in its own demo. Here 40 entities share 8 sectors,
five each, which clears NS-001's five-entity validity gate and exercises the real path.

**Cohort volumes vary realistically.** Healthy entities within a sector get +/-22%
volume jitter. Without it every peer sits within a few percent of the cohort mean, sigma
collapses, and NS-001 flags a 5%-below-average entity as materially under-reporting --
correct arithmetic on unrealistic data. It also exposes something worth knowing: NS-001
has no minimum effect size, so on a genuinely homogeneous cohort it can raise a finding
no supervisor would act on. Adding a floor (for example, also requiring the count to be
below half the cohort mean) is a rule change and therefore a decision for the product
owner, not a generator setting.

**Deterministic.** A fixed anchor and a seeded PRNG. The same command always produces a
byte-identical file, which is what lets it double as a regression fixture.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta

# Never datetime.now(). Findings must be reproducible on any machine on any day.
ANCHOR = datetime(2026, 1, 6, 0, 0, 0)
WINDOW_DAYS = 180

SECTORS = [
    "Power", "Telecom", "Banking", "Transport",
    "Healthcare", "Water", "Defence", "Oil & Gas",
]

# Five entities per sector: NS-001 needs a cohort of at least five before a peer
# comparison is defensible, so this is the smallest arrangement that exercises it.
ENTITIES_PER_SECTOR = 5

NAMES = {
    "Power": ["Northern Grid Operator", "Deccan Power Utility", "Coastal Thermal Corp",
              "Himalaya Hydro Authority", "Western Grid Systems"],
    "Telecom": ["Bharat Telecom Networks", "Meridian Mobile", "Coastal Fibre Ltd",
                "Skyline Communications", "Central Telecom Exchange"],
    "Banking": ["Vantage National Bank", "Union Cooperative Bank", "Meridian Financial",
                "Peninsula Savings", "Capital Clearing House"],
    "Transport": ["Metro Rail Authority", "National Freight Rail", "Harbour Port Trust",
                  "Skyway Airports Ltd", "Interstate Transit Board"],
    "Healthcare": ["Aurora Health Trust", "Civic Hospital Network", "Meridian Diagnostics",
                   "National Blood Services", "Riverside Medical Group"],
    "Water": ["Metropolitan Water Board", "Delta Irrigation Authority", "Coastal Desalination",
              "Highland Reservoir Trust", "Municipal Water Supply"],
    "Defence": ["Defence Logistics Command", "Naval Systems Directorate", "Aerospace Research Wing",
                "Strategic Materials Depot", "Defence Communications Unit"],
    "Oil & Gas": ["Offshore Drilling Consortium", "National Pipeline Grid", "Coastal Refinery",
                  "Gas Distribution Network", "Petrochemical Terminals"],
}

CATEGORIES = [
    "Malware", "Phishing", "Unauthorized Access", "Data Exfiltration",
    "Insider Threat", "Denial of Service", "Vulnerability Exploit", "Policy Violation",
]

# Written by an analyst who actually looked. Varied on purpose: EG-003 detects repetition,
# so healthy notes must not repeat by accident or the rule fires everywhere.
GENUINE_NOTES = [
    "Reviewed proxy logs for the source host; traffic consistent with a scheduled backup job.",
    "Correlated with the change record raised the same morning. Approved maintenance.",
    "Confirmed the binary hash against the allowlist. Signed vendor update.",
    "Contacted the asset owner; user confirmed the login from a new corporate device.",
    "Sandbox detonation returned no malicious behaviour. Sample retained for 30 days.",
    "Traced to a misconfigured monitoring agent. Ticket raised with platform team.",
    "Endpoint isolated and reimaged. Credentials rotated for the affected account.",
    "Firewall rule reviewed; the source range belongs to the partner VPN.",
    "Escalated to tier 2 after confirming lateral movement attempts from the host.",
    "Verified against the threat intel feed. Indicator is a known false positive.",
    "Mailbox rule removed and the user re-enrolled in phishing awareness training.",
    "Patched the affected service and confirmed the exploit path is closed.",
]

# The tell EG-003 exists to catch: the same sentence pasted across unrelated cases.
TEMPLATE_NOTE = "Checked. No further action required."


class Profile:
    """How one entity should behave, and therefore which rules should fire on it."""

    def __init__(self, name, *, volume, eg001=0, eg002=0, eg003=0, eg004=0,
                 eg005=0, blind_spot=False, asset_focus=False):
        self.name = name
        self.volume = volume          # multiplier on the base record count
        self.eg001 = eg001            # rapid closures, unescalated
        self.eg002 = eg002            # CRITICAL with no escalation
        self.eg003 = eg003            # how many templated-note groups
        self.eg004 = eg004            # serious alerts dismissed with no notes
        self.eg005 = eg005            # bulk-closure bursts
        self.blind_spot = blind_spot  # never reports one category the peers do
        self.asset_focus = asset_focus  # repeated alerts against one asset


# The supervisory shape of the dataset: a few entities in real trouble, a long tail of
# minor findings, and two genuinely clean ones. The clean pair is deliberate -- a tool
# that flags every entity it is shown has not demonstrated discrimination, and the "no
# findings" state has to be exercised somewhere.
# One profile per entity, grouped by sector so each peer cohort has real internal
# contrast. This matters more than it looks: NS-001 compares an entity against its own
# cohort, so two under-reporting entities in the SAME sector inflate that cohort's sigma
# and depress its threshold until neither of them trips the rule. They are deliberately
# spread across Telecom, Transport and Water, one per cohort, each a lone outlier.
#
# The shape overall: three entities in real trouble, a long tail of one- and two-finding
# entities, three under-reporters, and two with nothing to find. The clean pair is
# deliberate -- a tool that flags every entity it is shown has demonstrated no
# discrimination, and the "no findings" state has to exist somewhere in the demo.
PROFILES = [
    # --- Power ---------------------------------------------------------------
    Profile("severe", volume=1.15, eg001=9, eg002=7, eg003=3, eg004=6, eg005=2,
            blind_spot=True, asset_focus=True),
    Profile("severe", volume=1.05, eg001=7, eg002=5, eg003=2, eg004=4, eg005=1),
    Profile("high", volume=1.10, eg001=4, eg002=3, eg003=1, eg004=3),
    Profile("moderate", volume=1.00, eg001=2, eg004=1),
    Profile("low", volume=0.95, eg002=1),

    # --- Telecom -------------------------------------------------------------
    Profile("severe", volume=1.05, eg001=6, eg002=6, eg003=2, eg004=5, eg005=1,
            asset_focus=True),
    Profile("high", volume=1.00, eg001=5, eg002=2, eg004=2, eg005=1),
    Profile("moderate", volume=1.05, eg003=1, eg004=2),
    Profile("low", volume=1.00, eg001=1),
    Profile("under-reporting", volume=0.16, eg004=1),

    # --- Banking -------------------------------------------------------------
    Profile("high", volume=0.95, eg001=4, eg004=3, eg005=1, asset_focus=True),
    Profile("moderate", volume=1.00, eg002=2, eg003=1),
    Profile("moderate", volume=0.95, eg001=2, eg002=1),
    Profile("low", volume=1.05, eg004=1),
    Profile("clean", volume=1.00),

    # --- Transport -----------------------------------------------------------
    Profile("high", volume=1.05, eg002=4, eg003=2, eg004=2),
    Profile("moderate", volume=1.00, eg005=1, eg001=1),
    Profile("low", volume=1.00, eg003=1),
    Profile("low", volume=0.95, eg001=1),
    Profile("under-reporting", volume=0.14),

    # --- Healthcare ----------------------------------------------------------
    Profile("high", volume=0.90, eg001=3, eg002=3, eg003=1, blind_spot=True),
    Profile("moderate", volume=1.00, eg002=2, eg004=1),
    Profile("moderate", volume=0.90, eg004=2, blind_spot=True),
    Profile("low", volume=1.00, eg001=1),
    Profile("low", volume=1.05, eg002=1),

    # --- Water ---------------------------------------------------------------
    Profile("moderate", volume=1.10, eg001=2, eg003=1),
    Profile("moderate", volume=1.00, eg004=2),
    Profile("low", volume=1.00, eg002=1),
    Profile("low", volume=0.95, eg004=1),
    Profile("under-reporting", volume=0.18, eg001=1),

    # --- Defence -------------------------------------------------------------
    Profile("moderate", volume=1.00, eg001=1, eg004=1),
    Profile("low", volume=1.00, eg003=1),
    Profile("low", volume=1.05, eg001=1),
    Profile("low", volume=0.95, eg002=1),
    Profile("clean", volume=1.00),

    # --- Oil & Gas -----------------------------------------------------------
    Profile("high", volume=1.00, eg001=4, eg002=2, eg004=2),
    Profile("moderate", volume=1.05, eg002=1, eg003=1),
    Profile("low", volume=1.00, eg004=1),
    Profile("low", volume=0.95, eg001=1),
    Profile("low", volume=1.00, eg002=1),
]


def build(n_records: int, seed_value: int):
    rng = random.Random(seed_value)

    expected = len(SECTORS) * ENTITIES_PER_SECTOR
    if len(PROFILES) != expected:
        # Indexing profiles modulo their length would silently give the last entities a
        # copy of the first ones' weaknesses -- two identical "worst offenders" in the
        # ranking, which reads as a generator bug to anyone who looks.
        raise SystemExit(
            f"PROFILES has {len(PROFILES)} entries but the dataset has {expected} "
            f"entities. Every entity needs its own designed profile."
        )

    entities, plans = [], []
    index = 0
    for sector in SECTORS:
        for slot in range(ENTITIES_PER_SECTOR):
            entity_id = f"CSE-{index + 1:03d}"
            entities.append((entity_id, NAMES[sector][slot], sector))
            plans.append((entity_id, PROFILES[index]))
            index += 1

    total_weight = sum(p.volume for _, p in plans)
    rows = []
    record_no = 0

    for entity_id, profile in plans:
        # Per-entity variance, deterministic from the entity id. Without it the healthy
        # entities in a cohort land within a few percent of each other, cohort sigma
        # collapses, and NS-001's "below mean - 1.5 sigma" test starts flagging entities
        # 5% below average as materially under-reporting. That is the rule behaving
        # correctly on unrealistic data, not a rule defect -- real SOCs vary. See the
        # note in the module docstring about minimum effect size.
        jitter = 1.0 + (rng.random() - 0.5) * 0.45
        target = max(12, int(n_records * profile.volume * jitter / total_weight))
        assets = [f"AST-{entity_id[-3:]}-{i:02d}" for i in range(1, 13)]
        # An entity with a chronic unremediated problem keeps alerting on one asset --
        # illustrative use case (ii), repeated alerts without root-cause remediation.
        hot_asset = assets[0]

        categories = list(CATEGORIES)
        if profile.blind_spot:
            # Never files this category at all. Its peers do, which is the finding.
            categories.remove("Insider Threat")

        planted = []

        def stamp(i: int) -> datetime:
            """Spread over the window, business-hours weighted, fully deterministic."""
            day = (i * 7919) % WINDOW_DAYS
            hour = 8 + ((i * 13) % 11)
            minute = (i * 37) % 60
            return ANCHOR + timedelta(days=day, hours=hour, minutes=minute)

        # --- planted weaknesses --------------------------------------------------
        for k in range(profile.eg001):
            t = stamp(record_no + k)
            planted.append(dict(
                severity="HIGH" if k % 2 else "CRITICAL", category=rng.choice(categories),
                opened=t, closed=t + timedelta(seconds=45 + k),
                escalated=False, disposition="FALSE_POSITIVE",
                notes=rng.choice(GENUINE_NOTES), asset=hot_asset if profile.asset_focus else rng.choice(assets),
            ))
        for k in range(profile.eg002):
            t = stamp(record_no + 100 + k)
            planted.append(dict(
                severity="CRITICAL", category=rng.choice(categories),
                opened=t, closed=t + timedelta(hours=3, minutes=k),
                escalated=False, disposition="TRUE_POSITIVE",
                notes=rng.choice(GENUINE_NOTES), asset=rng.choice(assets),
            ))
        for g in range(profile.eg003):
            # One templated group = four cases sharing a sentence verbatim.
            for k in range(4):
                t = stamp(record_no + 200 + g * 10 + k)
                planted.append(dict(
                    severity=rng.choice(["LOW", "MEDIUM"]), category=rng.choice(categories),
                    opened=t, closed=t + timedelta(minutes=40 + k),
                    escalated=False, disposition="BENIGN",
                    notes=TEMPLATE_NOTE if g == 0 else f"{TEMPLATE_NOTE} Ref {g}.",
                    asset=rng.choice(assets),
                ))
        for k in range(profile.eg004):
            t = stamp(record_no + 300 + k)
            planted.append(dict(
                severity="HIGH" if k % 2 else "CRITICAL", category=rng.choice(categories),
                opened=t, closed=t + timedelta(hours=1, minutes=k),
                escalated=True, disposition="BENIGN" if k % 2 else "FALSE_POSITIVE",
                notes="", asset=rng.choice(assets),
            ))
        for b in range(profile.eg005):
            # Six cases closed inside the same minute: a queue being cleared, not worked.
            burst_close = ANCHOR + timedelta(days=30 + b * 20, hours=17, minutes=58)
            for k in range(6):
                t = burst_close - timedelta(days=2, minutes=k * 11)
                planted.append(dict(
                    severity=rng.choice(["LOW", "MEDIUM"]), category=rng.choice(categories),
                    opened=t, closed=burst_close,
                    escalated=False, disposition="FALSE_POSITIVE",
                    notes=rng.choice(GENUINE_NOTES), asset=rng.choice(assets),
                ))

        # --- ordinary, healthy traffic -------------------------------------------
        filler = max(0, target - len(planted))
        for k in range(filler):
            i = record_no + 1000 + k
            t = stamp(i)
            severity = ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "CRITICAL"][i % 6]
            # Healthy means CRITICAL is escalated. Otherwise EG-002 fires on the whole
            # dataset and the schedule stops distinguishing anything.
            escalated = True if severity == "CRITICAL" else (i % 3 == 0)
            minutes = 25 + (i % 420)
            disposition = ["TRUE_POSITIVE", "FALSE_POSITIVE", "BENIGN"][i % 3]
            planted.append(dict(
                severity=severity, category=categories[i % len(categories)],
                opened=t, closed=t + timedelta(minutes=minutes),
                escalated=escalated, disposition=disposition,
                # A case reference makes each note unique. Twelve stock sentences over
                # 1,200 records would repeat ~100 times each and EG-003 -- which detects
                # exactly that -- would fire on every entity in the dataset. Real
                # investigation notes carry case-specific detail; these have to as well,
                # or the planted repetition is indistinguishable from the background.
                notes=f"{GENUINE_NOTES[i % len(GENUINE_NOTES)]} (case {i:06d})",
                asset=hot_asset if (profile.asset_focus and i % 4 == 0) else assets[i % len(assets)],
            ))

        planted.sort(key=lambda r: r["opened"])
        for r in planted:
            record_no += 1
            rows.append((
                f"ALT-{record_no:07d}", entity_id, r["asset"], r["severity"], r["category"],
                r["opened"].isoformat(), r["closed"].isoformat(),
                "true" if r["escalated"] else "false", r["disposition"], r["notes"],
                f"{(r['closed'] - r['opened']).total_seconds() / 60:.2f}",
            ))

    return entities, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="samples/soc-dataset.csv")
    ap.add_argument("--records", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=20260906)
    args = ap.parse_args()

    entities, rows = build(args.records, args.seed)

    header = ["record_id", "entity_id", "entity_name", "sector", "asset_id", "severity",
              "category", "opened_at", "closed_at", "escalated", "disposition",
              "investigation_notes", "closure_time_minutes"]
    by_id = {e[0]: e for e in entities}
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            eid = r[1]
            w.writerow([r[0], eid, by_id[eid][1], by_id[eid][2], *r[2:]])

    print(f"{args.out}: {len(rows):,} records across {len(entities)} entities "
          f"in {len(SECTORS)} sectors ({ENTITIES_PER_SECTOR} per sector)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
