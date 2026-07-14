import React, { useEffect, useMemo, useRef, useState } from "react";
import RomTab from "./tabs/RomTab.jsx";
import ExtraTab from "./tabs/ExtraTab.jsx";
import MediaTab from "./tabs/MediaTab.jsx";
import LibraryTab from "./tabs/LibraryTab.jsx";
import DataTab from "./tabs/DataTab.jsx";
import HelpTab from "./tabs/HelpTab.jsx";
import ActivityFeed from "./ActivityFeed.jsx";
import { Upload, Clapperboard, Library, Download, Database, Info, Check, X, HardDrive, Languages, Loader2 } from "lucide-react";
import { getLibrary, packageSize, formatBytes, EMPTY_SD_FILTER, sdFilterCount } from "./api.js";
import SdFilterPanel from "./SdFilterPanel.jsx";
import { useDownload } from "./download.jsx";
import { useT, useI18n } from "./i18n.jsx";
import { useExperimentalMode, useKoreanMode } from "./config.jsx";
import { LOCALES } from "./i18n.locales.js";
import { DEMO, DEMO_LAB } from "./demo.js";

const REPO_URL = "https://github.com/jshsakura/game-and-what";

// Intro/demo bar for the static GitHub Pages preview: explains what the site is
// and that the data is sample-only, with links to the real thing.
function DemoBanner() {
  const t = useT();
  return (
    <div className="demo-banner">
      <span>
        🎮 {t("Demo preview — sample data only. A retro SD-card manager for the Game & Watch handheld.")}
      </span>
      <span className="demo-banner-links">
        <a href={REPO_URL} target="_blank" rel="noreferrer">GitHub ★</a>
        <a href={`${REPO_URL}#quick-start-docker`} target="_blank" rel="noreferrer">🐳 Docker</a>
        {/* Preview both deploy flavours: official (default) ↔ experimental lab. */}
        {DEMO_LAB
          ? <a href={window.location.pathname}>🧪 {t("Official mode preview")}</a>
          : <a href={`${window.location.pathname}?lab`}>🧪 {t("Experimental mode preview")}</a>}
      </span>
      <span className="demo-banner-tip">
        💡 {t("Self-host")}:&nbsp;
        <code
          title={t("Click to copy")}
          onClick={(e) => navigator.clipboard?.writeText(e.currentTarget.textContent)}
        >docker run -p 38472:8080 ghcr.io/jshsakura/game-and-what</code>
      </span>
    </div>
  );
}

const THEME_KEY = "gnw_theme";

// Systems that go on the card no matter what the SD-ZIP scope says. Homebrew holds
// the data files the firmware's built-in apps (Zelda 3, SMW, Super Metroid) cannot
// boot without — they are not games with a language, so a Korean-only card still
// needs them or those menu entries die on launch.
const ALWAYS_SHIPPED = new Set(["homebrew"]);

// Edition mark — swaps with the theme (CSS hides the inactive one).
const TABS = [
  // Primary: LIBRARY (default landing) + UPLOAD. Secondary (gray): MEDIA + DATA + HELP.
  // MEDIA merges the old VIDEO + MUSIC converters into one tab.
  // label is an English i18n key — rendered via t(tab.label) in JSX.
  { key: "library", label: "Library", Icon: Library },
  { key: "rom", label: "Upload", Icon: Upload },
  { key: "extra", label: "Extra", Icon: HardDrive },
  // MEDIA (video/music/clock converters) targets the fork firmware only —
  // hidden unless the deploy runs in experimental ("personal lab") mode.
  { key: "media", label: "Media", Icon: Clapperboard, secondary: true, media: true, experimental: true },
  { key: "data", label: "Data", Icon: Database, secondary: true, data: true },
  { key: "help", label: "Info", Icon: Info, secondary: true, help: true },
];

// 8-bit pixel heart (Zelda life heart) — used as the toggle knob.
const HEART_ROWS = ["0110110", "1111111", "1111111", "0111110", "0011100", "0001000"];
function PixelHeart({ size = 14 }) {
  return (
    <svg className="pixheart" width={size} height={size} viewBox="0 0 7 6" shapeRendering="crispEdges" aria-hidden>
      {HEART_ROWS.flatMap((row, y) =>
        row.split("").map((c, x) =>
          c === "1" ? <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" /> : null
        )
      )}
    </svg>
  );
}

// Edition emblem shown to the LEFT of the title — swaps with the theme:
// Zelda → Triforce (gold), Mario → a generic ("fake", non-Nintendo) mushroom.
function EditionEmblem({ theme, size = 26 }) {
  if (theme === "mario") {
    return (
      <svg className="edition-emblem mushroom" width={size} height={size} viewBox="0 0 24 24" aria-hidden>
        <path d="M3 13a9 9 0 0 1 18 0v1.2H3z" fill="#e0504a" />
        <rect x="8.5" y="14" width="7" height="8" rx="2" fill="#f4ead2" stroke="#c98b6a" strokeWidth="0.6" />
        <circle cx="8.3" cy="9.6" r="1.9" fill="#fff" />
        <circle cx="15.7" cy="9.6" r="1.9" fill="#fff" />
        <circle cx="12" cy="6.4" r="1.2" fill="#fff" />
      </svg>
    );
  }
  return (
    <svg className="edition-emblem triforce" width={size} height={size} viewBox="0 0 24 22" aria-hidden>
      <polygon points="12,1 6.4,10.6 17.6,10.6" fill="#e8c349" />
      <polygon points="6,11.6 0.4,21 11.6,21" fill="#e8c349" />
      <polygon points="18,11.6 12.4,21 23.6,21" fill="#e8c349" />
    </svg>
  );
}

// Edition toggle — simple left/right on-off switch; background colour is the
// edition (Zelda green / Mario red), knob is an 8-bit heart.
function ThemeToggle({ theme, onToggle }) {
  const t = useT();
  const isMario = theme === "mario";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={isMario}
      className={`theme-switch ${isMario ? "mario" : "zelda"}`}
      onClick={onToggle}
      title={t("Edition: {ed} · click to switch", { ed: isMario ? "Mario" : "Zelda" })}
    >
      <span className="theme-switch-knob"><PixelHeart size={14} /></span>
    </button>
  );
}

// Flag image with graceful fallback: some locales have no bundled flag PNG yet
// (e.g. tw, pt, ru, no) → show a short text code badge instead of a broken image.
function LangFlag({ locale }) {
  const [broken, setBroken] = useState(false);
  if (broken) return <span className="lang-code">{locale.code.toUpperCase()}</span>;
  return (
    <img
      src={`${import.meta.env.BASE_URL}flags/${locale.flag}.png`}
      alt={locale.label}
      onError={() => setBroken(true)}
    />
  );
}

// UI language picker (11 locales mirroring the retro-go-sd firmware set), shown as
// the current language's flag in the header. Opens a dropdown; closes on outside
// click / Escape — same idiom as SystemSelect.
function LangToggle() {
  const { lang, setLang } = useI18n();
  const t = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const current = LOCALES.find((l) => l.code === lang) || LOCALES[0];

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={`lang-switch ${open ? "open" : ""}`} ref={ref}>
      <button
        type="button"
        className="lang-switch-trigger"
        onClick={() => setOpen((o) => !o)}
        title={t("Language")}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="language"
      >
        <LangFlag locale={current} />
      </button>
      {open && (
        <div className="lang-panel" role="listbox">
          {LOCALES.map((l) => (
            <button
              key={l.code}
              type="button"
              role="option"
              aria-selected={l.code === lang}
              className={`lang-opt ${l.code === lang ? "on" : ""}`}
              onClick={() => { setLang(l.code); setOpen(false); }}
            >
              <LangFlag locale={l} />
              <span className="lang-opt-name">{l.label}</span>
              {l.code === lang && <Check size={13} strokeWidth={3} aria-hidden />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const t = useT();
  const experimental = useExperimentalMode();
  const koreanMode = useKoreanMode();
  const visibleTabs = TABS.filter((td) => experimental || !td.experimental);
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || "zelda");
  const [tab, setTab] = useState("library");
  const [reloadKey, setReloadKey] = useState(0);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);   // first library fetch — show button skeletons
  const [sdSize, setSdSize] = useState(null);
  const [libKeys, setLibKeys] = useState([]);        // system keys that have roms (selectable)
  const [selected, setSelected] = useState(() => new Set()); // checked systems for download
  const [selSize, setSelSize] = useState(null);
  const [roms, setRoms] = useState([]);           // the library, for counting what a filter would ship
  const [sdFilter, setSdFilter] = useState(EMPTY_SD_FILTER);   // SD ZIP 상세 조건
  const dl = useDownload();

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    getLibrary()
      .then((l) => {
        setCount(l.roms.length + l.videos.length + (l.music?.length || 0));
        setLibKeys([...new Set(l.roms.map((r) => r.system_key))].sort());
        setRoms(l.roms);
      })
      .catch(() => { setCount(0); setLibKeys([]); setRoms([]); })
      .finally(() => setLoading(false));   // stays false after first settle (no skeleton flash on reloads)
  }, [reloadKey]);

  // Does this ROM survive the conditions? The server decides for real (SdFilter in
  // routers/package.py); this mirror exists so the UI can grey out a platform that
  // would ship nothing, and count what a selection actually contains, without a
  // round-trip per keystroke. Homebrew is exempt there and here.
  const passes = useMemo(() => (rom) => {
    if (ALWAYS_SHIPPED.has(rom.system_key)) return true;
    if (rom.sd_exclude || rom.pico8_compat === "broken") return false;
    if (sdFilter.flags.length && !sdFilter.flags.includes(rom.cover_flag || "none")) return false;
    if (sdFilter.patched && !rom.is_korean_patched) return false;
    if (sdFilter.favorite && !rom.favorite) return false;
    if (sdFilter.minScore != null && !(rom.igdb_score >= sdFilter.minScore)) return false;
    if (sdFilter.maxMb && rom.size_bytes != null
        && rom.size_bytes > sdFilter.maxMb * 1024 * 1024) return false;
    return true;
  }, [sdFilter]);

  // Per-flag ROM counts for the panel — so a condition that would ship nothing reads
  // as zero before you pick it.
  const flagCounts = useMemo(() => {
    const out = {};
    for (const r of roms) {
      const code = r.cover_flag || "none";
      out[code] = (out[code] || 0) + 1;
    }
    return out;
  }, [roms]);

  // Platforms that still have something to ship under the conditions.
  const keepKeys = useMemo(
    () => new Set(roms.filter(passes).map((r) => r.system_key)), [roms, passes]);

  // Full-library size. Cleared BEFORE the refetch: changing a condition changes the
  // answer, and leaving the old number up until the new one lands reads as "nothing
  // happened". null == recalculating.
  useEffect(() => {
    let alive = true;
    setSdSize(null);
    packageSize(undefined, sdFilter)
      .then((b) => alive && setSdSize(b))
      .catch(() => alive && setSdSize(null));
    return () => { alive = false; };
  }, [reloadKey, sdFilter]);

  // Download selection (system key == dirname). 전체 선택 + 다운로드 live together top-right.
  // A platform the conditions empty out isn't selectable: checking it would ship an
  // empty folder, so the choice narrows the board instead of lying about it.
  const pickableKeys = useMemo(
    () => libKeys.filter((k) => keepKeys.has(k)), [libKeys, keepKeys]);
  const toggleSel = (key) => setSelected((s) => {
    const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n;
  });
  const selectedDirs = useMemo(
    () => pickableKeys.filter((k) => selected.has(k)), [pickableKeys, selected]);
  const allSelected = pickableKeys.length > 0 && pickableKeys.every((k) => selected.has(k));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(pickableKeys));
  const selKey = selectedDirs.join(",");
  const hasSel = selectedDirs.length > 0;

  // Setting a condition re-checks exactly the platforms that still have something to
  // ship, so you don't have to hunt for which ones those are.
  const filterCount = sdFilterCount(sdFilter);
  useEffect(() => {
    if (filterCount) setSelected(new Set(libKeys.filter((k) => keepKeys.has(k))));
  }, [filterCount, sdFilter, libKeys, keepKeys]);

  // Size of the checked-systems selection (for the top-right download button).
  useEffect(() => {
    let alive = true; setSelSize(null);
    if (selKey) packageSize(selKey, sdFilter).then((b) => alive && setSelSize(b)).catch(() => {});
    return () => { alive = false; };
  }, [selKey, reloadKey, sdFilter]);

  // Two sizes, and they are not the same number: `bytes` is what lands ON THE CARD
  // (uncompressed — the one that decides whether it fits), `zipBytes` is what you
  // download. The button shows the card size, since fitting the card is the point;
  // the zip size joins the tooltip once that build exists. null == recalculating.
  const shownSize = allSelected ? sdSize : selSize;
  const sizing = hasSel && shownSize == null;
  const cardBytes = shownSize?.bytes ?? null;
  const zipBytes = shownSize?.zipBytes ?? null;
  const sizeTitle = cardBytes == null ? undefined
    : zipBytes != null
      ? t("On the card: {card} · download (ZIP): {zip}", { card: formatBytes(cardBytes), zip: formatBytes(zipBytes) })
      : t("On the card: {card} · the ZIP is smaller; its exact size is known once it's built", { card: formatBytes(cardBytes) });

  const bumpLibrary = () => setReloadKey((k) => k + 1);

  const toggleTheme = () => setTheme((t) => (t === "mario" ? "zelda" : "mario"));

  return (
    <div className="app">
      {DEMO && <DemoBanner />}
      <header className="topbar">
        <div
          className="brand-id"
          role="button"
          tabIndex={0}
          title={t("Home")}
          onClick={() => setTab("library")}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setTab("library"); } }}
        >
          <EditionEmblem theme={theme} />
          <h1 title={t("Game & What — Retro SD Manager")}>{t("Game & What")}</h1>
        </div>
        <div className="topbar-actions">
          {loading ? (
            <>
              <span className="is-skel tg-skel lang" aria-hidden />
              <span className="is-skel tg-skel theme" aria-hidden />
              <span className="is-skel tg-skel bell" aria-hidden />
            </>
          ) : (
            <>
              <LangToggle />
              <ThemeToggle theme={theme} onToggle={toggleTheme} />
              <ActivityFeed pulse={reloadKey} onChanged={bumpLibrary} />
            </>
          )}
        </div>
      </header>

      <div className="tabbar">
        <nav className="tabs">
          {visibleTabs.map((tabDef, i) => (
            <React.Fragment key={tabDef.key}>
              {tabDef.secondary && !visibleTabs[i - 1]?.secondary && <span className="tab-divider" aria-hidden />}
              <button
                className={`tab ${tab === tabDef.key ? "active" : ""} ${tabDef.secondary ? "tab-secondary" : ""} ${tabDef.media ? "tab-media" : ""} ${tabDef.help ? "tab-help" : ""} ${tabDef.data ? "tab-data" : ""} ${loading ? "is-skel" : ""}`}
                onClick={() => setTab(tabDef.key)}
                title={t(tabDef.label)}
              >
                <tabDef.Icon size={15} strokeWidth={2.5} aria-hidden /> {t(tabDef.label)}
              </button>
            </React.Fragment>
          ))}
        </nav>
        {/* Select-all + SD ZIP belong to the library view — hide the whole
            group on other tabs instead of letting SD ZIP tag along alone. */}
        {tab !== "library" ? null : (loading || count > 0) ? (
          // While the library loads, the REAL controls render shimmered in place
          // (is-skel). Fixed-width skeleton boxes can't track a localized label or
          // the conditions button, so they always swapped in at the wrong size.
          //
          // Three controls: which platforms, on what conditions, then get it. On a
          // phone the first two share the top row and the download takes the width
          // below (see .tabbar-dl in theme.css).
          <div className="tabbar-dl">
            <button
              className={`btn tab-selall ${allSelected ? "on" : ""} ${loading ? "is-skel" : ""}`}
              onClick={toggleAll}
              disabled={loading || pickableKeys.length === 0}
              title={t("Select / clear all platforms")}
            >
              {allSelected
                ? <><X size={14} strokeWidth={3} aria-hidden /> {t("All platforms")}</>
                : <><Check size={14} strokeWidth={3} aria-hidden /> {t("All platforms")}</>}
            </button>
            {/* Every condition on what lands on the card lives in one panel — flags,
                size cap, rating floor, favorites, patched. Not a toggle per idea. */}
            <SdFilterPanel filter={sdFilter} onChange={setSdFilter}
              flagCounts={flagCounts} disabled={loading} />
            <button className={`btn tab-dl has-size ${loading ? "is-skel" : ""}`}
              disabled={loading || !hasSel || dl.busy}
              onClick={() => dl.downloadPackage(
                allSelected ? undefined : selKey,
                `gnw-sd${allSelected ? "" : "-selected"}${filterCount ? "-filtered" : ""}.zip`,
                zipBytes || cardBytes || 0,
                sdFilter,
              )}
              title={hasSel ? (allSelected ? t("Download the full SD (incl. firmware & BIOS) as ZIP") : t("Download the checked platforms as an SD ZIP")) : t("Check a platform (or select all) to download")}>
              <Download size={14} strokeWidth={2.5} aria-hidden /> SD ZIP
              {hasSel && (
                <span className={`size-tag ${sizing ? "sizing" : ""}`}
                  title={sizing ? t("Recalculating the size for this selection…") : sizeTitle}>
                  {sizing
                    ? <><Loader2 size={10} strokeWidth={3} className="spin" aria-hidden /> {t("Sizing…")}</>
                    : <>
                        {/* Say WHICH size this is. "SD" = what it takes on the card
                            (uncompressed); "ZIP" = the actual download, once built. */}
                        <span className="size-kind">{zipBytes != null ? "ZIP" : "SD"}</span>
                        {formatBytes(zipBytes != null ? zipBytes : cardBytes)}
                      </>}
                </span>
              )}
            </button>
          </div>
        ) : null}
      </div>

      <div className="device">
        <div className="lcd">
          {tab === "rom" && <RomTab onChanged={bumpLibrary} />}
          {tab === "extra" && <ExtraTab onChanged={bumpLibrary} />}
          {tab === "media" && experimental && <MediaTab onChanged={bumpLibrary} />}
          {tab === "library" && <LibraryTab reloadKey={reloadKey} onChanged={bumpLibrary} selected={selected}
            onToggleSel={toggleSel} passes={passes} keepKeys={keepKeys}
            filtered={filterCount > 0} alwaysKeys={ALWAYS_SHIPPED} />}
          {tab === "data" && <DataTab onChanged={bumpLibrary} />}
          {tab === "help" && <HelpTab />}
        </div>
      </div>
    </div>
  );
}
