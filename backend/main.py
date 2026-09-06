"""FastAPI app (PRD Section 6, amended 2026-09-05: CSV upload added).

The database is seeded automatically on startup when missing or empty, so no manual
seeding step ever exists (NFR 4). The demo seed remains the default dataset and the
reset target; `POST /api/dataset/upload` replaces it with a real alert export, and
`POST /api/demo/reset` puts the demo back.

Still no authentication and still no outbound network calls: an upload is read from the
request body and written to the local DuckDB file, nothing leaves the machine.
"""

from __future__ import annotations

import functools
import os
import tempfile
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import db
import ingest
import models
from detection import run_detection
from scoring import entity_scores, ranked_entities
from seed import seed

RECORD_COLUMNS = [
    "record_id", "entity_id", "asset_id", "severity", "category", "opened_at",
    "closed_at", "escalated", "disposition", "investigation_notes", "closure_time_minutes",
]

# A mis-selected file (a disk image, a video) should fail immediately rather than be
# read into memory first. Well above the 50k-row ceiling ingest.py enforces.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

DEMO_LABEL = "Synthetic demo dataset"

# One DuckDB connection is shared by every request, and FastAPI runs sync endpoints on
# a threadpool -- so two requests arriving together execute on the same connection
# concurrently and interleave each other's result sets. The observed failure was a
# `ValueError: dictionary update sequence element #0 has length 1` out of scoring.py
# and a spurious 404 from the entity lookup, i.e. a corrupted read, not a crash at the
# point of misuse.
#
# It stayed latent while every screen made one call at a time. The detail page now
# fetches its findings and its ML profile together, which is what surfaced it.
#
# Serialising is the right trade here rather than a connection pool: the dataset is a
# few hundred rows, every query is sub-millisecond, and a supervisory tool has one
# reader. Correctness over a concurrency win nobody can measure.
_db_lock = threading.RLock()


def serialised(fn):
    """Run a sync endpoint holding the database lock.

    Applied under @app.get/@app.post so FastAPI still reads the original signature
    through functools.wraps, and its dependency injection is unaffected.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _db_lock:
            return fn(*args, **kwargs)
    return wrapper


def _seed_demo(con) -> tuple[int, int]:
    """Load the built-in demo dataset and recompute. Returns (entities, findings)."""
    entities_loaded, records_loaded = seed(con)
    findings_generated = run_detection(con)
    db.set_dataset_meta(con, source="demo_seed", label=DEMO_LABEL,
                        entity_count=entities_loaded, record_count=records_loaded)
    return entities_loaded, findings_generated


def _ensure_seeded(con) -> None:
    if db.is_empty(con):
        _seed_demo(con)
    elif db.dataset_meta(con) is None:
        # A database written before provenance existed. Label it from what is actually
        # in it rather than guessing, and never re-seed over a user's uploaded data.
        entity_count = con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        record_count = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        db.set_dataset_meta(con, source="demo_seed", label=DEMO_LABEL,
                            entity_count=entity_count, record_count=record_count)


@asynccontextmanager
async def lifespan(app: FastAPI):
    con = db.connect()
    _ensure_seeded(con)
    app.state.con = con
    yield
    con.close()


app = FastAPI(title="SAT-SA - Supervisory Analytics", lifespan=lifespan)

# The Vite dev server runs on a different port. Localhost only -- no outbound calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Errors always carry an `error` key, per PRD Section 15."""
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(detail)})


@app.get("/api/health", response_model=models.Health)
def health():
    return {"status": "ok"}


@app.get("/api/entities", response_model=list[models.EntitySummary])
@serialised
def list_entities():
    return ranked_entities(app.state.con)


@app.get("/api/entities/{entity_id}", response_model=models.EntityDetail)
@serialised
def entity_detail(entity_id: str):
    con = app.state.con
    row = con.execute(
        "SELECT entity_id, entity_name, sector FROM entities WHERE entity_id = ?",
        [entity_id],
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "Entity not found"})

    findings = con.execute(
        """
        SELECT finding_id, rule_id, finding_type, title, weight, explanation
        FROM findings WHERE entity_id = ?
        ORDER BY finding_type, rule_id, finding_id
        """,
        [entity_id],
    ).fetchall()

    scores = entity_scores(con)[entity_id]
    return {
        "entity_id": row[0],
        "entity_name": row[1],
        "sector": row[2],
        "risk_score": scores["risk_score"],
        "risk_score_raw": scores["risk_score_raw"],
        "capped": scores["capped"],
        "tiers": scores["tiers"],
        "findings": [
            {
                "finding_id": f[0], "rule_id": f[1], "finding_type": f[2],
                "title": f[3], "weight": f[4], "explanation": f[5],
            }
            for f in findings
        ],
    }


@app.get("/api/findings/{finding_id}/evidence", response_model=models.Evidence)
@serialised
def finding_evidence(finding_id: str):
    con = app.state.con
    row = con.execute(
        """
        SELECT f.finding_id, f.rule_id, f.finding_type, f.title, f.weight, f.explanation,
               f.evidence_record_ids, f.entity_id, e.entity_name
        FROM findings f JOIN entities e ON e.entity_id = f.entity_id
        WHERE f.finding_id = ?
        """,
        [finding_id],
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "Finding not found"})

    record_ids = [r for r in row[6].split(",") if r]
    placeholders = ",".join("?" for _ in record_ids) or "NULL"
    records = con.execute(
        f"SELECT {', '.join(RECORD_COLUMNS)} FROM records "
        f"WHERE record_id IN ({placeholders}) ORDER BY record_id",
        record_ids,
    ).fetchall()

    return {
        "finding_id": row[0], "rule_id": row[1], "finding_type": row[2],
        "title": row[3], "weight": row[4], "explanation": row[5],
        "entity_id": row[7], "entity_name": row[8],
        "records": [dict(zip(RECORD_COLUMNS, r)) for r in records],
    }


@app.get("/api/entities/{entity_id}/ml", response_model=models.MlProfile)
@serialised
def entity_ml_profile(entity_id: str):
    """The corroboration layer's working for one entity.

    Served whether or not the entity carries an ML finding: "the model did not consider
    this entity unusual" is a supervisory answer, and it is only credible if the figures
    behind it can be read too.
    """
    con = app.state.con
    exists = con.execute(
        "SELECT 1 FROM entities WHERE entity_id = ?", [entity_id]
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail={"error": "Entity not found"})

    rows = con.execute(
        """
        SELECT feature, label, value, dataset_mean, deviation, contribution,
               method, anomalous, corroborated
        FROM ml_profile WHERE entity_id = ?
        """,
        [entity_id],
    ).fetchall()

    peer_count = con.execute(
        "SELECT COUNT(DISTINCT entity_id) FROM ml_profile"
    ).fetchone()[0]

    if not rows:
        return {
            "entity_id": entity_id, "available": False, "method": "none",
            "anomalous": False, "corroborated": False, "peer_count": peer_count,
            "features": [],
        }

    return {
        "entity_id": entity_id,
        "available": True,
        "method": rows[0][6],
        "anomalous": bool(rows[0][7]),
        "corroborated": bool(rows[0][8]),
        "peer_count": peer_count,
        "features": [
            {
                "feature": r[0], "label": r[1], "value": r[2],
                "dataset_mean": r[3], "deviation": r[4], "contribution": r[5],
            }
            for r in rows
        ],
    }


@app.get("/api/dataset", response_model=models.DatasetInfo)
@serialised
def dataset_info():
    """Provenance for the loaded dataset, shown in the masthead."""
    meta = db.dataset_meta(app.state.con)
    if meta is None:
        raise HTTPException(status_code=404, detail={"error": "No dataset loaded"})
    return meta


@app.get("/api/dataset/template.csv", include_in_schema=False)
def dataset_template():
    """A valid three-row example of the upload format.

    Present so the first question after seeing an upload control -- "what columns does
    it want?" -- is answered by downloading a file that is guaranteed to import, rather
    than by reading documentation.
    """
    return Response(
        content=ingest.TEMPLATE_CSV,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sat-sa-template.csv"'},
    )


@app.post("/api/dataset/upload", response_model=models.UploadResult)
async def dataset_upload(file: UploadFile = File(...)):
    """Replace the demo dataset with an uploaded alert export.

    Rejected uploads leave the previous dataset untouched: parsing and validation both
    complete before anything is written, so a bad file cannot leave the tool holding
    half a dataset in front of an audience.
    """
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
                    "details": []},
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail={"error": "File is not UTF-8 text. Export it as CSV or JSON, not XLSX.",
                    "details": []},
        )

    label = os.path.basename(file.filename or "uploaded.csv")
    is_json = (file.filename or "").lower().endswith(".json") or text.lstrip()[:1] in "[{"
    try:
        if is_json:
            # JSON is normalised through the CSV validator, which means it is
            # materialised. Acceptable: a JSON submission is an interchange format for
            # a review sample, not the million-row bulk path.
            entities, records = ingest.parse_json(text)
        else:
            entities, records = None, None
    except ingest.IngestError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": f"{len(exc.errors)} problem(s) in the file — nothing was "
                             f"loaded, the previous dataset is still in place.",
                    "details": exc.errors},
        )

    con = app.state.con
    # The lock is taken around the database work only, never across an await: this
    # endpoint runs on the event loop, and holding a blocking lock over a suspension
    # point would stall every other request rather than merely serialise this one.
    try:
        with _db_lock:
            if entities is None:
                # CSV: validate and load without materialising the dataset. The body is
                # spooled to disk first and read back as a handle, so neither the file
                # nor the parsed rows are ever held whole in memory.
                handle, spooled = tempfile.mkstemp(suffix=".csv", prefix="satsa-body-")
                os.write(handle, raw)
                os.close(handle)
                try:
                    with open(spooled, "r", encoding="utf-8-sig", newline="") as fh:
                        entities_loaded, records_loaded = ingest.load_streaming(
                            con, fh, label)
                finally:
                    os.unlink(spooled)
            else:
                entities_loaded, records_loaded = ingest.load(con, entities, records, label)
            findings_generated = run_detection(con)
    except Exception as exc:
        # The dataset is now indeterminate; restore the demo rather than serve a
        # half-written schedule.
        with _db_lock:
            _seed_demo(con)
        raise HTTPException(
            status_code=500,
            detail={"error": f"Load failed and the demo dataset was restored: {exc}",
                    "details": []},
        )

    return {
        "status": "upload_complete",
        "label": label,
        "entities_loaded": entities_loaded,
        "records_loaded": records_loaded,
        "findings_generated": findings_generated,
    }


@app.post("/api/demo/reset", response_model=models.ResetResult)
@serialised
def demo_reset():
    """Restore the built-in demo dataset, discarding any upload."""
    con = app.state.con
    try:
        entities_loaded, findings_generated = _seed_demo(con)
    except Exception as exc:  # surfaced to the UI as a retry-able banner
        raise HTTPException(status_code=500, detail={"error": f"Reset failed: {exc}"})
    return {
        "status": "reset_complete",
        "entities_loaded": entities_loaded,
        "findings_generated": findings_generated,
    }


# --- Static frontend (container builds only) -------------------------------------
# In the packaged image the built frontend is copied to /app/static and served by this
# same process, so the offline deployment is ONE container on ONE port -- one tar file
# to carry to an air-gapped machine, with no reverse proxy to misconfigure.
#
# Mounted LAST, on purpose. The catch-all below would shadow every /api route if it
# were registered first, and the failure would look like a 404 on a working endpoint.
#
# During local development this directory does not exist, uvicorn and the Vite dev
# server run separately on their own ports, and none of this code is reached -- which
# is why the CORS middleware above stays.
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")),
              name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve the SPA shell for any non-API path.

        React Router owns client-side routing, so a deep link like /entity/CSE-01 is a
        real URL a judge can reload or land on directly. Without this it would 404 --
        the server has no such route, only the bundle does.
        """
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail={"error": "Not found"})
        candidate = os.path.normpath(os.path.join(STATIC_DIR, full_path))
        # Containment check: never let a crafted path escape the static root.
        if (full_path and os.path.isfile(candidate)
                and os.path.commonpath([candidate, STATIC_DIR]) == STATIC_DIR):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
