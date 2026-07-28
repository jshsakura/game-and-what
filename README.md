<div align="center">

# 🎮 Game & What — Retro SD Manager

**A self-hosted web app that turns a pile of ROMs into a ready-to-flash Game & Watch SD card.**

**English** · [한국어](README.ko.md)

[![Live demo](https://img.shields.io/badge/▶_live-demo-4c9a2a?style=flat-square)](https://jshsakura.github.io/game-and-what/)
[![Docker image](https://img.shields.io/badge/ghcr.io-game--and--what-2496ED?style=flat-square&logo=docker&logoColor=white)](https://github.com/jshsakura/game-and-what/pkgs/container/game-and-what)
[![Build](https://img.shields.io/github/actions/workflow/status/jshsakura/game-and-what/docker-publish.yml?style=flat-square&label=image%20build)](https://github.com/jshsakura/game-and-what/actions/workflows/docker-publish.yml)
[![Version](https://img.shields.io/github/v/tag/jshsakura/game-and-what?style=flat-square&label=version)](https://github.com/jshsakura/game-and-what/tags)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
![Arch](https://img.shields.io/badge/arch-amd64_·_arm64-555?style=flat-square)

![Game & What preview](docs/preview.png)

</div>

Drop in ROMs, videos and music — Game & What auto-fetches names and device-spec
covers, then packs everything into a **single ZIP that matches the retro-go SD
card layout**. Extract it onto your card and you're done.

> Targets the [retro-go-sd](https://github.com/sylverb/game-and-watch-retro-go-sd)
> firmware for the Game & Watch handheld. The name "Game & What" is a play on
> words — this project ships **no ROMs, BIOS or copyrighted assets**
> (see [Disclaimer](#-disclaimer)).

**▶︎ [Try the live demo](https://jshsakura.github.io/game-and-what/)** — a static
preview with sample data (no backend; uploads/edits are disabled).

---

## 📑 Contents

- [What it does](#-what-it-does)
- [How it works](#-how-it-works) — the end-to-end flow
- [Getting started](#-getting-started) — **step-by-step install**
  - [1. Prerequisites](#1-prerequisites)
  - [2. Run it](#2-run-it-docker)
  - [3. First use — from ROM to SD card](#3-first-use--from-rom-to-sd-card)
  - [4. Updating to a new version](#4-updating-to-a-new-version)
  - [Platform notes](#platform-notes-nas--raspberry-pi--windows)
- [BIOS / system ROMs](#-bios--system-roms)
- [Homebrew — required files](#-homebrew--required-files)
- [Configuration](#️-configuration)
- [Security — no built-in login](#-security--no-built-in-login)
- [FAQ & troubleshooting](#-faq--troubleshooting)
- [Develop from source](#️-develop-from-source)
- [Tech stack](#-tech-stack) · [Credits](#-credits) · [Disclaimer](#-disclaimer) · [License](#-license)

---

## ✨ What it does

- **ROM → cover.** Upload a ROM for any supported system; a cover is auto-fetched
  (IGDB → TheGamesDB → SteamGridDB → libretro-thumbnails), rendered to the device
  spec (**186×100 `.img`**, aspect-preserved), and filed as `/covers/<sys>/Name.img`
  beside `/roms/<sys>/Name.<ext>`. Search/upload/crop covers manually too.
- **One-click SD ZIP.** Download the whole card (`/roms`, `/covers`, `/cores`, BIOS)
  in the exact firmware layout — extract to the SD root, done.
- **Play in browser.** Experimental in-page emulation (Nostalgist.js) for systems
  that have a WASM core — test a ROM before you flash it.
- **Curate a bloated set.** Each ROM shows its **IGDB rating** (0–100, color-tiered
  badge on the cover) so you can judge quality at a glance, and a per-ROM
  **"Exclude from SD"** toggle drops a ROM from the SD download while keeping it in
  the library — slim the device menu without deleting anything.
- **All 19 officially supported systems** — everything the latest upstream
  [sylverb firmware](https://github.com/sylverb/game-and-watch-retro-go-sd)
  **release** registers: NES, Game Boy / GB Color, Game Gear, Master System,
  Genesis, SG-1000, PC Engine, ColecoVision, MSX, Atari 2600 / 7800, Amstrad CPC,
  Supervision, Tamagotchi, Pokémon Mini, Game & Watch, Homebrew, PICO-8.
- **11-language UI** (ko, en, ja, zh-CN, zh-TW, de, es, fr, it, pt, ru, no) with
  per-locale CJK/Cyrillic fonts lazy-loaded on demand.
- **Optional Korean mode** (`GNW_KOREAN_MODE=true`) — Korean auto-naming, the
  "Korean-patched" flag, and related filters. **Off by default** (international image).
- **Optional experimental mode** (`GNW_EXPERIMENTAL_MODE=true`) — a "personal
  lab" for the [jshsakura fork firmware](https://github.com/jshsakura/game-and-watch-retro-go-sd):
  systems no upstream *release* registers yet — Neo Geo Pocket, WonderSwan, Virtual Boy,
  Super Nintendo, Odyssey², ZX Spectrum, C64, Game.com — the Super Metroid homebrew
  port, and the MEDIA tab (video → `/video` MJPEG `.avi`, music → `/music`, clock
  backgrounds).
  *(**PC Engine CD**, **Atari Lynx** and **Game Boy Advance** used to live here.
  Upstream [v1.4.0](https://github.com/sylverb/game-and-watch-retro-go-sd/releases/tag/v1.4.0)
  registers all three, so a stock firmware reads them and they are official now —
  upstream still labels them beta/experimental, but that is about maturity, not about
  needing the fork.)*
  **Off by default** — everything above stays hidden and the app tracks only what a
  firmware you can actually flash today supports.
- Retro **pixel-art UI** with a Zelda ↔ Mario edition toggle.

## 🔄 How it works

Game & What sits between your ROM collection and the SD card. The typical flow:

```
   your files                Game & What                     SD card
 ┌────────────┐   upload   ┌───────────────────────┐  ZIP  ┌─────────────┐
 │ ROMs       │──────────► │ • auto-name           │──────►│ /roms       │
 │ (+ videos, │            │ • fetch + render cover │       │ /covers     │
 │  music,    │            │ • rate / curate        │       │ /cores      │
 │  BIOS)     │            │ • exclude from SD      │       │ bios/…      │
 └────────────┘            │ • test in browser      │       └─────────────┘
                           └───────────────────────┘        extract to card
```

1. **Upload** a ROM (drag & drop, or a whole folder). The app detects the system,
   normalizes the filename, and stores it under `/roms/<sys>/`.
2. **Cover art** is fetched from the first provider that has a hit and rendered to
   the exact device spec. You can override it — search, upload your own, or crop.
3. **Curate** — sort by rating, hide low-quality dumps from the device with
   *Exclude from SD*, and (optionally) preview a ROM in the browser emulator.
4. **Download the SD ZIP.** Everything is packed in the firmware's exact directory
   layout. Extract to the root of a FAT32 SD card and boot the device.

> The app is **stateless toward your card** — it never writes to the SD directly.
> It hands you a ZIP; you extract it. Your library (DB + uploads) lives in a mounted
> volume and survives restarts and upgrades.

## 🚀 Getting started

The app ships as a single Docker image (FastAPI backend + built React UI on one
port). No database to set up, no build step — pull and run.

### 1. Prerequisites

- **[Docker](https://docs.docker.com/get-docker/)** (Desktop on Windows/macOS, or
  Engine on Linux). That's the only requirement.
- A **FAT32-formatted microSD card** and a Game & Watch running the
  [retro-go-sd](https://github.com/sylverb/game-and-watch-retro-go-sd) firmware
  (flashing the firmware itself is out of scope — see that project's guide).
- Your own **legally-obtained ROMs** (this project ships none).

### 2. Run it (Docker)

**Option A — one-liner:**

```bash
docker run -d --name game-and-what \
  -p 38472:8080 \
  -v "$PWD/data:/app/backend/data" \
  --restart unless-stopped \
  ghcr.io/jshsakura/game-and-what:latest
# → open http://localhost:38472
```

**Option B — Docker Compose** (recommended; easier to update and configure).
Save this as `docker-compose.yml`:

```yaml
services:
  game-and-what:
    image: ghcr.io/jshsakura/game-and-what:latest
    container_name: game-and-what
    ports:
      - "38472:8080"          # host:container — change the left side freely
    volumes:
      - ./data:/app/backend/data   # your library + DB live here
    environment:
      # All optional — the app boots with none. See .env.example / DEPLOY.md.
      IGDB_CLIENT_ID: ""
      IGDB_CLIENT_SECRET: ""
      TGDB_API_KEY: ""
    restart: unless-stopped
```

Then:

```bash
docker compose up -d
# → open http://localhost:38472
```

No API keys are required — cover search is just limited without them (see
[Configuration](#️-configuration)). The `./data` folder holds your entire library
(SQLite DB + uploads); back it up and you back up everything.

### 3. First use — from ROM to SD card

1. Open **`http://localhost:38472`** (or your host's IP + port).
2. Pick a **system tab** (e.g. Game Boy) and **drag a ROM** onto the page — or use
   the upload button. The cover is fetched and rendered automatically.
3. Repeat for as many ROMs as you like. Fix any missed cover with **search /
   upload / crop**, and toggle **Exclude from SD** on anything you don't want on
   the device.
4. Click **Download SD ZIP**. You'll get one archive in the firmware's layout.
5. **Extract it to the root of your FAT32 SD card** (so the card has `/roms`,
   `/covers`, `/cores`, etc. at the top level). Eject, insert into the device,
   power on. Your games are there.

> Need a BIOS for a system (Famicom Disk, ColecoVision, PC Engine CD…)? See
> [BIOS / system ROMs](#-bios--system-roms) — upload it once and it rides along in
> the ZIP at the right path.

### 4. Updating to a new version

Your data lives in the mounted volume, so upgrades are safe:

```bash
# Compose
docker compose pull && docker compose up -d

# Plain docker run
docker pull ghcr.io/jshsakura/game-and-what:latest
docker rm -f game-and-what
# …then re-run the same `docker run` command from step 2
```

Images are tagged per release (`:1.8.1`, `:1.8`, `:latest`) — pin a specific tag
if you prefer to control upgrades.

### Platform notes (NAS / Raspberry Pi / Windows)

- **Raspberry Pi & ARM SBCs** — the image is **multi-arch** (`amd64` + `arm64`);
  the same `docker pull` works. No emulation, native ARM.
- **Synology / QNAP NAS** — add the image in Container Manager / Container Station,
  map a host folder to `/app/backend/data`, and expose port `8080`. Same as any
  container.
- **Windows / macOS** — use Docker Desktop; the commands above are identical. On
  Windows, run them in PowerShell or WSL (in PowerShell, replace `$PWD` with `${PWD}`).
- **File ownership (Linux hosts)** — if the container can't write to `./data`,
  build with a matching UID (`UID=1000 docker compose build`) or `chown` the data
  dir. Details in [DEPLOY.md](DEPLOY.md).

Full deployment reference — env vars, publishing, Zero-Trust access — in
**[DEPLOY.md](DEPLOY.md)**.

## 💾 BIOS / system ROMs

A few systems need a copyrighted BIOS that we can't ship. Upload each file in the
**Extra (추가파일)** tab at the exact **SD path** below (the INFO tab lists these
too, with one-click copy). The file then rides along in the SD ZIP at that path,
where **both** the device firmware and the in-browser player load it. BIOS files
are user-supplied — grab your own dumps; the sizes below are the standard ones.

| System | SD path (upload target) | Size | Notes |
|--------|-------------------------|------|-------|
| Famicom Disk System | `bios/nes/disksys.rom` | 8 KB | Only `.fds` disk images need it; `.nes` carts boot without. |
| ColecoVision | `bios/coleco/coleco.bin` | 8 KB | System ROM — every game needs it. |
| PC Engine CD | `bios/pce/syscard3.pce` | 256 KB | System Card 3.0 — boots essentially the whole CD library. The firmware checks the dump: md5 `38179df8f4ac870017db21ebcbf53114`. |
| Game Boy Advance | `bios/gba/gba_bios.bin` | 16 KB | **Device only.** gpSP embeds an open-source BIOS and falls back to it, but [upstream v1.4.0](https://github.com/sylverb/game-and-watch-retro-go-sd/releases/tag/v1.4.0) does not recommend that — some games misbehave on the substitute. Browser play uses mGBA, which boots HLE and never needs it. |
| Odyssey² / Videopac | `bios/videopac/o2rom.bin` | 1 KB | o2rom system BIOS for the o2em core. |
| Commodore 64 | `bios/c64/basic.bin`, `bios/c64/kernal.bin`, `bios/c64/chargen.bin` | 8 / 8 / 4 KB | The three C64 system ROMs (© Commodore). |
| Tiger Game.com | `bios/gamecom/internal.bin`, `bios/gamecom/external.bin` | 4 / 256 KB | Internal OS + external/kernel ROM (© Tiger). |

> The browser core may look for a slightly different filename than the SD stores
> (e.g. ColecoVision's core wants `colecovision.rom` for the same bytes) — the app
> handles that remap for you. The canonical list lives in
> [`frontend/src/bios.js`](frontend/src/bios.js).

## 🧱 Homebrew — required files

The homebrew apps (Zelda 3, Super Mario World, Celeste, …) are compiled **into the
firmware**, and the firmware update unpacks its own half of `/roms/homebrew/` onto
the card. **The only file you add is the one that comes from your own cartridge** —
so in practice: put in the cart, nothing else.

| App | The firmware update installs | You add | How to make it |
|-----|------------------------------|---------|----------------|
| Zelda 3 | `Zelda 3.bin`, `zelda3.ro` | `zelda3_assets.dat` | Original **US** `zelda3.sfc` (sha1 `6d4f10a8…`, hash-checked) → `make -C external/zelda3 tables/zelda3_assets.dat` |
| Super Mario World | `Super Mario World.bin` | `smw_assets.dat` | Original **US** `smw.sfc` (sha1 `6b47bb75…`) → `make -C external/smw smw_assets.dat` |
| Super Metroid *(fork only)* | `Super Metroid.bin`, `sm.xip` | `sm.smc` | No tool — it's **the original 3 MB JP ROM itself**, read at runtime |
| Celeste Classic | `celeste.bin` | — | Nothing to add |

Add your file on the game's card in the library (**Add / replace data file**); it
then rides along in the SD ZIP. The INFO tab lists the same table with one-click
path copy. Notes worth knowing:

- **Keep the firmware's own files out of the library.** `.bin`, `zelda3.ro` and
  `sm.xip` are a matched pair with the build you flashed — they link against that
  build's addresses. Let the firmware update place them; a copy kept here would
  only overwrite the fresh one with a stale one on the next SD ZIP.
- **Don't rename a `.bin`.** The firmware dispatches on the exact filename stem, so
  a renamed app loads and then matches nothing. (The library blocks the rename.)
- **Super Metroid needs an upgraded flash chip.** Its ROM is cached into external
  flash — 3 MB does not fit the stock 1 MB.
- A `.dat` built from a different ROM (or a different build of the extractor) is
  rejected as `Mismatching …_assets.dat`; a missing one halts with
  `Missing …_assets.dat` on screen.

The canonical list lives in [`frontend/src/homebrew.js`](frontend/src/homebrew.js);
the generator scripts and per-app button maps are in the
[firmware README](https://github.com/sylverb/game-and-watch-retro-go-sd#homebrew-ports).

## 📸 Screenshots

*(from the [live demo](https://jshsakura.github.io/game-and-what/) — sample data)*

| Library — per-system grid, covers, one-click SD ZIP | Built-in guide & SD spec reference |
|---|---|
| ![Library](docs/screen-library.png) | ![Info & spec](docs/screen-info.png) |

**Pick your edition** — the whole UI reskins between a Zelda (green) and Mario (red) theme:

![Mario edition](docs/screen-mario.png)

## ⚙️ Configuration

There is **no in-app settings screen** — everything is an environment variable
(the Docker convention). Provide keys via `docker run -e`, a compose `.env`, or
`backend/.env` for local dev. **Nothing is required to boot.** Keys are read at
startup, so recreate the container after changing one. See
**[`.env.example`](.env.example)** and the table in [DEPLOY.md](DEPLOY.md).

| Variable | Default | Purpose |
|---|---|---|
| `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` | — | IGDB cover search / auto-fill (free Twitch dev app) |
| `TGDB_API_KEY` | — | TheGamesDB cover search / auto-fill (free key, monthly quota) |
| `STEAMGRIDDB_API_KEY` | — | SteamGridDB cover search (free Bearer token) |
| `GNW_KOREAN_MODE` | `false` | Korea-specific features (한글패치 / 한글명) |
| `GNW_EXPERIMENTAL_MODE` | `false` | "Personal lab": fork-firmware extras — experimental systems + MEDIA tab |
| `GNW_CORS_ORIGINS` | `*` | CORS allow-list (the app has no auth — front it with Zero Trust) |

> **Why bother with cover-search keys?** With none, the app falls back to
> libretro-thumbnails only. Adding even one provider (IGDB is free and broad)
> dramatically improves cover hit-rate and gives you IGDB ratings for curation.

## 🔒 Security — no built-in login

The app has **no authentication** (single shared workspace, `CORS=*`). **Do not
expose it raw to the internet.** Put a Zero Trust layer in front (Cloudflare
Tunnel + Access, or Tailscale). Details and setup steps in
[DEPLOY.md](DEPLOY.md#access-control--no-login-use-zero-trust).

## ❓ FAQ & troubleshooting

**A cover didn't get found / looks wrong.**
Add an `IGDB` key (free, broad coverage) and re-run cover search on that ROM, or
just **search / upload / crop** the cover manually from the ROM's card.

**Can I play games in the browser to test them?**
Yes — systems with a WASM core support in-page emulation (experimental). It's for
quick verification before flashing, not a full experience.

**The SD ZIP didn't work on my device.**
Make sure you extracted it to the **root** of a **FAT32** card (so `/roms`,
`/covers`, etc. sit at the top level), and that your device runs the
[retro-go-sd](https://github.com/sylverb/game-and-watch-retro-go-sd) firmware.
Systems needing a [BIOS](#-bios--system-roms) won't boot without it.

**Port `38472` is already in use.**
Change the host side of the port map — `-p 9000:8080` (docker run) or the
`ports:` left value in compose. The container always listens on `8080` internally.

**The container can't write to my data folder (Linux).**
UID mismatch. Rebuild with your UID (`UID=1000 docker compose build`) or `chown`
the mounted `data` dir to the container's user. See [DEPLOY.md](DEPLOY.md).

**Where's my library stored / how do I back it up?**
Everything mutable is in the mounted volume (`./data` → `/app/backend/data`):
SQLite DB + all uploads. Copy that folder and you've backed up the whole install.

**I see extra systems / a MEDIA tab that the README calls "official 20".**
You (or the image) have `GNW_EXPERIMENTAL_MODE=true`. That's the fork-firmware
lab; turn it off for the official-only feature set.

## 🛠️ Develop from source

```bash
# Backend — FastAPI on :38080
cd backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 38080

# Frontend — Vite dev server on :38081 (proxies /api → :38080)
cd frontend
npm install
npm run dev
# → http://localhost:38081
```

Local secrets go in `backend/.env` (git-ignored, auto-loaded by `config.py`).
Run the backend tests with `cd backend && python3 -m pytest`.

## 🧱 Tech stack

- **Backend:** FastAPI (Python 3.12), SQLite, Pillow, `ffmpeg`.
- **Frontend:** React 18 + Vite, lucide-react, Nostalgist.js, Press Start 2P +
  Noto Sans (KR/JP/SC/TC) fonts.
- **Packaging:** multi-stage Docker (Vite build → Python image serving the SPA +
  API on one port). Multi-arch (amd64/arm64) image published to GHCR via GitHub
  Actions on version tags.

## 🙏 Credits

- [retro-go-sd](https://github.com/sylverb/game-and-watch-retro-go-sd) (sylverb) —
  the firmware this tool targets, and the source of the card layout & cover spec.
- [retro-go](https://github.com/ducalex/retro-go) (ducalex) — upstream.
- The `smw` / `zelda3` reimplementation ports (snesrev) used by the homebrew apps.
- Cover art: [IGDB](https://www.igdb.com/), [TheGamesDB](https://thegamesdb.net/),
  [SteamGridDB](https://www.steamgriddb.com/),
  [libretro-thumbnails](https://github.com/libretro-thumbnails).

## ⚖️ Disclaimer

This project ships **no ROMs, BIOS, or copyrighted game assets** — you supply your
own legally-obtained files. "Game & Watch", game titles and related marks are
trademarks of their respective owners; this project is **unaffiliated** with and
**not endorsed** by Nintendo or any rights holder. Provided for use with content
you are legally entitled to.

## 📜 License

This project's **own source code** is [MIT](LICENSE) © 2026 jshsakura.

It **bundles third-party components** (libretro emulator cores under
`frontend/public/cores/`, system icons, fonts) that retain their **own licenses**
— GPLv2/GPLv3, zlib, Public Domain, and CC BY 4.0. See
**[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)** for the full per-component list
and corresponding-source links.

> ⚠️ **Non-commercial as distributed.** The bundled **Genesis Plus GX** core
> (Genesis/MD, Master System, Game Gear, SG-1000) is under a **non-commercial**
> license. The project **as assembled and distributed** therefore may not be used
> or redistributed commercially. The MIT grant covers the author's own code only.
