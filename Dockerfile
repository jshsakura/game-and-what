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


# ── Stage 2: `idlefind` — the GBA prober ─────────────────────────────────────
# Whether a GBA game can run on the real device turns on two numbers its header does
# not carry: where its VBlank idle loop is (gpSP skips nothing without it, and cannot
# find it by itself), and how much work it actually does per frame. Neither can be read
# off the rom — a spin loop and a polling loop look identical in a disassembly — so the
# only way to know is to RUN the game. This builds the tool that does (mGBA headless,
# its idle-loop detector on, plus a per-frame cycle counter). See scripts/idlefind.
#
# mGBA is pinned: the cycle-counter patch is written against this exact tree.
FROM debian:bookworm-slim AS gba-probe-builder

ARG MGBA_COMMIT=5157ce208a5965e8a47bf5b48b5aae5198c22a5e

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates git cmake build-essential libpng-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY scripts/idlefind/ ./idlefind/

RUN git clone https://github.com/mgba-emu/mgba.git && \
    cd mgba && git checkout "${MGBA_COMMIT}" && \
    git apply /build/idlefind/mgba-cycle-counter.patch

RUN cd mgba && mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_QT=OFF -DBUILD_SDL=OFF -DBUILD_GL=OFF -DBUILD_GLES2=OFF -DBUILD_GLES3=OFF \
        -DUSE_FFMPEG=OFF -DUSE_DISCORD_RPC=OFF -DUSE_LIBZIP=OFF -DUSE_SQLITE3=OFF \
        -DUSE_ELF=OFF -DUSE_EDITLINE=OFF -DBUILD_SHARED=OFF -DBUILD_STATIC=ON \
        -DENABLE_SCRIPTING=OFF && \
    make -j"$(nproc)" mgba

# Compile with mGBA's OWN flags. `struct mCore`'s layout depends on them (ENABLE_DEBUGGERS
# alone changes its size by 4 KB), and building against a different set yields a null
# vtable and a segfault on the first call — silently, at run time.
RUN cd mgba/build && \
    grep '^C_DEFINES'  CMakeFiles/mgba.dir/flags.make | sed 's/^C_DEFINES *= *//'  > /tmp/defs.rsp && \
    grep '^C_INCLUDES' CMakeFiles/mgba.dir/flags.make | sed 's/^C_INCLUDES *= *//' > /tmp/incs.rsp && \
    gcc -O2 @/tmp/defs.rsp @/tmp/incs.rsp -o /build/idlefind-bin /build/idlefind/idlefind.c \
        libmgba.a -lz -lpng -lm -lpthread -ldl && \
    /build/idlefind-bin 2>&1 | grep -q usage    # it links and starts


# ── Stage 3: Python backend + built frontend ──────────────────────────────────
FROM python:3.12-slim

# ffmpeg for video encoding; gifsicle for the clock bg.gif lossy shrink pass.
# libpng/zlib are what idlefind links against.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg gifsicle libpng16-16 zlib1g && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend sources.
COPY backend/ ./backend/

# The GBA prober, and the table of everything already measured (services/gba_probe
# looks a rom up there first and only runs the game when it has never seen it).
COPY --from=gba-probe-builder /build/idlefind-bin /usr/local/bin/idlefind
COPY scripts/gba_idle_loop_db.json ./scripts/gba_idle_loop_db.json

# The Korean name dictionary — hash -> name, 1,900-odd of them. A Korean deploy
# (GNW_KOREAN_MODE) seeds an empty database from this at startup, so a fresh install can
# name a rom it has never seen. /app/data is the SHIPPED dataset; /app/backend/data
# (GNW_DATA_DIR, a volume) is the user's library. Different things.
COPY data/names.ko.json ./data/names.ko.json

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
