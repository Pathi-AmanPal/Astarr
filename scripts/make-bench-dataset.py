"""Deterministic SOC-shaped dataset generator for scale testing."""
import sys, os
from datetime import datetime, timedelta

n_records = int(sys.argv[1]); n_entities = int(sys.argv[2]); out = sys.argv[3]
ANCHOR = datetime(2026, 1, 1, 0, 0, 0)
SEV = ["LOW","MEDIUM","HIGH","CRITICAL"]
CAT = ["Malware","Phishing","Unauthorized Access","Data Exfiltration","Insider Threat","DDoS"]
DISP = ["TRUE_POSITIVE","FALSE_POSITIVE","BENIGN"]

with open(out, "w", encoding="utf-8", newline="") as f:
    f.write("record_id,entity_id,entity_name,sector,asset_id,severity,category,opened_at,closed_at,escalated,disposition,investigation_notes,closure_time_minutes\n")
    for i in range(n_records):
        e = i % n_entities
        eid = f"CSE-{e:03d}"
        opened = ANCHOR + timedelta(minutes=(i * 7) % 525600)
        sev = SEV[(i * 3) % 4]
        # ~4% planted rapid closures on HIGH/CRITICAL, unescalated -> EG-001 population
        rapid = (i % 25 == 0) and sev in ("HIGH","CRITICAL")
        mins = 1.0 if rapid else float(30 + (i % 300))
        closed = opened + timedelta(minutes=mins)
        esc = "false" if rapid else ("true" if i % 3 == 0 else "false")
        disp = DISP[(i * 5) % 3]
        notes = "" if i % 11 == 0 else f"Triaged under runbook {(i % 40):02d}."
        f.write(f"ALT-{i:08d},{eid},Entity {e:03d},Sector-{e % 12},AST-{(i % 500):04d},{sev},{CAT[(i*2)%6]},"
                f"{opened.isoformat()},{closed.isoformat()},{esc},{disp},{notes},{mins}\n")
print(f"{out}: {n_records} records, {n_entities} entities, {os.path.getsize(out)/1048576:.1f} MiB")
