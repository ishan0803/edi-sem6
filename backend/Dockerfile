# ══════════════════════════════════════════════════════════════════════════════
# Backend Dockerfile — Optimized for fast rebuilds
# ══════════════════════════════════════════════════════════════════════════════
# Layer strategy (bottom = changes least, top = changes most):
#   1. System deps (apt)          — almost never changes
#   2. ML deps (torch, spacy)     — changes rarely         (~1 GB CPU-only)
#   3. Geo deps (osmnx, ortools)  — changes rarely         (~200 MB)
#   4. Base deps (fastapi, etc)   — changes occasionally   (~50 MB)
#   5. App code (*.py)            — changes every build    (~100 KB)
#
# Typical code-change rebuild: < 5 seconds (only layer 5 rebuilds).
# ══════════════════════════════════════════════════════════════════════════════

FROM python:3.11-slim AS base

# ── Layer 1: System dependencies ─────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip

# ── Layer 2: ML dependencies (heaviest, changes least) ──────────────────────
# CPU-only PyTorch = ~200 MB instead of ~2.5 GB with CUDA
COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt \
    && python -m spacy download en_core_web_sm

# ── Layer 3: Geo/spatial dependencies ────────────────────────────────────────
COPY requirements-geo.txt .
RUN pip install --no-cache-dir -r requirements-geo.txt

# ── Layer 4: Base dependencies (lightest pip layer) ──────────────────────────
COPY requirements-base.txt .
RUN pip install --no-cache-dir -r requirements-base.txt

# ── Layer 5: Application code (changes most frequently) ─────────────────────
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
