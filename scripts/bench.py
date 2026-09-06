"""Measure ingest + detection + scoring at one dataset size. Run as a subprocess
so peak RSS is attributable to this run alone."""
import os, resource, sys, tempfile, time
import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "backend"))
import db, ingest
ingest.MAX_ROWS = 10_000_000
from detection import run_detection
from scoring import ranked_entities

path = sys.argv[1]
def peak(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

t0 = time.perf_counter()
text = open(path, "r", encoding="utf-8-sig").read()
t_read = time.perf_counter() - t0

t0 = time.perf_counter()
entities, records = ingest.parse(text, path)
t_parse = time.perf_counter() - t0
rss_parse = peak()
del text

con = db.connect(os.path.join(tempfile.mkdtemp(), "bench.duckdb"))
t0 = time.perf_counter()
ingest.load(con, entities, records, os.path.basename(path))
t_load = time.perf_counter() - t0
del entities, records

t0 = time.perf_counter()
findings = run_detection(con)
t_detect = time.perf_counter() - t0
rss_detect = peak()

t0 = time.perf_counter()
ranked = ranked_entities(con)
t_score = time.perf_counter() - t0

n = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
print(f"{n}\t{len(ranked)}\t{findings}\t{t_read:.2f}\t{t_parse:.2f}\t{t_load:.2f}"
      f"\t{t_detect:.2f}\t{t_score:.2f}\t{rss_parse:.0f}\t{rss_detect:.0f}\t{peak():.0f}")
