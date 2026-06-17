# Deploy — Game & What (Retro SD Manager)

Self-hosted. One image = FastAPI backend + the built React SPA (served as static
files). SQLite DB + uploads live on a mounted volume.

## TL;DR

```bash
# build
docker build -t game-and-what:latest .

# run (no keys needed — cover search just limited)
docker run -d --name game-and-what \
  -p 38472:8080 \
  -v "$PWD/data:/app/backend/data" \
  game-and-what:latest
# → http://localhost:38472
```

Or `docker compose up -d` (see `docker-compose.yml`).

## Environment variables

All optional — the app boots without any. Authoritative defaults live in
`backend/app/config.py`. Local dev reads `backend/.env`; in Docker pass them as
container env (compose auto-loads a sibling `.env`). See `.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` | — | IGDB cover search + auto-fill (Twitch dev app) |
| `TGDB_API_KEY` | — | TheGamesDB cover search + auto-fill (free key, **monthly quota**) |
| `STEAMGRIDDB_API_KEY` | — | SteamGridDB cover search (free Bearer token from steamgriddb.com) |
| `GNW_KOREAN_MODE` | `false` | Korea-only features (한글패치/한글명/커버 ko). Public image: off |
| `GNW_CORS_ORIGINS` | `*` | Comma-separated CORS origins (no auth — front with Zero Trust) |
| `GNW_DATA_DIR` | `…/backend/data` | Persistent data root (set to `/app/backend/data` in the image) |
| `GNW_MAX_ROM_BYTES` etc. | see config | Per-type upload size caps |

Host-side (compose only): `GNW_HOST_PORT` (host port → 8080), `GNW_DATA_PATH`
(host volume path), `UID` (build arg — match the host owner of the data dir).

> **Secrets never go in the image.** `.dockerignore` excludes `**/.env` and all of
> `backend/data` (DB, backups, uploads). The published image ships empty; provide
> keys at runtime via env.

## Data & persistence

Everything mutable is under `/app/backend/data` (SQLite `gnw.db`, `library/`
uploads, `tmp/`). Mount it as a volume so it survives restarts/upgrades. The
curated Korean-name dataset is in the source tree (`app/assets/korean_names`),
baked into the image — a data wipe never loses it.

## Configuration — no in-app settings (env only)

There is **no settings screen** in the app. Every option is an **environment
variable** — the standard way to configure a self-hosted container. Set them in
any of three ways:

```bash
# 1) docker run -e
docker run -d -p 38472:8080 -v "$PWD/data:/app/backend/data" \
  -e IGDB_CLIENT_ID=xxx -e IGDB_CLIENT_SECRET=yyy -e TGDB_API_KEY=zzz \
  -e STEAMGRIDDB_API_KEY=sgdb \
  ghcr.io/<owner>/game-and-what:latest
```

```bash
# 2) docker compose — put values in a .env beside docker-compose.yml
#    (compose auto-loads it; copy .env.example), then:
docker compose up -d
```

```bash
# 3) local dev — backend/.env (auto-loaded by config.py), then run uvicorn
```

Keys are read **at startup**, so after changing one, recreate the container
(`docker compose up -d` / re-`docker run`). Nothing is required to boot — with no
keys the app runs and cover search is just limited. Full list: the table above
and `.env.example`.

## Access control — no login, use Zero Trust

The app ships **no authentication**: one shared public workspace, `CORS=*` —
anyone who can reach the port has full access. This is **by design**: access
control is delegated to a **Zero Trust** layer instead of being reinvented inside
the app. **Never bind it directly to a public IP/port.**

**Option A — Cloudflare Tunnel + Access** (public hostname, SSO-gated, no open port):
1. `cloudflared tunnel create gnw` — creates the tunnel + credentials.
2. Ingress rule → the container: `service: http://localhost:38472`.
3. Cloudflare Zero Trust → **Access → Applications** → add the hostname with a
   policy (allow specific emails, Google/GitHub SSO, or one-time PIN). Visitors
   authenticate at Cloudflare's edge **before** any request reaches the app.

**Option B — Tailscale** (private, nothing public):
- Keep the host on your tailnet; reach it at `http://<machine>:38472` over WireGuard.
- Restrict to specific users via tailnet ACLs, or expose one HTTPS hostname with
  `tailscale serve` (tailnet-only). Avoid `tailscale funnel` (public) unless it's
  fronted by auth.

If real per-user accounts are ever needed, add them at this proxy layer — not in
the app.

## Publishing — GHCR via GitHub Actions

Source and image live together on GitHub. The included workflow
(`.github/workflows/docker-publish.yml`) builds a **multi-arch** image
(`linux/amd64, linux/arm64` — so it runs on Pi/ARM SBCs) and pushes to **GHCR**
using the built-in `GITHUB_TOKEN` (no extra secrets). The image name follows the
repo automatically: `ghcr.io/<owner>/<repo>`.

```bash
# cut a release → CI builds & pushes :1.0.0 + :1.0 + :latest
git tag v1.0.0
git push origin v1.0.0
# (or trigger the workflow manually from the Actions tab)
```

After the first push, set the GHCR package **visibility to public** (GitHub →
Packages → the package → settings) so anyone can `docker pull` without auth.

Manual push, if not using CI:
```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u <owner> --password-stdin
docker build -t ghcr.io/<owner>/<repo>:latest .
docker push ghcr.io/<owner>/<repo>:latest
```

> A Docker Hub mirror is optional (same flow with `docker.io/<user>/<repo>`); GHCR
> alone is enough and avoids Docker Hub's anonymous pull-rate limits.
