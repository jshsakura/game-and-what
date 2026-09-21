# Third-Party Notices

This project's **own source code** is licensed under the [MIT License](LICENSE)
© 2026 jshsakura.

It additionally **bundles and redistributes** third-party components that keep
their original licenses. Those licenses govern the corresponding files, not the
MIT license above. This file documents each bundled component, its upstream
source (the "corresponding source" for the GPL'd binaries), and its license.

> **Important — non-commercial restriction.** This distribution bundles the
> **Genesis Plus GX, Snes9x and PicoDrive** cores, which are released under
> **non-commercial** licenses. PicoDrive includes the non-commercial Cyclone 68000
> and DrZ80 components.
> As assembled and distributed (image + repo), this project as a whole therefore
> **may not be used or redistributed for commercial purposes.** The MIT grant
> applies to the author's own code in isolation; it does **not** override the
> non-commercial terms of the bundled core.

---

## Emulator cores — `frontend/public/cores/`

Pre-compiled libretro WASM cores, loaded in the browser by Nostalgist.js as
separate modules (not statically linked into this project's code). Each is
redistributed under its own license; corresponding source is at the upstream
repository listed.

| File (`*_libretro.{js,wasm}`) | System(s) | License | Upstream / corresponding source |
|---|---|---|---|
| `fceumm` | NES | GPLv2 | https://github.com/libretro/libretro-fceumm |
| `gambatte` | Game Boy / GB Color | GPLv2 | https://github.com/libretro/gambatte-libretro |
| `mednafen_pce_fast` | PC Engine | GPLv2 | https://github.com/libretro/beetle-pce-fast-libretro |
| `gearcoleco` | ColecoVision | GPLv3 | https://github.com/libretro/gearcoleco |
| `genesis_plus_gx` | Genesis/MD, Sega CD, Master System, Game Gear, SG-1000 | **Non-commercial** | https://github.com/libretro/Genesis-Plus-GX |
| `picodrive` | Sega 32X | **Non-commercial** | https://github.com/libretro/picodrive |
| `snes9x` | Super Nintendo | **Non-commercial** | https://github.com/libretro/snes9x |
| `gw_libretro` | Game & Watch (Handheld Electronic Game) | zlib | https://github.com/libretro/gw-libretro |
| `potator` | Watara Supervision | Public Domain | https://github.com/libretro/potator |
| `retro8` | PICO-8 | GPLv3 | https://github.com/libretro/retro8 |
| `tamalibretro` | Tamagotchi | GPLv2 | https://github.com/celerizer/tamalibretro (based on [jcrona/tamalib](https://github.com/jcrona/tamalib), GPLv2) |

The full text of the GNU GPL (v2, v3) and the per-core copyright headers are
available in each upstream repository above. For the GPL'd cores, the linked
upstream repositories constitute the offer of corresponding source as required
by the GPL.

## System icons — `frontend/public/system-icons/`

Console/system icons (`*.svg`, `*.png`) are sourced from the **libretro / RetroArch
assets** project (also used by [RomM](https://github.com/rommapp/romm)), licensed
under **Creative Commons Attribution 4.0 International (CC BY 4.0)**.

- Source: https://git.libretro.com/libretro-assets/retroarch-assets
- License: https://creativecommons.org/licenses/by/4.0/

## Fonts — bundled into the built frontend (via `@fontsource`)

| Font | License |
|---|---|
| Noto Sans / Noto Sans JP / KR / SC / TC | SIL Open Font License 1.1 (OFL) |
| Press Start 2P | SIL Open Font License 1.1 (OFL) |

## Other dependencies

Python (`backend/requirements.txt`) and npm (`frontend/package.json`) runtime
dependencies are distributed under their own permissive licenses (MIT / BSD /
Apache-2.0; Pillow under HPND; py7zr under LGPL-2.1). See each package's
distribution for the authoritative text.

---

This project ships **no ROMs, BIOS, or copyrighted game content** — users supply
their own legally-obtained files. See the [Disclaimer](README.md#disclaimer).
