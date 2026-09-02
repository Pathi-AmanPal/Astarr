# SAT-SA offline deployment image.
#
# One container, one port. The frontend is built here and served by the same FastAPI
# process, so the air-gapped deliverable is a single `docker save` tar with no reverse
# proxy to configure and nothing to fetch at runtime.
#
# Every Python dependency resolves to a prebuilt manylinux wheel on cp314 -- verified
# including numba and llvmlite, which shap pulls and which historically lag new Python
# releases. That is why no compiler toolchain appears anywhere in this file: if a
# source build ever becomes necessary, the honest fix is to pin the Python version
# down, not to bolt gcc onto the runtime image.

# ---------------------------------------------------------------- frontend build
FROM node:24-slim AS frontend
WORKDIR /build

# Lockfile first: this layer is cached unless dependencies actually change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- python deps
FROM python:3.14-slim AS deps
WORKDIR /build

COPY backend/requirements.txt ./
# --only-binary=:all: turns a missing wheel into a hard build failure instead of a
# silent source build that would bloat the image or fail obscurely at import time.
RUN pip install --no-cache-dir --only-binary=:all: \
        --prefix=/install -r requirements.txt

# ---------------------------------------------------------------- runtime
FROM python:3.14-slim AS runtime

# Deterministic behaviour, and the demo's timestamps must not shift with the host TZ:
# EG-005 buckets closures by minute, so a timezone change could alter findings.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC \
    SATSA_DB=/data/sat_sa.duckdb

COPY --from=deps /install /usr/local

WORKDIR /app
COPY backend/ /app/
COPY --from=frontend /build/dist /app/static

# The database is rebuilt from the seed on startup, so it lives on a writable volume
# rather than in the image. Non-root: nothing here needs privileges.
RUN mkdir -p /data \
 && useradd --create-home --uid 10001 satsa \
 && chown -R satsa:satsa /app /data
USER satsa
VOLUME ["/data"]

EXPOSE 8000

# No shell form: signals reach uvicorn directly so Ctrl-C and `docker stop` are clean.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
