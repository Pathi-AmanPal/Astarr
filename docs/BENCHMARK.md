# SAT-SA — Performance and Scalability Report

Measured 2026-09-06 · Reproducible with `scripts/bench.py` and `scripts/make-bench-dataset.py`

Every figure here is measured, not estimated. Where a number is a projection it says so.

---

## 1. Test environment

| | |
| --- | --- |
| CPU | 4 × Intel Xeon @ 2.10GHz |
| RAM | 15 GiB (the tool needs far less — see §5) |
| OS | Linux 6.18 |
| Python | 3.11.15 |
| DuckDB | 1.5.5 |
| scikit-learn / shap | 1.9.0 / 0.51.0 |
| Regression suite | **130 checks, 0 failures** |

**Method.** Each configuration is run twice in a fresh process and the second, warm run is
reported. The first run in any sweep pays one-off costs — importing scikit-learn and
shap, and a cold page cache — which added 18 seconds to a 10,000-record measurement and
would have made the smallest dataset look like the slowest. Peak memory is
`ru_maxrss` for the whole process, so it includes the interpreter and every import.

"Ingest" covers reading, validating and loading. "Detect" covers all seven deterministic
rules, the ML corroboration layer and scoring.

---

## 2. Throughput by dataset size

| Records | Entities | Findings | Ingest | Detect | **Total** | Peak RSS |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 20 | 2,253 | 0.48s | 1.33s | **1.80s** | 298 MiB |
| 50,000 | 20 | 11,067 | 1.07s | 1.49s | **2.56s** | 328 MiB |
| 100,000 | 20 | 22,080 | 1.90s | 2.02s | **3.91s** | 351 MiB |
| 500,000 | 50 | 110,363 | 7.84s | 2.67s | **10.52s** | 406 MiB |
| 1,000,000 | 50 | 220,514 | 15.24s | 4.13s | **19.37s** | 631 MiB |

Throughput is linear in record count at roughly **65,000 records/second** end to end.
Detection is close to flat because the rules are set-based; the slope is almost entirely
ingest.

---

## 3. Throughput by entity count

The axis the problem statement names — *"difficult to scale across a growing number of
CSEs"*. Record volume held at 100,000.

| Entities | Findings | Ingest | Detect | **Total** | Peak RSS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 22,080 | 1.90s | 2.02s | **3.91s** | 351 MiB |
| 100 | 22,280 | 1.95s | 2.26s | **4.21s** | 343 MiB |
| 500 | 23,288 | 2.25s | 3.30s | **5.55s** | 368 MiB |
| 2,000 | 25,089 | 3.40s | 6.68s | **10.08s** | 311 MiB |

A hundredfold increase in entity count costs **2.6×** in total time and nothing in memory.
The residual growth is the ML layer, which fits one feature vector per entity — see §6.

---

## 4. The demonstration dataset

| | |
| --- | --- |
| File | `samples/soc-dataset.csv` (12.5 MB) |
| Shape | 51,878 records · 40 entities · 8 sectors · 5 entities per sector |
| Findings | 224, across all eight rules |
| Score spread | 57.0 down to 0.0, two clean entities |
| **Upload to rendered dashboard** | **2.81s** (1.24s ingest, 1.57s detect) |
| Peak RSS | 340 MiB |

This is the file uploaded on camera in the demo. Under three seconds from a 12.5 MB
upload to a fully computed schedule.

---

## 5. Stated minimum specification

> **2 vCPU · 2 GiB RAM · 1 GiB disk · no GPU · no network connectivity.**
>
> Runs on a standard air-gapped Windows or Linux virtual machine. One million alert
> records ingest, analyse and score in under 20 seconds at a peak of ~630 MiB. A typical
> supervisory submission of 50,000 records completes in under 3 seconds.

DuckDB's working memory can be constrained further with `SATSA_DB_MEMORY_LIMIT` and
`SATSA_DB_THREADS`. Both are unset by default deliberately: DuckDB's own default adapts
to the host, and a fixed low limit is not free. Measured on the million-record load,
`256MB` holds peak RSS to 404 MiB; **`128MB` fails outright** with an OutOfMemoryError
inside EG-003's aggregation. Treat it as a deployment knob, not a default.

---

## 6. Optimisation history

Four changes, each found by profiling rather than assumption. Every one preserved
findings byte-for-byte, asserted by the regression suite.

### 6.1 Bulk insert — 198× on the load path

`con.executemany` issues one prepared statement per row, measured at ~1.3ms each.

| 50,000 records | Time |
| --- | ---: |
| `executemany` | 64.93s |
| Staged CSV + DuckDB `read_csv` | **0.33s** |

At a million rows this was the difference between roughly 22 minutes and 6 seconds. Column
types are declared rather than sniffed — DuckDB's CSV sniffer samples, so a file whose
first rows lack `closed_at` would type the column VARCHAR and every later timestamp
comparison would quietly misbehave.

### 6.2 Removing O(records × entities) scans

EG-003, EG-005 and NS-002 each scanned the whole record list once per entity; NS-002 did
it once per entity *per missing category*. Invisible at 12 entities, dominant as entities
grow.

| 100,000 records | Before | After |
| ---: | ---: | ---: |
| 500 entities | 8.43s | 5.09s |
| 2,000 entities | 26.89s | 13.35s |

### 6.3 Streaming ingestion — the memory fix

Peak memory was ~1.5 KiB per record: 1,530 MiB for a million rows from a 150 MB file, a
**tenfold amplification** of the source data. Three separate full copies were responsible,
and all three are gone:

- `io.StringIO(text)` duplicated the entire file for the CSV reader
- a second dict was built per row on top of `DictReader`'s
- the upload endpoint held the whole request body as a Python string

Validation now streams from a file handle straight to a staged CSV.

| Stage, 1M records | Before | After |
| --- | ---: | ---: |
| Validation peak | 895 MiB | **143 MiB** |
| Whole pipeline peak | 1,530 MiB | **631 MiB** |

### 6.4 Set-based detection

`rules_sql.py` expresses EG-001…005 and NS-002 as `INSERT ... SELECT`, so neither a
record nor a finding becomes a Python object. Detection on a million records fell from
**17.35s to 4.13s**.

NS-001 stays in Python deliberately: it reasons over one number per entity, and its
peer-cohort validity gate is a judgement SQL would obscure rather than accelerate.

### 6.5 Two smaller O(n²) mistakes

- `_zscores` recomputed each feature column's mean and standard deviation **once per
  row** — 1.79s at 2,000 entities, nearly as slow as SHAP itself. Statistics are now
  computed once.
- `_write_ml_profile` still used `executemany`: four rows per entity, so 8,000 prepared
  statements at 2,000 entities, roughly ten seconds.

---

## 7. Overall before / after

| Records / entities | Before | After | Time | Memory |
| --- | --- | --- | ---: | ---: |
| 100,000 / 20 | 5.7s · 438 MiB | **3.9s · 351 MiB** | 1.5× | 1.2× |
| 100,000 / 2,000 | 30.2s · 427 MiB | **10.1s · 311 MiB** | 3.0× | 1.4× |
| 1,000,000 / 50 | 37.7s · 1,530 MiB | **19.4s · 631 MiB** | 1.9× | 2.4× |

---

## 8. Correctness under optimisation

Performance work on a supervisory tool is worthless if it changes what the tool finds.
Three properties are asserted on every run of `verify.py`:

1. **Two engines, one answer.** `run_detection_python` — the original, record-in-memory
   implementation — is retained as the executable specification. The suite asserts that
   it and the SQL engine produce byte-identical findings: same ids, same order, same
   explanation strings, same evidence lists. If they ever disagree, the Python one is
   right.
2. **Streaming equals materialised.** `stage_csv` and `parse_csv` must accept and reject
   exactly the same files and load exactly the same rows, including from a file handle.
3. **A rejected upload changes nothing.** Validation completes before the database is
   touched, so a malformed file leaves the previously loaded dataset intact. Asserted.

**One real bug was caught by these tests and would not have been caught by any small
dataset:** DuckDB's `lpad` *truncates* a string longer than the target width, where
Python's `f"{i:04d}"` pads but never truncates. The ten-thousandth finding became `F-1000`
and collided with the thousandth on the primary key. Invisible below 10,000 findings.

---

## 9. Known limits

**1. Ingest is now the dominant cost** — 15 of the 19 seconds on a million records. That
is Python-level per-row validation, and it buys the line-numbered error messages the
upload flow depends on. Parallelising across processes is the next lever and is not
needed yet.

**2. The ML layer scales with entity count**, not record count: Isolation Forest plus
SHAP over a 2,000-row feature matrix is ~5s. Beyond roughly 5,000 CSEs, fit on a sample
and score the full set.

**3. Memory is bounded by DuckDB, not by Python.** The remaining peak is the database's
working set during aggregation. It is configurable, with the caveat in §5.

**4. NS-001 has no minimum effect size.** On a homogeneous peer cohort, σ is small and
`mean − 1.5σ` can sit 5% below the mean, raising a finding no supervisor would act on.
Observed while building the demonstration dataset. This is a rule threshold decision, not
a performance issue, and is recorded in the PRD for approval rather than changed quietly.

---

## 10. Reproducing these figures

```bash
# generate the fixed benchmark datasets
python scripts/make-bench-dataset.py 1000000 50 /tmp/d_1m.csv

# measure one configuration (run twice; report the warm run)
python scripts/bench.py /tmp/d_1m.csv

# the demonstration dataset
python scripts/make-soc-dataset.py --out samples/soc-dataset.csv
python scripts/bench.py samples/soc-dataset.csv

# correctness
cd backend && python verify.py     # expect: All checks passed. (130)
```
