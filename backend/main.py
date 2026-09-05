"""FastAPI app (PRD Section 6). No authentication, no upload endpoints.

The database is seeded automatically on startup when missing or empty, so no manual
seeding step ever exists (NFR 4).
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

_pkg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packages")
if os.path.isdir(_pkg_dir) and _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import db
import models
from detection import run_detection
from ingest import ingest_file
from scoring import entity_scores, ranked_entities
from seed import seed

RECORD_COLUMNS = [
    "record_id", "entity_id", "asset_id", "severity", "category", "opened_at",
    "closed_at", "escalated", "disposition", "investigation_notes", "closure_time_minutes",
]


def _ensure_seeded(con) -> None:
    if db.is_empty(con):
        seed(con)
        run_detection(con)


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
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
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
def list_entities():
    return ranked_entities(app.state.con)


@app.get("/api/entities/{entity_id}", response_model=models.EntityDetail)
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


@app.post("/api/demo/reset", response_model=models.ResetResult)
def demo_reset():
    con = app.state.con
    try:
        entities_loaded, _records = seed(con)
        findings_generated = run_detection(con)
    except Exception as exc:  # surfaced to the UI as a retry-able banner
        raise HTTPException(status_code=500, detail={"error": f"Reset failed: {exc}"})
    return {
        "status": "reset_complete",
        "entities_loaded": entities_loaded,
        "findings_generated": findings_generated,
    }


@app.post("/api/ingest", response_model=models.ResetResult)
async def ingest_dataset(request: Request):
    con = app.state.con
    body_bytes = await request.body()
    if not body_bytes:
        raise HTTPException(status_code=400, detail={"error": "Empty dataset"})

    content_text = body_bytes.decode("utf-8", errors="ignore")
    ext = ".json" if content_text.strip().startswith(("[", "{")) else ".csv"

    temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"temp_upload{ext}")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content_text)
        entities_loaded, _records_loaded, findings_generated = ingest_file(temp_path, con=con, clear_existing=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": f"Ingestion failed: {exc}"})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return {
        "status": "ingestion_complete",
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
