// ── Static demo mode (GitHub Pages preview) ──────────────────────────────────
// There is NO backend on GitHub Pages, so when the frontend is built with
// VITE_DEMO=1 we monkeypatch window.fetch to serve canned fixtures. The real UI
// then renders fully with sample data — most things are empty or fake, but the
// design/layout is identical to the live app. korean_mode stays OFF (this is the
// international/public build), and cover images use an inline SVG placeholder.
export const DEMO = import.meta.env.VITE_DEMO === "1";

// The demo can preview BOTH deploy flavours: the default is the official
// (upstream-only) feature set; `?lab` shows the experimental "personal lab"
// mode — fork-only systems + the MEDIA tab. The banner links between the two.
export const DEMO_LAB = DEMO && new URLSearchParams(window.location.search).has("lab");

// Systems list — same shape the backend returns (platform identifiers only).
// Full fork set; official demo serves only the non-experimental ones.
const SYSTEMS = [{"key":"nes","name":"NES","dirname":"nes","exts":["nes","fds","nsf"],"pico8":false,"experimental":false},{"key":"gb","name":"Game Boy","dirname":"gb","exts":["gb","gbc"],"pico8":false,"experimental":false},{"key":"gbc","name":"GB Color","dirname":"gbc","exts":["gb","gbc"],"pico8":false,"experimental":false},{"key":"gg","name":"Game Gear","dirname":"gg","exts":["gg"],"pico8":false,"experimental":false},{"key":"sms","name":"Master System","dirname":"sms","exts":["sms"],"pico8":false,"experimental":false},{"key":"md","name":"Genesis","dirname":"md","exts":["md","gen","bin"],"pico8":false,"experimental":false},{"key":"32x","name":"Sega 32X","dirname":"32x","exts":["32x","bin"],"pico8":false,"experimental":true},{"key":"sg","name":"SG-1000","dirname":"sg","exts":["sg"],"pico8":false,"experimental":false},{"key":"pce","name":"PC Engine","dirname":"pce","exts":["pce"],"pico8":false,"experimental":false},{"key":"pcecd","name":"PC Engine CD","dirname":"pcecd","exts":["chd","cue"],"pico8":false,"experimental":true},{"key":"col","name":"ColecoVision","dirname":"col","exts":["col"],"pico8":false,"experimental":false},{"key":"msx","name":"MSX","dirname":"msx","exts":["dsk","rom","mx1","mx2","cdk"],"pico8":false,"experimental":false},{"key":"a2600","name":"Atari 2600","dirname":"a2600","exts":["a26","bin"],"pico8":false,"experimental":false},{"key":"a7800","name":"Atari 7800","dirname":"a7800","exts":["a78","bin"],"pico8":false,"experimental":false},{"key":"lynx","name":"Atari Lynx","dirname":"lynx","exts":["lnx"],"pico8":false,"experimental":false},{"key":"amstrad","name":"Amstrad CPC","dirname":"amstrad","exts":["dsk","cdk"],"pico8":false,"experimental":false},{"key":"wsv","name":"Supervision","dirname":"wsv","exts":["wsv","sv","bin"],"pico8":false,"experimental":false},{"key":"ngp","name":"NEOGEO Pocket","dirname":"ngp","exts":["ngp","ngc","ngpc"],"pico8":false,"experimental":true},{"key":"ws","name":"WonderSwan","dirname":"ws","exts":["ws","wsc"],"pico8":false,"experimental":true},{"key":"vb","name":"Virtual Boy","dirname":"vb","exts":["vb"],"pico8":false,"experimental":true},{"key":"gba","name":"Game Boy Advance","dirname":"gba","exts":["gba"],"pico8":false,"experimental":true},{"key":"snes","name":"Super Nintendo","dirname":"snes","exts":["sfc","smc"],"pico8":false,"experimental":true},{"key":"videopac","name":"Odyssey²","dirname":"videopac","exts":["bin"],"pico8":false,"experimental":true},{"key":"zxs","name":"ZX Spectrum","dirname":"zxs","exts":["z80","tap","tzx","sna","szx"],"pico8":false,"experimental":true},{"key":"c64","name":"Commodore 64","dirname":"c64","exts":["d64","t64","prg","crt","g64","tap"],"pico8":false,"experimental":true},{"key":"gamecom","name":"Tiger Game.com","dirname":"gamecom","exts":["bin","tgc"],"pico8":false,"experimental":true},{"key":"tama","name":"Tamagotchi","dirname":"tama","exts":["b"],"pico8":false,"experimental":false},{"key":"mini","name":"Pokémon Mini","dirname":"mini","exts":["min"],"pico8":false,"experimental":false},{"key":"gw","name":"Game & Watch","dirname":"gw","exts":["gw"],"pico8":false,"experimental":false},{"key":"homebrew","name":"Homebrew","dirname":"homebrew","exts":["bin","dat"],"pico8":false,"experimental":false},{"key":"pico8","name":"PICO-8","dirname":"pico8","exts":["p8","png"],"pico8":true,"experimental":false}];

// Per-title inline-SVG cover (data URI → no request, can never 404). Styled as a
// retro cartridge label — per-title hue, chunky frame, the game title in big
// type and a small DEMO tag — so sample covers read as intentional art, not as
// broken images.
const hueFor = (s) => {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
};

function coverSvg(title) {
  const hue = hueFor(title);
  const words = title.split(" ");
  const split = Math.ceil(words.length / 2);
  const line1 = words.slice(0, split).join(" ");
  const line2 = words.slice(split).join(" ");
  const bg = `hsl(${hue} 42% 34%)`;
  const panel = `hsl(${hue} 46% 26%)`;
  const frame = `hsl(${hue} 55% 16%)`;
  const glint = `hsl(${hue} 55% 48%)`;
  // Simple 8-bit sprite (5x4 invader-ish) drawn with 6px blocks, centered.
  const SPRITE = ["01010", "11111", "10101", "01110"];
  const px = SPRITE.flatMap((row, y) =>
    row.split("").map((c, x) =>
      c === "1" ? `<rect x='${78 + x * 6}' y='${16 + y * 6}' width='6' height='6' fill='${glint}'/>` : ""
    )
  ).join("");
  return (
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' width='186' height='100'>` +
      `<rect width='186' height='100' fill='${frame}'/>` +
      `<rect x='4' y='4' width='178' height='92' fill='${bg}'/>` +
      `<rect x='4' y='4' width='178' height='10' fill='${glint}' opacity='0.35'/>` +
      `<rect x='10' y='50' width='166' height='40' rx='3' fill='${panel}'/>` +
      px +
      `<text x='93' y='${line2 ? 66 : 72}' fill='#f2ead8' font-family='monospace' font-size='13' font-weight='bold' text-anchor='middle'>${line1}</text>` +
      (line2 ? `<text x='93' y='82' fill='#f2ead8' font-family='monospace' font-size='13' font-weight='bold' text-anchor='middle'>${line2}</text>` : "") +
      `<rect x='140' y='8' width='40' height='13' rx='2' fill='#00000055'/>` +
      `<text x='160' y='18' fill='#f2ead8' font-family='monospace' font-size='9' text-anchor='middle'>DEMO</text>` +
      `</svg>`
    )
  );
}

// Generic fallback (unknown id) + per-rom lookup used by api.coverUrl in DEMO.
export const PLACEHOLDER_COVER = coverSvg("Game & What");
const COVER_BY_ROM_ID = {};
export function demoCoverUrl(romId) {
  return COVER_BY_ROM_ID[romId] || PLACEHOLDER_COVER;
}

// A handful of fake roms across a few systems — enough to populate the grid.
// Generic titles only (no real game content); covers are the placeholder.
const SAMPLE_TITLES = [
  "Sample Cart 01", "Sample Cart 02", "Demo Adventure", "Pixel Quest",
  "Retro Racer", "Block Puzzle", "Star Voyager", "Cave Diver",
  "Mini Kart", "Dungeon Run", "Sky Hopper", "Bit Brawler",
];
const SAMPLE_SYSTEMS = ["nes", "gb", "gbc", "md", "sms", "pce"];

function fakeRom(i) {
  const sys = SAMPLE_SYSTEMS[i % SAMPLE_SYSTEMS.length];
  const name = SAMPLE_TITLES[i % SAMPLE_TITLES.length] + (i >= SAMPLE_TITLES.length ? ` ${i}` : "");
  return {
    id: `demo-${i}`,
    session_id: "public",
    system_key: sys,
    original_name: name,
    stored_name: `${name}.${sys === "gb" || sys === "gbc" ? "gb" : "bin"}`,
    korean_name: null,
    rom_path: `roms/${sys}/${name}`,
    cover_path: `covers/${sys}/${name}.img`,
    cover_status: i % 4 === 0 ? "none" : "ok",
    created_at: "2026-06-18 00:00:00",
    cover_source: "auto",
    crop_box: null,
    is_korean_patched: 0, lang_source: "auto", region: null, cover_flag: null,
    sd_include: 0, sd_exclude: i % 7 === 0 ? 1 : 0, extra_files: null, favorite: i % 6 === 0 ? 1 : 0,
    pico8_compat: null, patch_ver: null,
    // IGDB score spread so the preview shows every tier (null = unfetched,
    // -1 = no rating, else the 0-100 score).
    igdb_score: [88, 73, 56, 42, null, -1, 81][i % 7],
    igdb_votes: [1700, 240, 35, 12, 0, 0, 96][i % 7],
    display_name: name, display_region: null,
  };
}

const LIBRARY = {
  session_id: "public",
  roms: Array.from({ length: 12 }, (_, i) => fakeRom(i)),
  videos: [],
  music: [],
};
LIBRARY.roms.forEach((r) => { COVER_BY_ROM_ID[r.id] = coverSvg(r.display_name); });

// Path → fixture. Order matters (first match wins for prefix routes).
function route(path) {
  if (path.endsWith("/api/systems")) return { systems: DEMO_LAB ? SYSTEMS : SYSTEMS.filter((s) => !s.experimental) };
  if (path.endsWith("/api/health")) return { status: "ok", ffmpeg: true };
  if (path.endsWith("/api/config")) return { korean_mode: false, experimental_mode: DEMO_LAB, cover_sources: { libretro: true, igdb: false, tgdb: false, sgdb: false } };
  if (path.endsWith("/library")) return LIBRARY;
  if (path.endsWith("/firmware")) return { present: false };
  if (path.endsWith("/extra")) return { files: [] };
  if (path.endsWith("/data")) return { files: [] };
  if (path.endsWith("/package/size")) return { bytes: 0 };
  if (path.includes("/search")) return { results: [] };          // igdb/tgdb/sgdb
  return {};                                                       // safe empty default
}

const DEMO_NOTICE = "Demo mode — install via Docker to use uploads and edits.";

// Install once, before the app renders. GET → fixture JSON; any write → a clear
// "demo mode" rejection so mutating actions don't silently appear to work.
export function installDemoFetch() {
  const realFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url = typeof input === "string" ? input : input?.url || "";
    if (!url.includes("/api/")) return realFetch(input, init);    // assets, fonts…
    const method = (init.method || "GET").toUpperCase();
    if (method !== "GET") {
      return Promise.resolve(new Response(JSON.stringify({ detail: DEMO_NOTICE }), {
        status: 403, headers: { "Content-Type": "application/json" },
      }));
    }
    return Promise.resolve(new Response(JSON.stringify(route(url)), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
  };
  // Default the UI to English for the demo unless the visitor already chose one.
  try {
    if (!localStorage.getItem("gnw_lang")) localStorage.setItem("gnw_lang", "en");
  } catch (_) { /* ignore */ }
}
