// Canonical homebrew file catalog — what each firmware-built-in homebrew app
// needs at /roms/homebrew/ before it will boot. Consumed by:
//   - the INFO tab reference table (HelpTab.jsx),
//   - the docs (README).
//
// The apps themselves are compiled INTO the firmware, so "installing" one is
// really just placing its data files on the SD card. Two kinds of file, and the
// difference is the whole point of this table:
//
//   source: "firmware" — comes out of the firmware build you flashed (the .bin
//     launch template, zelda3.ro, sm.xip). It is a matched pair with that build:
//     a copy from another release links against different addresses and dies on
//     launch. Take these from the release you actually flashed.
//   source: "rom" — you generate it from your OWN original cartridge dump. These
//     are copyrighted game data, so they are never shipped with anything: not the
//     firmware, not this app.
//
// Every path is verified against the firmware source (Core/Src/porting/<app>/):
// zelda3 → main_zelda3.c:87,388 · smw → main_smw.c:97 · sm → main_sm.c:57,163.
//
// Entries with `experimental: true` are fork-only apps and are hidden from the
// INFO table when the deploy isn't in experimental mode.

export const HOMEBREW_CATALOG = [
  {
    key: "zelda3",
    label: "Zelda 3 — A Link to the Past",
    files: [
      { sdPath: "roms/homebrew/Zelda 3.bin", source: "firmware" },
      { sdPath: "roms/homebrew/zelda3.ro", source: "firmware" },
      { sdPath: "roms/homebrew/zelda3_assets.dat", source: "rom" },
    ],
    note: "Build the assets file from an original US Zelda 3 ROM (zelda3.sfc, sha1 6d4f10a8…, enforced by the tool): put it in external/zelda3/tables/ and run `make -C external/zelda3 tables/zelda3_assets.dat`. Other languages need the dialogue extracted from each localized ROM first — see the firmware README. Without the .dat the app halts with \"Missing zelda3_assets.dat\"; without zelda3.ro it says nothing and crashes, so ship both.",
  },
  {
    key: "smw",
    label: "Super Mario World",
    files: [
      { sdPath: "roms/homebrew/Super Mario World.bin", source: "firmware" },
      { sdPath: "roms/homebrew/smw_assets.dat", source: "rom" },
    ],
    note: "Build the assets file from an original US Super Mario World ROM (smw.sfc, sha1 6b47bb75…): put it in external/smw/assets/ and run `make -C external/smw smw_assets.dat`. A .dat from a different ROM — or from a different build of the tool — is rejected as \"Mismatching smw_assets.dat\".",
  },
  {
    key: "sm",
    experimental: true,
    label: "Super Metroid",
    tag: "fork only",
    files: [
      { sdPath: "roms/homebrew/Super Metroid.bin", source: "firmware" },
      { sdPath: "roms/homebrew/sm.xip", source: "firmware" },
      { sdPath: "roms/homebrew/sm.smc", source: "rom" },
    ],
    note: "The odd one out — no assets file. The port still reads the original ROM while it runs, so your own 3 MB Super Metroid ROM (sm.smc, the Japanese one) goes on the card as-is; a Korean fan-patched ROM is detected and offered as the second language. It is cached into external flash, so a 3 MB ROM needs an upgraded flash chip — it will not fit the stock 1 MB. sm.xip holds the cold code banks and read-only data that don't fit in RAM; like the .bin it comes out of the firmware build and must be from that same release.",
  },
];

// Apps that need nothing but the firmware — listed so the INFO tab can say so
// instead of leaving users hunting for a file that doesn't exist.
export const HOMEBREW_SELF_CONTAINED = ["Celeste Classic"];

// Fast lookup by app key.
export const HOMEBREW_BY_KEY = Object.fromEntries(HOMEBREW_CATALOG.map((h) => [h.key, h]));
