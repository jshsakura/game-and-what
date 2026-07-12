// Canonical homebrew file catalog — what each firmware-built-in homebrew app
// needs at /roms/homebrew/ before it will boot. Consumed by:
//   - the INFO tab reference table (HelpTab.jsx),
//   - the docs (README).
//
// The apps are compiled INTO the firmware, and the firmware update unpacks its
// own half onto the card. So there are two kinds of file, and only one of them
// is yours to manage:
//
//   source: "firmware" — the .bin launch template and its siblings (zelda3.ro,
//     sm.xip). The firmware update writes these; they are a matched pair with
//     that build, so a copy kept anywhere else only risks overwriting the right
//     one with a stale one. Listed here so you know what belongs on the card —
//     NOT so you add it. Don't put them in the library.
//   source: "rom" — made from your OWN original cartridge dump. This is the only
//     thing you have to supply. It is copyrighted game data, so nothing ships it:
//     not the firmware, not this app.
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
    note: "You supply the assets file only. Build it from an original US Zelda 3 ROM (zelda3.sfc, sha1 6d4f10a8…, enforced by the tool): put it in external/zelda3/tables/ and run `make -C external/zelda3 tables/zelda3_assets.dat`. Other languages need the dialogue extracted from each localized ROM first — see the firmware README. Without the .dat the app halts with \"Missing zelda3_assets.dat\".",
  },
  {
    key: "smw",
    label: "Super Mario World",
    files: [
      { sdPath: "roms/homebrew/Super Mario World.bin", source: "firmware" },
      { sdPath: "roms/homebrew/smw_assets.dat", source: "rom" },
    ],
    note: "You supply the assets file only. Build it from an original US Super Mario World ROM (smw.sfc, sha1 6b47bb75…): put it in external/smw/assets/ and run `make -C external/smw smw_assets.dat`. A .dat from a different ROM — or from a different build of the tool — is rejected as \"Mismatching smw_assets.dat\".",
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
    note: "The odd one out — no assets file. Drop in the cartridge itself: the port reads the original ROM while it runs, so your own 3 MB Super Metroid ROM (sm.smc, the Japanese one) goes on the card as-is. A Korean fan-patched ROM is detected and offered as the second language. It is cached into external flash, so 3 MB needs an upgraded flash chip — it will not fit the stock 1 MB. (sm.xip, the cold code banks that don't fit in RAM, comes with the firmware update.)",
  },
];

// Apps that need nothing but the firmware — listed so the INFO tab can say so
// instead of leaving users hunting for a file that doesn't exist.
export const HOMEBREW_SELF_CONTAINED = ["Celeste Classic"];

// Fast lookup by app key.
export const HOMEBREW_BY_KEY = Object.fromEntries(HOMEBREW_CATALOG.map((h) => [h.key, h]));
