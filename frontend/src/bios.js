// Canonical BIOS catalog — the single source of truth for every system that
// needs a user-supplied BIOS/system ROM to boot. Consumed by:
//   - the browser emulator (emulator.jsx) to know what to fetch before launch,
//   - the INFO tab reference table (HelpTab.jsx),
//   - the docs (README).
//
// Users upload each file to the Extra tab at the exact `sdPath`; the
// SD ZIP then places it at /<sdPath>, where BOTH the real device firmware and
// the browser core look for it.
//
// `coreName` is the filename the libretro BROWSER core expects in its system
// dir — it can differ from the SD filename (e.g. gearcoleco wants
// "colecovision.rom" while the SD stores the same bytes as "coleco.bin").
//
// Entries with `experimental: true` belong to fork-only systems and are
// hidden from the INFO table when the deploy isn't in experimental mode.
//
// BIOS files are copyrighted and must be supplied by the user — we never ship
// them. Sizes are the standard No-Intro/redump sizes so users can sanity-check
// a dump before uploading.

export const BIOS_CATALOG = [
  {
    key: "nes",
    label: "Famicom Disk System",
    tag: "FDS only",
    note: "Only .fds disk images need this — regular .nes cartridges boot without it.",
    files: [
      { sdPath: "bios/nes/disksys.rom", coreName: "disksys.rom", size: "8 KB" },
    ],
  },
  {
    key: "col",
    label: "ColecoVision",
    note: "The ColecoVision system ROM — every game needs it to boot.",
    files: [
      { sdPath: "bios/coleco/coleco.bin", coreName: "colecovision.rom", size: "8 KB" },
    ],
  },
  {
    key: "pcecd",
    label: "PC Engine CD",
    note: "System Card 3.0 — boots essentially the entire CD library. The firmware checks the dump: md5 38179df8f4ac870017db21ebcbf53114.",
    files: [
      { sdPath: "bios/pce/syscard3.pce", coreName: "syscard3.pce", size: "256 KB" },
    ],
  },
  {
    // DEVICE ONLY — deliberately no `coreName`. The firmware's gpSP wants a real BIOS
    // (upstream v1.4.0: "open source bios is included but it's not recommended as it
    // could cause some bugs in some games"), while the browser runs mGBA, which boots
    // .gba HLE and needs nothing. Giving this a coreName would make a missing file
    // block browser play for a system that has never required one — see the BIOS map
    // in emulator.jsx.
    key: "gba",
    tag: "device only",
    label: "Game Boy Advance",
    note: "gpSP on the device ships an open-source BIOS and falls back to it, but upstream recommends the real one — some games misbehave on the substitute. Browser play never needs it.",
    files: [
      { sdPath: "bios/gba/gba_bios.bin", size: "16 KB" },
    ],
  },
  {
    key: "videopac",
    experimental: true,
    label: "Odyssey² / Videopac",
    note: "The o2rom system BIOS — the o2em core can't boot without it.",
    files: [
      { sdPath: "bios/videopac/o2rom.bin", coreName: "o2rom.bin", size: "1 KB" },
    ],
  },
  {
    key: "c64",
    experimental: true,
    label: "Commodore 64",
    note: "The three C64 system ROMs (© Commodore, user-supplied).",
    files: [
      { sdPath: "bios/c64/basic.bin",   coreName: "basic",   size: "8 KB" },
      { sdPath: "bios/c64/kernal.bin",  coreName: "kernal",  size: "8 KB" },
      { sdPath: "bios/c64/chargen.bin", coreName: "chargen", size: "4 KB" },
    ],
  },
  {
    key: "gamecom",
    experimental: true,
    label: "Tiger Game.com",
    note: "Internal OS + external/kernel ROM (© Tiger, user-supplied).",
    files: [
      { sdPath: "bios/gamecom/internal.bin", coreName: "internal.bin", size: "4 KB" },
      { sdPath: "bios/gamecom/external.bin", coreName: "external.bin", size: "256 KB" },
    ],
  },
];

// Fast lookup by system key.
export const BIOS_BY_KEY = Object.fromEntries(BIOS_CATALOG.map((b) => [b.key, b]));

// Every distinct SD path in the catalog — handy for docs/examples.
export const BIOS_EXAMPLE_PATHS = BIOS_CATALOG.flatMap((b) => b.files.map((f) => f.sdPath));
