# syntax=docker/dockerfile:1
# SIH26184 - Cybercrime Intelligence Platform - API/worker image
#
# Single image is used for the API, the Celery worker and the Celery beat
# process; the entrypoint differs per container (`make api`, `make worker`,
# `make beat`, `make seed`).
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/cybercrime

# OS-level deps required by the geospatial stack (Shapely/GEOS at runtime).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev libgeos-dev gdal-bin \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY README.md ./
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --upgrade pip \
    && pip install --no-cache-dir "setuptools>=68" wheel \
    && pip install --no-cache-dir .

EXPOSE 8000

# Run the FastAPI app via uvicorn by default.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]