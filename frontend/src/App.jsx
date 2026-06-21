import React, { useEffect, useMemo, useRef, useState } from "react";
import RomTab from "./tabs/RomTab.jsx";
import ExtraTab from "./tabs/ExtraTab.jsx";
import MediaTab from "./tabs/MediaTab.jsx";
import LibraryTab from "./tabs/LibraryTab.jsx";
import DataTab from "./tabs/DataTab.jsx";
import HelpTab from "./tabs/HelpTab.jsx";
import ActivityFeed from "./ActivityFeed.jsx";
import { Upload, Clapperboard, Library, Download, Database, Info, Check, X, HardDrive } from "lucide-react";
import { getLibrary, packageUrl, packageSize, formatBytes } from "./api.js";
import { useDownload } from "./download.jsx";
import { useT, useI18n } from "./i18n.jsx";
import { LOCALES } from "./i18n.locales.js";
import { DEMO } from "./demo.js";

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

// Edition mark — swaps with the theme (CSS hides the inactive one).
const TABS = [
  // Primary: LIBRARY (default landing) + UPLOAD. Secondary (gray): MEDIA + DATA + HELP.
  // MEDIA merges the old VIDEO + MUSIC converters into one tab.
  // label is an English i18n key — rendered via t(tab.label) in JSX.
  { key: "library", label: "Library", Icon: Library },
  { key: "rom", label: "Upload", Icon: Upload },
  { key: "extra", label: "Extra", Icon: HardDrive },
  { key: "media", label: "Media", Icon: Clapperboard, secondary: true, media: true },
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
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || "zelda");
  const [tab, setTab] = useState("library");
  const [reloadKey, setReloadKey] = useState(0);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);   // first library fetch — show button skeletons
  const [sdSize, setSdSize] = useState(null);
  const [libKeys, setLibKeys] = useState([]);        // system keys that have roms (selectable)
  const [selected, setSelected] = useState(() => new Set()); // checked systems for download
  const [selSize, setSelSize] = useState(null);
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
      })
      .catch(() => { setCount(0); setLibKeys([]); })
      .finally(() => setLoading(false));   // stays false after first settle (no skeleton flash on reloads)
    packageSize().then(setSdSize).catch(() => setSdSize(null));
  }, [reloadKey]);

  // Download selection (system key == dirname). 전체 선택 + 다운로드 live together top-right.
  const toggleSel = (key) => setSelected((s) => {
    const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n;
  });
  const selectedDirs = useMemo(() => libKeys.filter((k) => selected.has(k)), [libKeys, selected]);
  const allSelected = libKeys.length > 0 && libKeys.every((k) => selected.has(k));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(libKeys));
  const selKey = selectedDirs.join(",");
  const hasSel = selectedDirs.length > 0;

  // Size of the checked-systems selection (for the top-right download button).
  useEffect(() => {
    let alive = true; setSelSize(null);
    if (selKey) packageSize(selKey).then((b) => alive && setSelSize(b)).catch(() => {});
    return () => { alive = false; };
  }, [selKey, reloadKey]);

  const bumpLibrary = () => setReloadKey((k) => k + 1);
  const zip = packageUrl();

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
          {TABS.map((tabDef, i) => (
            <React.Fragment key={tabDef.key}>
              {tabDef.secondary && !TABS[i - 1]?.secondary && <span className="tab-divider" aria-hidden />}
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
        {loading ? (
          // Fixed-position button set — show skeletons in place so they don't pop in.
          <div className="tabbar-dl">
            {tab === "library" && <span className="btn-skel sel" aria-hidden />}
            <span className="btn-skel dl" aria-hidden />
          </div>
        ) : count > 0 ? (
          <div className="tabbar-dl">
            {tab === "library" && (
              <button
                className={`btn tab-selall ${allSelected ? "on" : ""}`}
                onClick={toggleAll}
                disabled={libKeys.length === 0}
                title={t("Select / clear all platforms")}
              >
                {allSelected
                  ? <><X size={14} strokeWidth={3} aria-hidden /> {t("All")}</>
                  : <><Check size={14} strokeWidth={3} aria-hidden /> {t("All")}</>}
              </button>
            )}
            <button className="btn tab-dl has-size" disabled={!hasSel || dl.busy}
              onClick={() => dl.download(
                allSelected ? zip : packageUrl(selKey),
                allSelected ? "gnw-sd.zip" : "gnw-sd-selected.zip",
                (allSelected ? sdSize : selSize) || 0,
              )}
              title={hasSel ? (allSelected ? t("Download the full SD (incl. firmware & BIOS) as ZIP") : t("Download the checked platforms as an SD ZIP")) : t("Check a platform (or select all) to download")}>
              <Download size={14} strokeWidth={2.5} aria-hidden /> SD ZIP
              {hasSel && (
                <span className="size-tag">{(allSelected ? sdSize : selSize) != null ? formatBytes(allSelected ? sdSize : selSize) : "…"}</span>
              )}
            </button>
          </div>
        ) : null}
      </div>

      <div className="device">
        <div className="lcd">
          {tab === "rom" && <RomTab onChanged={bumpLibrary} />}
          {tab === "extra" && <ExtraTab onChanged={bumpLibrary} />}
          {tab === "media" && <MediaTab onChanged={bumpLibrary} />}
          {tab === "library" && <LibraryTab reloadKey={reloadKey} onChanged={bumpLibrary} selected={selected} onToggleSel={toggleSel} />}
          {tab === "data" && <DataTab onChanged={bumpLibrary} />}
          {tab === "help" && <HelpTab />}
        </div>
      </div>
    </div>
  );
}
