// ── Static demo mode (GitHub Pages preview) ──────────────────────────────────
// There is NO backend on GitHub Pages, so when the frontend is built with
// VITE_DEMO=1 we monkeypatch window.fetch to serve canned fixtures. The real UI
// then renders fully with sample data — most things are empty or fake, but the
// design/layout is identical to the live app. korean_mode stays OFF (this is the
// international/public build), and cover images use an inline SVG placeholder.
export const DEMO = import.meta.env.VITE_DEMO === "1";

// Systems list — same shape the backend returns (platform identifiers only).
const SYSTEMS = [{"key":"nes","name":"NES","dirname":"nes","exts":["nes","fds","nsf"],"pico8":false},{"key":"gb","name":"Game Boy","dirname":"gb","exts":["gb","gbc"],"pico8":false},{"key":"gbc","name":"GB Color","dirname":"gbc","exts":["gb","gbc"],"pico8":false},{"key":"gg","name":"Game Gear","dirname":"gg","exts":["gg"],"pico8":false},{"key":"sms","name":"Master System","dirname":"sms","exts":["sms"],"pico8":false},{"key":"md","name":"Genesis","dirname":"md","exts":["md","gen","bin"],"pico8":false},{"key":"sg","name":"SG-1000","dirname":"sg","exts":["sg"],"pico8":false},{"key":"pce","name":"PC Engine","dirname":"pce","exts":["pce"],"pico8":false},{"key":"col","name":"ColecoVision","dirname":"col","exts":["col"],"pico8":false},{"key":"msx","name":"MSX","dirname":"msx","exts":["dsk","rom","mx1","mx2","cdk"],"pico8":false},{"key":"a2600","name":"Atari 2600","dirname":"a2600","exts":["a26","bin"],"pico8":false},{"key":"a7800","name":"Atari 7800","dirname":"a7800","exts":["a78","bin"],"pico8":false},{"key":"lynx","name":"Atari Lynx","dirname":"lynx","exts":["lnx"],"pico8":false},{"key":"amstrad","name":"Amstrad CPC","dirname":"amstrad","exts":["dsk","cdk"],"pico8":false},{"key":"wsv","name":"Watara","dirname":"wsv","exts":["wsv","sv","bin"],"pico8":false},{"key":"tama","name":"Tamagotchi","dirname":"tama","exts":["b"],"pico8":false},{"key":"mini","name":"Pokémon Mini","dirname":"mini","exts":["min"],"pico8":false},{"key":"gw","name":"Game & Watch","dirname":"gw","exts":["gw","mgw"],"pico8":false},{"key":"homebrew","name":"Homebrew","dirname":"homebrew","exts":["bin","dat"],"pico8":false},{"key":"pico8","name":"PICO-8","dirname":"pico8","exts":["p8","png"],"pico8":true}];

// A neutral inline-SVG "no real data" cover placeholder (data URI → no request).
export const PLACEHOLDER_COVER =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='186' height='100'>` +
    `<rect width='100%' height='100%' fill='#2a2a3a'/>` +
    `<text x='50%' y='50%' fill='#7a7a96' font-family='monospace' font-size='11' ` +
    `text-anchor='middle' dominant-baseline='middle'>DEMO</text></svg>`
  );

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

// Path → fixture. Order matters (first match wins for prefix routes).
function route(path) {
  if (path.endsWith("/api/systems")) return { systems: SYSTEMS };
  if (path.endsWith("/api/health")) return { status: "ok", ffmpeg: true };
  if (path.endsWith("/api/config")) return { korean_mode: false };
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
