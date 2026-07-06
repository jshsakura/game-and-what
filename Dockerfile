# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

# Install deps first (better layer caching).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy sources and build.
COPY frontend/ ./
RUN npm run build
# Output is at /build/frontend/dist


# ── Stage 2: Python backend + built frontend ──────────────────────────────────
FROM python:3.12-slim

# ffmpeg for video encoding; gifsicle for the clock bg.gif lossy shrink pass.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg gifsicle && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend sources.
COPY backend/ ./backend/

# Copy the built frontend into the location the app checks at startup.
COPY --from=frontend-builder /build/frontend/dist /app/frontend_dist

# Persistent data lives on a volume (gnw.db + uploaded files).
# We create the directory so the mount point exists even without a volume.
RUN mkdir -p /app/backend/data

# Run as non-root. The UID is a build arg so it can match the host user that
# owns the bind-mounted data dir (default 1001 = this host's `ubuntu` user),
# avoiding permission errors on /app/backend/data. Override: --build-arg UID=...
ARG UID=1001
RUN useradd -m -u ${UID} gnw && chown -R gnw:gnw /app
USER gnw

EXPOSE 8080

# Run from the project root so relative imports resolve correctly.
CMD ["python3", "-m", "uvicorn", "backend.app.main:app", \
     "--host", "0.0.0.0", "--port", "8080"]
