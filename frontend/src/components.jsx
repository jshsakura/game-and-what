import React, { useEffect, useRef, useState } from "react";
import Cropper from "react-easy-crop";
import {
  Check, ImageOff, XCircle, ImagePlus, Loader, Play,
  Download, MoreHorizontal, Trash2, X, Film, Music, ChevronDown, Pencil, Search, Hand, Crop, Upload, FolderPlus, Star,
  AlertTriangle, HelpCircle, Timer, Copy, Files, ArrowDownUp, HardDriveDownload,
} from "lucide-react";
import { EmulatorOverlay, canPlay, isExperimental } from "./emulator.jsx";
import { useDownload } from "./download.jsx";
import {
  uploadCover, coverUrl, deviceCoverUrl, originalCoverUrl, coverDownloadUrl, downloadRomUrl, downloadVideoUrl, downloadMusicUrl,
  videoThumbUrl, videoPreviewUrl, musicCoverUrl, streamMusicUrl, deleteRom, deleteVideo, deleteMusic,
  renameRom, igdbSearch, tgdbSearch, sgdbSearch, setCoverFromUrl, deleteCover, recropCover, replaceRomFile, formatBytes, setRomLang, setSdInclude, setSdExclude,
  setFavorite, addRomFile, deleteRomFile, setPico8Compat, setCoverFlag,
} from "./api.js";
import { useToast } from "./toast.jsx";
import { useT } from "./i18n.jsx";

// NEW = uploaded TODAY (the viewer's local calendar day). created_at is stored
// UTC; we compare against local "today" so a fresh batch is easy to spot and
// organize before it blends into the list. Sorting is newest-first separately.
export function isNewRom(rom) {
  const ts = rom?.created_at;
  if (!ts) return false;
  const d = new Date(ts.replace(" ", "T") + "Z"); // parse as UTC
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return d.getFullYear() === now.getFullYear()
      && d.getMonth() === now.getMonth()
      && d.getDate() === now.getDate();
}

// System icon keyed 1:1 to the firmware folder name (dirname): the asset at
// /system-icons/<dirname>.svg is THE icon for that system. Until that asset is
// dropped in, fall back to a DISTINCT colored code chip per system (so systems
// never look identical).
const SYS_ABBREV = {
  nes: "NES", gb: "GB", gbc: "GBC", gg: "GG", sms: "SMS", md: "MD", sg: "SG",
  pce: "PCE", pcecd: "PCD", col: "COL", msx: "MSX", a2600: "A26", a7800: "A78", amstrad: "CPC",
  wsv: "WSV", tama: "TAM", mini: "MIN", gw: "GW", homebrew: "HB", pico8: "P8",
  lynx: "LNX",
};

function hueFor(key) {
  let h = 0;
  for (const c of key) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

// Distinct vivid accent per system (the hash hues were too similar).
const SYS_PALETTE = {
  nes: "#e23b3b", gb: "#6ab02c", gbc: "#7b3ff2", gg: "#13a8c4", sms: "#2c7be0",
  md: "#e07a1a", sg: "#13a07a", pce: "#d61f6b", pcecd: "#a61e5d", col: "#d94f2b", msx: "#3b5bdb",
  a2600: "#9b59b6", a7800: "#b5651d", amstrad: "#0f9d58", wsv: "#d4a017",
  tama: "#1fc4a8", mini: "#e84393", gw: "#c9a227", homebrew: "#6b7280", pico8: "#ff77a8",
  lynx: "#82c91e",
};
export function systemColor(key) {
  return SYS_PALETTE[key] || `hsl(${hueFor(key || "x")} 62% 52%)`;
}

// IGDB score → quality tier (color band): 80+ great, 65+ good, 45+ ok, else low.
export function scoreTier(score) {
  if (score >= 80) return "hi";
  if (score >= 65) return "mid";
  if (score >= 45) return "lo";
  return "vlo";
}

// Score → face, a finer 6-step gradient from a medal (great) to a crying face (bad).
export function scoreFace(score) {
  if (score >= 90) return "🏅";
  if (score >= 80) return "😄";
  if (score >= 70) return "🙂";
  if (score >= 60) return "😐";
  if (score >= 50) return "🙁";
  return "😢";
}

// Try the real asset (svg first, then png — RomM ico-derived), then fall back
// to the colored monogram chip when no asset exists (tama/gw/homebrew).
const ICON_EXTS = ["svg", "png"];
// Cache-buster for the static /system-icons assets. They live under a fixed URL,
// so a browser/Cloudflare cache serves the OLD file after we swap an icon (no
// Cache-Control on the origin → CF caches .svg by default). Bump this whenever a
// shipped icon changes so the URL differs and clients refetch.
const ICON_VER = "20260628";
export function SystemIcon({ dirname, size = 16 }) {
  const [extIdx, setExtIdx] = useState(0);
  const imgRef = useRef(null);
  useEffect(() => { setExtIdx(0); }, [dirname]);
  const exhausted = extIdx >= ICON_EXTS.length;
  const next = () => setExtIdx((i) => i + 1);

  // A cached/transient broken image won't fire onError (it's already `complete`
  // with naturalWidth 0) → it would show a broken-X. Detect and advance to the
  // next ext, finally the monogram. Guarantees the chip never shows an X.
  useEffect(() => {
    const im = imgRef.current;
    if (im && im.complete && im.naturalWidth === 0) next();
  }, [extIdx, dirname]);

  if (dirname && !exhausted) {
    return (
      <img
        ref={imgRef}
        className="sys-ico"
        src={`${import.meta.env.BASE_URL}system-icons/${dirname}.${ICON_EXTS[extIdx]}?v=${ICON_VER}`}
        width={size}
        height={size}
        alt=""
        onError={next}
        onLoad={(e) => { if (e.currentTarget.naturalWidth === 0) next(); }}
      />
    );
  }
  const label = SYS_ABBREV[dirname] || (dirname || "?").slice(0, 3).toUpperCase();
  const hue = hueFor(dirname || "x");
  return (
    <span
      className="sys-mono"
      style={{ background: `hsl(${hue} 48% 38%)`, fontSize: Math.max(6, Math.round(size * 0.5)) }}
      aria-hidden
    >
      {label}
    </span>
  );
}

// "Cartridge slot" dropdown for picking a system — replaces the wall of chips.
// Closes on outside click / Escape. The trigger reads like a cartridge seated
// in a slot; the panel lists all systems with their icon + accepted extensions.
export function SystemSelect({ systems, value, onChange }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const current = systems.find((s) => s.key === value);

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
    <div className={`sysselect ${open ? "open" : ""}`} ref={ref}>
      <button
        type="button"
        className="sysselect-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="sysselect-tag">{t("Platform")}</span>
        <span className="sysselect-cart">{current?.Icon ? <current.Icon size={18} aria-hidden /> : <SystemIcon dirname={current?.dirname} size={18} />}</span>
        <span className="sysselect-name">{current?.name ?? t("Select")}</span>
        {current?.exts?.length > 0 && <span className="sysselect-ext">.{current.exts.join(" .")}</span>}
        <span className="sysselect-chev"><ChevronDown size={16} strokeWidth={2.5} aria-hidden /></span>
      </button>
      {open && (
        <div className="sysselect-panel" role="listbox">
          {systems.map((s) => (
            <button
              key={s.key}
              type="button"
              role="option"
              aria-selected={s.key === value}
              className={`sysselect-opt ${s.key === value ? "on" : ""}`}
              onClick={() => { onChange(s.key); setOpen(false); }}
            >
              {s.Icon ? <s.Icon size={18} aria-hidden /> : <SystemIcon dirname={s.dirname} size={18} />}
              <span className="sysselect-opt-name">{s.name}</span>
              {s.exts?.length > 0 && <span className="sysselect-opt-ext">.{s.exts.join(" .")}</span>}
              {s.key === value && <Check size={14} strokeWidth={3} aria-hidden />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// Recurse a dropped folder (DataTransfer entries) into a flat file list, tagging
// each file with its webkitRelativePath. Falls back to a plain file list.
async function filesFromDrop(dt) {
  const items = dt.items ? Array.from(dt.items) : [];
  const entries = items.map((it) => it.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.length) return Array.from(dt.files || []);
  const out = [];
  const walk = (entry, prefix) => new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((f) => {
        try { Object.defineProperty(f, "webkitRelativePath", { value: prefix + entry.name }); } catch (_) {}
        out.push(f); resolve();
      }, () => resolve());
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      reader.readEntries(async (ents) => {
        for (const e of ents) await walk(e, prefix + entry.name + "/");
        resolve();
      }, () => resolve());
    } else resolve();
  });
  for (const e of entries) await walk(e, "");
  return out;
}

// Drag-and-drop + click-to-pick file zone. Shows a busy overlay while onFiles
// runs. `folder` adds a button to pick a whole folder (subfolders included).
export function Dropzone({ accept, multiple, label, folder, onFiles, busyLabel }) {
  const t = useT();
  const inputRef = useRef(null);
  const folderRef = useRef(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState(null);   // null = no byte progress yet (indeterminate)

  const handle = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length || busy) return;
    setBusy(true); setPct(null);
    try {
      await Promise.resolve(onFiles(files, (loaded, total) =>
        setPct(total ? Math.min(100, Math.round((loaded / total) * 100)) : null)));
    } finally {
      setBusy(false); setPct(null);
    }
  };

  const processing = pct === 100;   // 100% uploaded, awaiting server response
  return (
    <div
      className={`dropzone ${drag ? "drag" : ""} ${busy ? "busy" : ""}`}
      onClick={() => !busy && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); if (!busy) setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={async (e) => { e.preventDefault(); setDrag(false); handle(await filesFromDrop(e.dataTransfer)); }}
    >
      {busy ? (
        <div className="dz-busy">
          <span className="dz-busy-label">
            <Loader size={15} className="spin" aria-hidden />
            {pct == null ? ` ${busyLabel || t("Uploading…")}` : processing ? ` ${t("Processing…")}` : ` ${t("Uploading… {pct}%", { pct })}`}
          </span>
          <div className={`dl-bar ${pct == null || processing ? "indet" : ""}`}>
            <div className="dl-fill" style={pct == null || processing ? undefined : { width: `${pct}%` }} />
          </div>
        </div>
      ) : (
        <>
          {label}
          {folder && (
            <button type="button" className="dz-folder-btn" disabled={busy}
              onClick={(e) => { e.stopPropagation(); folderRef.current?.click(); }}>
              <FolderPlus size={13} strokeWidth={2.5} /> {t("Whole folder")}
            </button>
          )}
        </>
      )}
      <input ref={inputRef} type="file" accept={accept} multiple={multiple} hidden
        onChange={(e) => { handle(e.target.files); e.target.value = ""; }} />
      {folder && (
        <input ref={folderRef} type="file" webkitdirectory="" directory="" multiple hidden
          onChange={(e) => { handle(e.target.files); e.target.value = ""; }} />
      )}
    </div>
  );
}

// Cover slot — shows the cover (or a beautiful centered placeholder when
// missing/broken) and is clickable to upload your own cover image directly.
export function CoverSlot({ romId, src: initialSrc, bust, alt = "", aspect = 3 / 4, onActivate, badge = null, cornerBL = null, gauge = null, status = null, overlay = null }) {
  const t = useT();
  const [src, setSrc] = useState(initialSrc || null);
  const [err, setErr] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const imgRef = useRef(null);
  const showImg = src && !err;

  // Cached images can be `complete` before React attaches onLoad, so onLoad never
  // fires and the skeleton would spin forever. Detect that and mark it loaded.
  useEffect(() => {
    const img = imgRef.current;
    if (img && img.complete) {
      if (img.naturalWidth > 0) setLoaded(true);
      else setErr(true);
    }
  }, [src]);

  // Failsafe: if a cover request stalls (e.g. backend busy building the SD zip),
  // stop the skeleton after a timeout so it never spins forever.
  useEffect(() => {
    if (!showImg || loaded) return undefined;
    const t = setTimeout(() => setLoaded(true), 10000);
    return () => clearTimeout(t);
  }, [showImg, loaded, src]);

  // Reflect external src changes (e.g. cover_status flipped to ok after reload).
  useEffect(() => { setSrc(initialSrc || null); setErr(false); setLoaded(false); }, [initialSrc]);
  // A cover (re)applied elsewhere keeps the SAME url → bump the bust to reload.
  useEffect(() => {
    if (bust && romId) { setSrc(`${coverUrl(romId)}?v=${bust}`); setErr(false); setLoaded(false); }
  }, [bust, romId]);

  // Clickable even while 'pending' — opening the detail lets the user upload a
  // cover manually, which acts as a stop/override for the running search.
  return (
    <div
      className={`shot cover-slot ${showImg ? "" : "shot-empty"} ${romId ? "clickable" : ""}`}
      style={{ aspectRatio: aspect }}
      onClick={() => romId && onActivate?.()}
      title={romId ? t("Click for details") : ""}
    >
      {showImg ? (
        <>
          {!loaded && <div className="skeleton" aria-hidden />}
          <img
            ref={imgRef}
            src={src}
            alt={alt}
            loading="lazy"
            style={{ opacity: loaded ? 1 : 0 }}
            onLoad={() => setLoaded(true)}
            onError={() => { setErr(true); setLoaded(true); }}
          />
        </>
      ) : status === "pending" ? (
        <div className="cover-add cover-searching">
          <Loader size={22} className="spin" aria-hidden />
          <span>{t("Searching cover…")}</span>
        </div>
      ) : (
        <div className="cover-add">
          <ImagePlus size={24} strokeWidth={2} aria-hidden />
          <span>{t("Add cover")}</span>
        </div>
      )}
      {overlay && <span className="cover-corner">{overlay}</span>}
      {cornerBL && <span className="cover-badge bl">{cornerBL}</span>}
      {badge && <span className="cover-badge">{badge}</span>}
      {gauge && (
        <span className="cover-gauge" title={gauge.title} aria-hidden>
          <i className={`g-${gauge.cls}`} style={{ width: `${Math.min(100, gauge.pct)}%` }} />
        </span>
      )}
    </div>
  );
}

export function ProgressBar({ value }) {
  return (
    <div className="progress">
      <i style={{ width: `${Math.round((value || 0) * 100)}%` }} />
    </div>
  );
}

// Inline loading indicator — shown while a tab fetches its data.
export function Loading({ text }) {
  const t = useT();
  return (
    <div className="loading" role="status" aria-live="polite">
      <Loader size={16} className="spin" aria-hidden /> {text ?? t("Loading…")}
    </div>
  );
}

const BADGE = {
  ok: { Icon: Check, text: "COVER OK" },
  none: { Icon: ImageOff, text: "NO COVER" },
  failed: { Icon: XCircle, text: "FAIL" },
};

export function Badge({ status }) {
  const b = BADGE[status] || { Icon: null, text: status };
  return (
    <span className={`badge ${status}`}>
      {b.Icon && <b.Icon size={11} strokeWidth={2.5} aria-hidden />} {b.text}
    </span>
  );
}

// Centered popup over a dimmed backdrop.
export function Modal({ title, onClose, children }) {
  // Close ONLY on the X button or Escape — never on an outside/backdrop click
  // (avoids losing work by mis-clicking).
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <div className="modal-head">
          <span className="modal-title">{title}</span>
          <button className="icon-btn" onClick={onClose} aria-label="close">
            <X size={14} strokeWidth={2.5} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

// IGDB cover search (검색기) — runs inside the ROM popup. Search by name,
// pick a cover thumbnail → it's fetched, rendered to 186x100 .img, and applied.
// Strip the extension and release tags ((..)/[..]) so the name matches IGDB.
function cleanTitle(name = "") {
  return name
    .replace(/\.[^.]+$/, "")
    .replace(/[([{].*?[)\]}]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function CoverSearch({ rom, onPick }) {
  const t = useT();
  // Search query = the ORIGINAL file title as-is (extension + release tags
  // stripped). No language-specific extraction — same for every locale. Uses the
  // original upload name (stored_name may be the Korean-renamed file).
  const [q, setQ] = useState(cleanTitle(rom.original_name || rom.stored_name));
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState(null);
  const [err, setErr] = useState("");
  const [source, setSource] = useState("igdb");

  async function search() {
    const query = q.trim();
    if (!query || busy) return;
    setBusy(true); setErr(""); setResults(null);
    try {
      const searchFn = source === "igdb" ? igdbSearch : source === "tgdb" ? tgdbSearch : sgdbSearch;
      const d = await searchFn(query, rom.system_key);
      if (!d.available) {
        setErr(source === "igdb"
          ? t("IGDB key is not set")
          : source === "tgdb"
          ? t("TheGamesDB key is not set")
          : t("SteamGridDB key is not configured"));
      } else if (d.quota_exceeded) {
        setErr(t("TheGamesDB quota exceeded — use IGDB or try later"));
      }
      setResults(d.results || []);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="cover-search">
      <div className="field-label">{t("Cover search")}</div>
      <span className="search-scope" role="group">
        <button className={`scope-btn ${source === "igdb" ? "on" : ""}`} onClick={() => setSource("igdb")}>IGDB</button>
        <button className={`scope-btn ${source === "tgdb" ? "on" : ""}`} onClick={() => setSource("tgdb")}>TheGamesDB</button>
        <button className={`scope-btn ${source === "sgdb" ? "on" : ""}`} onClick={() => setSource("sgdb")}>SteamGridDB</button>
      </span>
      <div className="rename-row">
        <input
          className="text-input"
          value={q}
          disabled={busy}
          spellCheck={false}
          placeholder={t("Game name")}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <button className="btn" disabled={busy || !q.trim()} onClick={search}>
          {busy ? <Loader size={13} className="spin" /> : <Search size={13} strokeWidth={2.5} />} {t("Search")}
        </button>
      </div>
      <div className="muted" style={{ fontSize: "11px" }}>{t("Auto-filled from free sources on upload · search here or upload an image if missing")}</div>
      {err && <div className="badge failed">{err}</div>}
      {results && results.length === 0 && !busy && !err && (
        <div className="muted">{t("No results found.")}</div>
      )}
      {results && results.length > 0 && (
        <div className="cover-results">
          {results.map((r) => (
            <button
              key={r.cover_url}
              className="cover-result"
              title={`${r.name}${r.year ? ` (${r.year})` : ""}`}
              onClick={() => onPick(r.cover_url)}
            >
              <img src={r.thumb_url} alt={r.name} loading="lazy" />
              <span className="cover-result-name">{r.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// Each system pins ONE cover aspect so the firmware grid frame fits every cover
// (gui_draw_coverflow_v sizes the frame from one cover, centers the rest). Square
// for label art (homebrew apps, PICO-8 cart labels), 3:4 box art for everything.
const SQUARE_SYSTEMS = new Set(["homebrew", "pico8"]);
export function coverAspect(systemKey) {
  return SQUARE_SYSTEMS.has(systemKey) ? 1 : 3 / 4;   // 100×100 vs 75×100
}

// Crop to the system's FIXED aspect. The device crop-to-fills the cover to that
// exact size, so the live canvas (sized to the target) fills edge-to-edge.
function CoverCropper({ src, aspect = 3 / 4, busy, onCancel, onDone }) {
  const t = useT();
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const pctRef = useRef(null);   // croppedArea (percent) → backend fraction
  const pxRef = useRef(null);    // croppedAreaPixels → live device preview
  const canvasRef = useRef(null);
  const imgElRef = useRef(null);
  const canvasH = 100, canvasW = Math.round(canvasH * aspect);  // 75×100 or 100×100

  // Load the source once for the live device preview (display only → no CORS read).
  useEffect(() => {
    const im = new Image();
    im.onload = () => { imgElRef.current = im; drawPreview(); };
    im.src = src;
    return () => { imgElRef.current = null; };
  }, [src]);

  // Draw the cropped region FIT-WITHIN 186×100, centered (letterboxed) — exactly
  // how the device coverflow shows a cover at its own aspect.
  function drawPreview() {
    const cv = canvasRef.current, im = imgElRef.current, a = pxRef.current;
    if (!cv || !im || !a) return;
    const ctx = cv.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.clearRect(0, 0, cv.width, cv.height);
    const scale = Math.min(cv.width / a.width, cv.height / a.height);
    const dw = a.width * scale, dh = a.height * scale;
    const dx = (cv.width - dw) / 2, dy = (cv.height - dh) / 2;
    try { ctx.drawImage(im, a.x, a.y, a.width, a.height, dx, dy, dw, dh); } catch (_) {}
  }

  const cropBox = () => {
    const a = pctRef.current;
    if (!a) return null;
    return { x: a.x / 100, y: a.y / 100, width: a.width / 100, height: a.height / 100 };
  };

  return (
    <div className="cropper">
      <div className="cropper-stage">
        <Cropper
          image={src}
          crop={crop}
          zoom={zoom}
          aspect={aspect}
          restrictPosition={false}
          onCropChange={setCrop}
          onZoomChange={setZoom}
          onCropComplete={(areaPct, areaPx) => { pctRef.current = areaPct; pxRef.current = areaPx; drawPreview(); }}
        />
      </div>
      <input
        className="cropper-zoom" type="range" min="1" max="3" step="0.01"
        value={zoom} onChange={(e) => setZoom(Number(e.target.value))} aria-label="zoom"
      />
      <div className="cropper-preview">
        <canvas ref={canvasRef} width={canvasW} height={canvasH} className="device-canvas"
          style={{ height: 168, width: Math.round(168 * aspect) }} aria-hidden />
        <span>{t("Device preview (exactly {w}×{h})", { w: canvasW, h: canvasH })}</span>
      </div>
      <div className="cropper-actions">
        <button className="btn ghost" disabled={busy} onClick={onCancel}>{t("Cancel")}</button>
        <button className="btn ghost" disabled={busy} onClick={() => onDone(null)}>{t("Full original")}</button>
        <button className="btn" disabled={busy} onClick={() => onDone(cropBox())}>
          {busy ? <Loader size={13} className="spin" /> : <Check size={13} strokeWidth={2.5} />} {t("This area")}
        </button>
      </div>
    </div>
  );
}

// Detail preview: the WEB high-res cover vs the ACTUAL device .img (186×100).
// The device side carries the crop control as an OVERLAY button on the image.
function CoverCompare({ rom, bust, onRecrop }) {
  const t = useT();
  if (rom.cover_status !== "ok") {
    return (
      <div className="cover-compare empty">
        <ImageOff size={18} aria-hidden /> {t("No cover yet. Search, upload, or use auto-fill below.")}
      </div>
    );
  }
  const v = bust ? `?v=${bust}` : "";
  const ar = coverAspect(rom.system_key) === 1 ? "1 / 1" : "3 / 4";
  return (
    <div className="cover-compare" style={{ "--cover-ar": ar }}>
      <figure>
        <span className="cmp-imgwrap">
          <img className="cmp-web" src={`${originalCoverUrl(rom.id)}${bust ? `&v=${bust}` : ""}`} alt={t("Full original")} />
          <a className="cmp-dl-overlay" href={coverDownloadUrl(rom.id, "original")} download
             title={t("Download original cover")} onClick={(e) => e.stopPropagation()}>
            <Download size={12} strokeWidth={2.5} />
          </a>
        </span>
        <figcaption>{t("Original (full shape)")}</figcaption>
      </figure>
      <figure>
        <span className="cmp-imgwrap">
          <img className="cmp-device" src={`${deviceCoverUrl(rom.id)}${bust ? `&v=${bust}` : ""}`} alt={t("Device view")} />
          <a className="cmp-dl-overlay" href={coverDownloadUrl(rom.id, "device")} download
             title={t("Download device cover")} onClick={(e) => e.stopPropagation()}>
            <Download size={12} strokeWidth={2.5} />
          </a>
          {onRecrop && (
            <button type="button" className="cmp-crop-overlay" onClick={onRecrop} title={t("Adjust device cover position")}>
              <Crop size={12} strokeWidth={2.5} /> {t("Adjust position")}
            </button>
          )}
        </span>
        <figcaption>{t("Actual device")} ({coverAspect(rom.system_key) === 1 ? "100×100" : "75×100"})</figcaption>
      </figure>
    </div>
  );
}

// "KO" = the game's CONTENT is Korean — a Korean release (Korea region) OR a
// Korean fan-translation (한글 patch / J-K / (K)/[K] tag). It reads the ORIGINAL
// upload name + stored name; our own Korean *display* title (e.g. "록맨") does NOT
// trigger it — only a real Korea/한글/J-K marker does.
const KO_RE = /한글|korea|\bJ-?K\b|[(\[]\s*K\s*[)\]]/i;
export function isKoreanPatched(rom) {
  // Scanned/auto/manual rows carry the authoritative DB flag (lang_source set);
  // un-scanned legacy rows fall back to the filename heuristic.
  if (rom.lang_source) return !!rom.is_korean_patched;
  return KO_RE.test(`${rom.original_name || ""}  ${rom.stored_name || ""}`);
}

// Language code → English label (passed through t() for i18n at render time).
const LANG_LABEL = {
  ja: "Japanese", en: "English", ko: "Korean", zh: "Chinese",
  es: "Spanish", de: "German", fr: "French", it: "Italian", unl: "Unofficial",
};
export function langLabel(code) {
  return code ? (LANG_LABEL[code] || code) : "?";
}

// Language/region code → ISO country code for the flag IMAGE. Emoji flags render
// as tofu boxes on Windows (and some Linux), so we ship small flag PNGs locally
// under /public/flags. 'unl'(비공식) has no flag. English → US, PAL/Europe → EU.
const LANG_CC = {
  ko: "kr", ja: "jp", en: "us", zh: "cn",
  es: "es", de: "de", fr: "fr", it: "it", eu: "eu",
};
export function langCC(code) {
  return code ? (LANG_CC[code] || "") : "";
}
export function langFlagUrl(code) {
  const cc = langCC(code);
  return cc ? `${import.meta.env.BASE_URL}flags/${cc}.png` : "";   // bundled locally — no external CDN
}

// Cover-flag (corner country icon) options for the rom edit modal. "" = no flag.
const FLAG_OPTIONS = [
  { code: "", label: "No flag" },
  { code: "ko", label: "Korea" },
  { code: "ja", label: "Japan" },
  { code: "en", label: "USA/English" },
  { code: "zh", label: "China" },
  { code: "es", label: "Spain" },
  { code: "de", label: "Germany" },
  { code: "fr", label: "France" },
  { code: "it", label: "Italy" },
  { code: "eu", label: "Europe (EU)" },
];

// PICO-8 cart runnability on the G&W z8lua engine (from the community sheet).
// good = confirmed · partial = slow/occasional OOM · broken = doesn't run ·
// (no status) = untested. Shown as a small icon on PICO-8 cards.
const P8_COMPAT = {
  good:    { cls: "good",    Icon: Check,         label: "Compatibility (real G&W): runs fine",                    short: "Works" },
  slow:    { cls: "slow",    Icon: Timer,         label: "Compatibility (real G&W): runs, but slow",              short: "Slow" },
  partial: { cls: "partial", Icon: AlertTriangle, label: "Compatibility (real G&W): unstable (some issues / occasional OOM)", short: "Unstable" },
  broken:  { cls: "broken",  Icon: XCircle,       label: "Compatibility (real G&W): doesn't run (OOM, etc.)",    short: "Broken" },
};
const P8_UNTESTED = { cls: "untested", Icon: HelpCircle, label: "Compatibility (real G&W): untested", short: "Untested" };
const p8meta = (status) => (status && P8_COMPAT[status]) || P8_UNTESTED;
// Statuses the user can assign in the ROM detail (null → clear back to untested).
const P8_COMPAT_ORDER = ["good", "slow", "partial", "broken", null];

function Pico8Compat({ status }) {
  const t = useT();
  const m = p8meta(status);
  const Icon = m.Icon;
  return (
    <span className={`p8compat ${m.cls}`} title={t(m.label)}>
      <Icon size={12} strokeWidth={2.8} aria-hidden />
    </span>
  );
}

// Rough static cart-complexity hint → Low/Medium/High (NOT a real device figure).
const p8memLevel = (pct) =>
  pct >= 80 ? { cls: "high", label: "High" }
  : pct >= 50 ? { cls: "mid", label: "Medium" }
  : { cls: "low", label: "Low" };

// ROM-detail editor: let the user set a PICO-8 cart's real-device (G&W) status.
// The compat sheet is hand-maintained, so this is a manual override per cart.
function Pico8CompatEditor({ rom, onChanged }) {
  const t = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const current = rom.pico8_compat || null;
  const hint = rom.pico8_mem_hint;
  const lvl = hint != null ? p8memLevel(hint) : null;
  async function pick(value) {
    if (busy || value === current) return;
    setBusy(true);
    try {
      await setPico8Compat(rom.id, value);
      onChanged?.();
    } catch (err) {
      toast.error(err.message || t("Failed to set status"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="p8compat-edit">
      <label className="field-label">{t("Compatibility (real G&W)")}</label>
      <div className="p8compat-opts">
        {P8_COMPAT_ORDER.map((value) => {
          const m = p8meta(value);
          const Icon = m.Icon;
          const active = (value || null) === current;
          return (
            <button key={m.cls} type="button" disabled={busy}
              className={`p8opt ${m.cls} ${active ? "on" : ""}`}
              onClick={() => pick(value)} title={t(m.label)}>
              <Icon size={14} strokeWidth={2.6} aria-hidden />
              <span>{t(m.short)}</span>
            </button>
          );
        })}
      </div>
      {lvl && (
        <div className="p8memhint">
          <span>{t("Code size")}: <b className={`p8mem-${lvl.cls}`}>{t(lvl.label)}</b> ({hint}%)</span>
          <span className="p8memhint-note">{t("Share of the PICO-8 code limit (not on-device memory)")}</span>
        </div>
      )}
    </div>
  );
}

// Compat filter shown above the PICO-8 game list — All + one chip per status,
// each with its colored icon and a live count. Reuses the P8_COMPAT taxonomy.
const P8_FILTER_OPTS = [
  { v: "all", short: "All" },
  { v: "good", ...P8_COMPAT.good },
  { v: "slow", ...P8_COMPAT.slow },
  { v: "partial", ...P8_COMPAT.partial },
  { v: "broken", ...P8_COMPAT.broken },
  { v: "untested", ...P8_UNTESTED },
];
export function Pico8CompatFilter({ value, onChange, roms = [] }) {
  const t = useT();
  const counts = roms.reduce((acc, r) => {
    const k = r.pico8_compat || "untested";
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
  return (
    <span className="search-scope p8-filter" role="group" aria-label={t("Compatibility filter")}>
      {P8_FILTER_OPTS.map((o) => {
        const Icon = o.Icon;
        const n = o.v === "all" ? roms.length : counts[o.v] || 0;
        const on = value === o.v;
        return (
          <button key={o.v} className={`scope-btn ${on ? "on" : ""}`} aria-pressed={on}
            onClick={() => onChange(o.v)} title={t(o.label || o.short)}>
            {Icon && <span className={`p8compat ${o.cls}`}><Icon size={13} strokeWidth={2.6} /></span>}
            {t(o.short)} <span className="scope-count">{n}</span>
          </button>
        );
      })}
    </span>
  );
}

// ROM card: cover (click-to-upload) + name + per-card download + edit/delete popup.
// Library sort picker — a compact select box (sort icon + current label + caret)
// with a dropdown, same open/close idiom as the language switch. One icon, not a
// row of buttons.
export function SortSelect({ value, options, onChange }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);
  const cur = options.find((o) => o.key === value) || options[0];
  return (
    <div className={`sort-select ${open ? "open" : ""}`} ref={ref}>
      <button type="button" className="sort-select-trigger" onClick={() => setOpen((o) => !o)}
        title={t("Sort")} aria-haspopup="listbox" aria-expanded={open}>
        <ArrowDownUp size={14} strokeWidth={2.5} aria-hidden />
        <span className="sort-select-cur">{t(cur?.label ?? "")}</span>
        <ChevronDown size={13} strokeWidth={2.5} className="sort-caret" aria-hidden />
      </button>
      {open && (
        <div className="sort-panel" role="listbox">
          {options.map((o) => (
            <button key={o.key} type="button" role="option" aria-selected={o.key === value}
              className={`sort-opt ${o.key === value ? "on" : ""}`}
              onClick={() => { onChange(o.key); setOpen(false); }}>
              <span className="sort-opt-name">{t(o.label)}</span>
              {o.key === value && <Check size={13} strokeWidth={3} aria-hidden />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function RomCard({ rom, previewSrc, onChanged, dupes = [] }) {
  const toast = useToast();
  const t = useT();
  // Homebrew cards can hold extra files (e.g. smw_assets.dat). The badge counts
  // the files that actually ship in the SD download: data files (.dat etc.) plus
  // the .bin app itself once it's opted into the SD (sd_include).
  let extraFiles = [];
  try { extraFiles = JSON.parse(rom.extra_files || "[]"); } catch { extraFiles = []; }
  const dataFileCount = [rom.stored_name, ...extraFiles.map((f) => f.name)]
    .filter((n) => n && (!n.toLowerCase().endsWith(".bin") || rom.sd_include)).length;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const romFileRef = useRef(null);
  const dataFileRef = useRef(null);
  // The rename field edits the BASE name only — the extension is locked (shown as
  // a fixed suffix) so it can't be accidentally changed/removed.
  const extDot = rom.stored_name.lastIndexOf(".");
  const romExt = extDot > 0 ? rom.stored_name.slice(extDot) : "";        // e.g. ".sms"
  const romBase = extDot > 0 ? rom.stored_name.slice(0, extDot) : rom.stored_name;
  const [name, setName] = useState(romBase);
  const [nameErr, setNameErr] = useState("");
  const [coverV, setCoverV] = useState(0); // bumped on cover change → instant refresh
  const [cropper, setCropper] = useState(null); // { src, apply, revoke? }
  const [playing, setPlaying] = useState(false); // in-browser emulator overlay
  const [copied, setCopied] = useState(false);   // content-hash copy feedback
  const dl = downloadRomUrl(rom.id);
  // Route downloads through the shared overlay (Preparing… + progress) instead of a
  // bare <a download>, which showed NOTHING while the server builds a big ZIP (a
  // CD game's ROM+tracks can be hundreds of MB → felt frozen). dlBusy spins the btn.
  const { download, busy: dlBusy } = useDownload();
  const startDownload = () => dl && download(dl, `${rom.stored_name || "rom"}.zip`);

  // Copy the raw SHA-256 content hash so the user can diff look-alike dumps
  // (same game, "부제 있고 없고" 차이) outside the app.
  async function copyHash() {
    if (!rom.content_hash) return;
    try {
      await navigator.clipboard.writeText(rom.content_hash);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.warn(t("Couldn't copy"));
    }
  }
  // Card title = the (normalized) filename base "한글명 (영어)" so a manual rename
  // shows on the card instantly. (display_name is an explicit user override.)
  const title = rom.display_name || romBase;
  const runnable = canPlay(rom.system_key);

  async function launch() {
    if (isExperimental(rom.system_key)) {
      const ok = await toast.confirm(t("Run '{title}' (experimental support)", { title }), {
        detail: t("This platform may not run correctly because its browser core and ROM format can differ. Run anyway?"),
        confirmText: t("Run"),
      });
      if (!ok) return;
    }
    setOpen(false);
    setPlaying(true);
  }

  // a cover was (re)applied → reload the preview now, then refresh the library
  function coverChanged() { setCoverV(Date.now()); onChanged?.(); }

  function openModal() {
    setName(romBase);
    setNameErr("");
    setOpen(true);
  }
  // Picking a cover (IGDB or file) opens the crop step instead of applying直接.
  function pickIgdb(url) {
    setCropper({ src: url, apply: (box) => setCoverFromUrl(rom.id, url, box) });
  }
  // Re-crop the EXISTING cover (no re-download) — pick a region from the UNTOUCHED
  // full original (?full=1), not the cropped display, so it's freely re-adjustable.
  function reCrop() {
    setCropper({ src: `${originalCoverUrl(rom.id)}&v=${coverV || 1}`, apply: (box) => recropCover(rom.id, box) });
  }
  // Replace the ROM binary itself (keep name/cover/slot) — e.g. a better dump.
  async function replaceFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || busy) return;
    setBusy(true);
    try {
      await replaceRomFile(rom.id, file);
      toast.success(t("ROM file replaced"));
      onChanged?.();
    } catch (err) {
      toast.error(err.message || t("Failed to replace file"));
    } finally {
      setBusy(false);
    }
  }
  function replaceCover(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const objUrl = URL.createObjectURL(file);
    setCropper({ src: objUrl, apply: (box) => uploadCover(rom.id, file, box), revoke: objUrl });
  }
  function closeCropper() {
    if (cropper?.revoke) URL.revokeObjectURL(cropper.revoke);
    setCropper(null);
  }
  async function applyCrop(box) {
    if (busy) return;
    setBusy(true);
    try { await cropper.apply(box); coverChanged(); closeCropper(); setOpen(false); toast.success(t("Cover applied")); }
    catch (e) { toast.error((e.message && t(e.message)) || t("Failed to apply cover")); }
    finally { setBusy(false); }
  }
  async function rename() {
    const base = name.trim();
    const next = base + romExt;   // extension is locked — re-attach it on save
    if (busy || !base || next === rom.stored_name) { setOpen(false); return; }
    setBusy(true); setNameErr("");
    try { await renameRom(rom.id, next); onChanged?.(); setOpen(false); toast.success(t("Filename changed")); }
    catch (e) { setNameErr(e.message); toast.error(e.message); }
    finally { setBusy(false); }
  }
  async function removeCover() {
    if (busy) return;
    const ok = await toast.confirm(t("Remove only this cover?"), {
      detail: t("Keeps the ROM and deletes only the cover (.img + preview). You can refill it later."),
      confirmText: t("Remove cover"),
    });
    if (!ok) return;
    setBusy(true);
    try { await deleteCover(rom.id); coverChanged(); setOpen(false); toast.success(t("Cover removed")); }
    catch (e) { toast.error(e.message || t("Failed to remove cover")); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (busy) return;
    const ok = await toast.confirm(t("Delete the ROM '{title}'?", { title }), {
      detail: t("Moves to trash (_trash) — recoverable."),
      confirmText: t("Delete (trash)"),
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try { await deleteRom(rom.id); onChanged?.(); setOpen(false); toast.success(t("Moved to trash")); }
    catch (e) { toast.error(e.message || t("Failed to delete")); }
    finally { setBusy(false); }
  }

  const koPatched = isKoreanPatched(rom);

  // Manually flip the 한글패치 flag (protected from future auto-scans). Used by the
  // corner badge (turn OFF) and the modal toggle (either direction).
  async function togglePatch() {
    if (busy) return;
    setBusy(true);
    try {
      await setRomLang(rom.id, !koPatched);
      onChanged?.();
      toast.success(!koPatched ? t("Marked as user-patched") : t("User-patch mark removed"));
    } catch (e) { toast.error(e.message || t("Failed to change")); }
    finally { setBusy(false); }
  }

  // Toggle favorite (★) — sorts to the front + shows a star on the cover.
  async function toggleFavorite(e) {
    e?.stopPropagation?.();
    if (busy) return;
    setBusy(true);
    try {
      await setFavorite(rom.id, !rom.favorite);
      onChanged?.();
    } catch (e) { toast.error(e.message || t("Failed to set favorite")); }
    finally { setBusy(false); }
  }

  // Set the cover's corner flag (baked into the device .img). Independent of the
  // 한글패치 toggle — purely which country flag shows on the cover.
  async function changeFlag(code) {
    if (busy || (rom.cover_flag || "") === (code || "")) return;
    setBusy(true);
    try {
      await setCoverFlag(rom.id, code);
      coverChanged();   // rebaked device .img → refresh preview + library
    } catch (e) {
      toast.error(e.message || t("Failed to set flag"));
    } finally { setBusy(false); }
  }

  // Homebrew only: opt this ROM file into the SD ZIP (default = cover only).
  async function changeSdInclude(include) {
    if (busy) return;
    setBusy(true);
    try {
      await setSdInclude(rom.id, include);
      onChanged?.();
    } catch (e) { toast.error(e.message || t("Failed to change")); }
    finally { setBusy(false); }
  }

  // Non-homebrew: keep the file in the library but drop it from the SD ZIP.
  async function toggleSdExclude() {
    if (busy) return;
    setBusy(true);
    try {
      await setSdExclude(rom.id, !rom.sd_exclude);
      onChanged?.();
    } catch (e) { toast.error(e.message || t("Failed to change")); }
    finally { setBusy(false); }
  }

  // Add/replace a data file on the card (e.g. smw_assets.dat). Same name = replace.
  async function addFile(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || busy) return;
    setBusy(true);
    try { await addRomFile(rom.id, f); onChanged?.(); toast.success(t("File added")); }
    catch (err) { toast.error(err.message || t("Failed to add file")); }
    finally { setBusy(false); }
  }
  async function removeFile(name) {
    if (busy) return;
    setBusy(true);
    try { await deleteRomFile(rom.id, name); onChanged?.(); toast.success(t("File deleted")); }
    catch (err) { toast.error(err.message || t("Failed to delete file")); }
    finally { setBusy(false); }
  }

  // Cover-state badge, pinned to the cover's bottom-right corner:
  // crop = hand-cropped for the device (original kept) · hand = manually uploaded
  // · image-off = no cover. Auto cover shows nothing.
  const statusBadge =
    rom.cover_status === "ok" && rom.cover_source === "crop" ? (
      <span className="cover-crop" title={t("Manually cropped for device (original kept)")}>
        <Crop size={12} strokeWidth={2.5} aria-hidden />
      </span>
    ) : rom.cover_status === "ok" && rom.cover_source === "manual" ? (
      <span className="cover-manual" title={t("Manually added cover (no auto-overwrite)")}>
        <Hand size={12} strokeWidth={2.5} aria-hidden />
      </span>
    ) : rom.cover_status !== "ok" ? (
      <span className="no-cover" title={t("No cover")}><ImageOff size={12} strokeWidth={2.5} aria-hidden /></span>
    ) : null;

  // IGDB score (0-100) pinned at the cover's bottom-right. NULL = not fetched,
  // -1 = fetched but unrated → both hidden. Color tiers by quality.
  const hasScore = rom.igdb_score != null && rom.igdb_score >= 0;
  const scoreBadge = hasScore ? (
    <span className={`cover-score ${scoreTier(rom.igdb_score)}`}
      title={`${t("IGDB rating")}: ${rom.igdb_score}/100${rom.igdb_votes ? ` · ${t("{n} votes", { n: rom.igdb_votes })}` : ""}`}>
      <span className="score-face" aria-hidden>{scoreFace(rom.igdb_score)}</span>{rom.igdb_score}
    </span>
  ) : null;

  return (
    <div className={`card ${rom.system_key === "pico8" && rom.pico8_compat === "broken" ? "card-broken" : ""} ${rom.sd_exclude ? "card-sd-out" : ""}`}
      style={{ borderTopColor: systemColor(rom.system_key) }}>
      <CoverSlot romId={rom.id} src={previewSrc} bust={coverV} alt={title}
        aspect={coverAspect(rom.system_key)} onActivate={openModal}
        badge={(scoreBadge || statusBadge) ? <>{statusBadge}{scoreBadge}</> : null}
        cornerBL={rom.sd_exclude
          ? <span className="sd-out" title={t("Excluded from the SD download (kept in library)")}>
              <HardDriveDownload size={11} strokeWidth={2.5} aria-hidden /> {t("Not on SD")}
            </span>
          : rom.system_key === "pico8" ? <Pico8Compat status={rom.pico8_compat} /> : null}
        gauge={rom.system_key === "pico8" && rom.pico8_mem_hint != null ? {
          pct: rom.pico8_mem_hint, cls: p8memLevel(rom.pico8_mem_hint).cls,
          title: `${t("Code size")}: ${t(p8memLevel(rom.pico8_mem_hint).label)} (${rom.pico8_mem_hint}%)`,
        } : null}
        status={rom.cover_status}
        overlay={
          <button type="button" className={`cover-fav ${rom.favorite ? "on" : ""}`} disabled={busy}
            onClick={toggleFavorite} title={rom.favorite ? t("Remove from favorites") : t("Add to favorites")}>
            {rom.favorite
              ? <Star size={14} strokeWidth={2.5} fill="currentColor" aria-hidden />
              : (rom.system_key ? <SystemIcon dirname={rom.system_key} size={14} /> : <Star size={14} strokeWidth={2.5} aria-hidden />)}
          </button>
        } />
      <div className="name">
        {isNewRom(rom) && (
          <span className="new-badge" title={t("Added today")}>NEW</span>
        )}
        {title}
        {rom.system_key === "homebrew" && dataFileCount > 0 && (
          <span className="file-count" title={t("{n} files", { n: dataFileCount })}>{dataFileCount}</span>
        )}
        {dupes.length > 0 && (
          <span className="dup-badge" title={t("{n} more rom(s) with identical content (hash)", { n: dupes.length })}>
            <Files size={11} strokeWidth={2.5} aria-hidden /> {t("Duplicate")}
          </span>
        )}
      </div>
      <div className="card-actions">
        {dl && (
          <button className="icon-btn" disabled={dlBusy} onClick={startDownload}
            title={t("Download (ROM + cover)")}>
            {dlBusy ? <Loader size={13} className="spin" strokeWidth={2.5} /> : <Download size={13} strokeWidth={2.5} />}
          </button>
        )}
        <button className="icon-btn" onClick={openModal} title={t("Edit / delete")}>
          <MoreHorizontal size={13} strokeWidth={2.5} />
        </button>
        {/* ▶ play sits at the FAR RIGHT so download/edit keep a fixed position on
           every card, whether or not the system is browser-playable. */}
        {runnable && (
          <button className="icon-btn play-btn" onClick={launch}
            title={isExperimental(rom.system_key) ? t("Run in browser (experimental)") : t("Run in browser")}>
            <Play size={13} strokeWidth={2.5} />
          </button>
        )}
      </div>

      {open && (
        <Modal title={title} onClose={() => { closeCropper(); setOpen(false); }}>
          {cropper ? (
            <CoverCropper src={cropper.src} aspect={coverAspect(rom.system_key)} busy={busy} onCancel={closeCropper} onDone={applyCrop} />
          ) : (
            <>
              <CoverCompare rom={rom} bust={coverV} onRecrop={rom.cover_status === "ok" ? reCrop : null} />

              {/* IGDB rating line — shown once the score has been fetched. */}
              {rom.igdb_score != null && (
                <div className="igdb-line">
                  {rom.igdb_score >= 0 ? (
                    <>
                      <span className={`cover-score ${scoreTier(rom.igdb_score)}`}>
                        <span className="score-face" aria-hidden>{scoreFace(rom.igdb_score)}</span>{rom.igdb_score}
                      </span>
                      <span className="muted">{t("IGDB rating")}: {rom.igdb_score}/100{rom.igdb_votes ? ` · ${t("{n} votes", { n: rom.igdb_votes })}` : ""}</span>
                    </>
                  ) : (
                    <span className="muted">{t("No IGDB rating")}</span>
                  )}
                </div>
              )}

              {/* Homebrew entries are fixed firmware launch templates — the .bin
                  name must stay exact, so no rename field (managed via file list). */}
              {rom.system_key !== "homebrew" && (
                <>
                  <label className="field-label">{t("Filename")}</label>
                  <div className="rename-row">
                    {rom.system_key && <span className="path-prefix">/roms/{rom.system_key}/</span>}
                    <input
                      className="text-input"
                      value={name}
                      disabled={busy}
                      spellCheck={false}
                      onChange={(e) => setName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && rename()}
                    />
                    <button className="btn" disabled={busy || !name.trim() || name.trim() === romBase} onClick={rename}>
                      <Pencil size={13} strokeWidth={2.5} /> {t("Change")}
                    </button>
                  </div>
                  {nameErr && <div className="badge failed">{nameErr}</div>}
                </>
              )}

              {rom.original_name && rom.original_name !== romBase && (
                <div className="orig-name-row" title={t("Original filename at upload — preserves No-Intro region/dump/version info")}>
                  <span className="orig-name-label">{t("Original name")}</span>
                  <code className="orig-name-val">{rom.original_name}</code>
                </div>
              )}

              {rom.patch_ver && (
                <div className="patch-ver-row" title={t("Korean-patch version parsed from the filename — used to tell newer vs older builds of the same game")}>
                  <span className="patch-ver-label">{t("Patch version")}</span>
                  <code className="patch-ver-val">{rom.patch_ver}</code>
                </div>
              )}

              {rom.content_hash && (
                <div className="hash-section">
                  <label className="field-label">{t("Content hash (SHA-256)")}</label>
                  <div className="hash-row">
                    <code className="hash-value" title={rom.content_hash}>{rom.content_hash}</code>
                    <button className="btn ghost hash-copy" disabled={busy} onClick={copyHash}
                      title={t("Copy hash")}>
                      {copied
                        ? <><Check size={13} strokeWidth={2.5} /> {t("Copied")}</>
                        : <><Copy size={13} strokeWidth={2.5} /> {t("Copy")}</>}
                    </button>
                  </div>
                  {dupes.length > 0 && (
                    <div className="hash-dups" title={t("Byte-for-byte identical files — likely the same game with a different subtitle")}>
                      <AlertTriangle size={13} strokeWidth={2.5} aria-hidden />
                      <span>{t("{n} rom(s) with identical content", { n: dupes.length })}: {dupes.map((d) => d.name).join(", ")}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="lang-row">
                <label className="lang-toggle" title={t("Mark whether this ROM has a user patch (translation, hack, etc.) applied")}>
                  <input type="checkbox" checked={koPatched} disabled={busy} onChange={togglePatch} />
                  <span>{t("User patch applied")}</span>
                </label>
                <button type="button" className={`fav-toggle ${rom.favorite ? "on" : ""}`} disabled={busy}
                  onClick={toggleFavorite} title={t("Favorite (sorted to the front)")}>
                  <Star size={14} strokeWidth={2.5} fill={rom.favorite ? "currentColor" : "none"} aria-hidden />
                  <span>{t("Favorite")}</span>
                </button>
                {rom.system_key !== "homebrew" && (
                  <button type="button" className={`fav-toggle sd-toggle ${rom.sd_exclude ? "on" : ""}`} disabled={busy}
                    onClick={toggleSdExclude}
                    title={t("Keep this ROM in the library but exclude it from the SD download")}>
                    <HardDriveDownload size={14} strokeWidth={2.5} aria-hidden />
                    <span>{rom.sd_exclude ? t("Excluded from SD") : t("Exclude from SD")}</span>
                  </button>
                )}
              </div>

              {rom.system_key !== "homebrew" && (
                <div className="flag-row">
                  <span className="flag-row-label" title={t("Flag shown at the cover's top-right — independent of the Korean-patch toggle")}>{t("Cover flag")}</span>
                  <div className="flag-opts" role="group" aria-label={t("Cover flag")}>
                    {FLAG_OPTIONS.map((opt) => {
                      const on = (rom.cover_flag || "") === opt.code;
                      const url = langFlagUrl(opt.code);
                      return (
                        <button key={opt.code || "none"} type="button"
                          className={`flag-opt ${on ? "on" : ""} ${opt.code ? "" : "flag-opt-none"}`}
                          disabled={busy} onClick={() => changeFlag(opt.code)}
                          title={t(opt.label)} aria-pressed={on}>
                          {url ? <img src={url} alt={t(opt.label)} /> : <X size={13} strokeWidth={2.5} aria-hidden />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {rom.system_key === "pico8" && <Pico8CompatEditor rom={rom} onChanged={onChanged} />}

              {rom.system_key === "homebrew" && (
                <div className="file-list">
                  <label className="field-label">{t("Files ({n})", { n: dataFileCount })}</label>
                  <ul className="files">
                    <li className="file-row">
                      <span className="file-name">{rom.stored_name}</span>
                      <label className="file-sd" title={t("Check to include this executable (.bin) in the SD download (shared library — applies to everyone)")}>
                        <input type="checkbox" checked={!!rom.sd_include} disabled={busy}
                          onChange={(e) => changeSdInclude(e.target.checked)} />
                        {t("Include in SD")}
                      </label>
                    </li>
                    {extraFiles.map((f) => (
                      <li className="file-row" key={f.name}>
                        <span className="file-name">{f.name}</span>
                        <span className="file-size">{formatBytes(f.size)}</span>
                        <button className="icon-btn" disabled={busy} onClick={() => removeFile(f.name)} title={t("Delete")}>
                          <Trash2 size={12} strokeWidth={2.5} />
                        </button>
                      </li>
                    ))}
                  </ul>
                  <p className="hb-bin-note">
                    {t("⚠ The executable (.bin) is paired with its firmware build. Use the .bin extracted from the firmware you flashed to your device — mismatched versions will crash on launch.")}
                  </p>
                  <input ref={dataFileRef} type="file" hidden onChange={addFile} />
                </div>
              )}

              {/* Homebrew: data-file add/replace + download share one 50/50 row */}
              {rom.system_key === "homebrew" && (
                <div className="modal-actions">
                  <button className="btn ghost" disabled={busy} onClick={() => dataFileRef.current?.click()}
                    title={t("Add a data file (.dat, etc.); uploading the same name replaces it.")}>
                    <Upload size={13} strokeWidth={2.5} /> {t("Add / replace data file")}
                  </button>
                  {dl && (
                    <button className="btn ghost" disabled={busy || dlBusy} onClick={startDownload}
                      title={t("Download ROM + cover ZIP")}>
                      {dlBusy ? <Loader size={13} className="spin" strokeWidth={2.5} /> : <Download size={13} strokeWidth={2.5} />} {t("Download")}
                    </button>
                  )}
                </div>
              )}

              {(runnable || rom.system_key !== "homebrew") && (
                <div className="modal-actions">
                  {runnable && (
                    <button className="btn play" disabled={busy} onClick={launch}
                      title={isExperimental(rom.system_key) ? t("Run directly in browser (experimental support)") : t("Run directly in browser")}>
                      <Play size={13} strokeWidth={2.5} /> {t("Run in browser")}
                    </button>
                  )}
                  {rom.system_key !== "homebrew" && (
                    <button className="btn ghost" disabled={busy} onClick={() => romFileRef.current?.click()}
                      title={t("Replace the ROM file itself with another (keeps name and cover)")}>
                      <Upload size={13} strokeWidth={2.5} /> {t("Replace file")}
                    </button>
                  )}
                  {dl && rom.system_key !== "homebrew" && (
                    <button className="btn ghost" disabled={busy || dlBusy} onClick={startDownload}
                      title={t("Download ROM + cover ZIP")}>
                      {dlBusy ? <Loader size={13} className="spin" strokeWidth={2.5} /> : <Download size={13} strokeWidth={2.5} />} {t("Download")}
                    </button>
                  )}
                </div>
              )}
              <input ref={romFileRef} type="file" hidden onChange={replaceFile} />

              <CoverSearch rom={rom} onPick={pickIgdb} />

              <div className="modal-actions">
                <button className="btn" disabled={busy} onClick={() => fileRef.current?.click()}>
                  <ImagePlus size={13} strokeWidth={2.5} /> {t("Upload")}
                </button>
                <button className="btn ghost" disabled={busy} onClick={removeCover}>
                  <ImageOff size={13} strokeWidth={2.5} /> {t("Remove cover")}
                </button>
                <button className="btn danger" disabled={busy} onClick={remove}>
                  <Trash2 size={13} strokeWidth={2.5} /> {t("Delete")}
                </button>
              </div>
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={replaceCover} />
            </>
          )}
        </Modal>
      )}

      {playing && <EmulatorOverlay rom={rom} onClose={() => setPlaying(false)} />}
    </div>
  );
}

// Music card: name + inline MP3 player + download + delete.
// Music library — one sticky player up top, a clickable track list below (a track
// row → loads + plays in that single player). Music app style, not per-card players.
export function MusicList({ tracks, onChanged }) {
  const toast = useToast();
  const t = useT();
  const [curId, setCurId] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const cur = tracks.find((tr) => tr.id === curId);

  async function remove(track, e) {
    e.stopPropagation();
    if (busyId) return;
    if (!(await toast.confirm(t("Delete '{name}'?", { name: track.original_name || track.stored_name }), { confirmText: t("Delete") }))) return;
    setBusyId(track.id);
    try {
      await deleteMusic(track.id);
      if (curId === track.id) setCurId(null);
      onChanged?.();
    } catch (err) { toast.error(err.message); } finally { setBusyId(null); }
  }

  return (
    <div className="music-lib">
      <div className="music-bar">
        <div className="music-now">
          <Music size={13} strokeWidth={2.5} aria-hidden />
          <span>{cur ? (cur.original_name || cur.stored_name) : t("Tap a track to play")}</span>
        </div>
        {/* key reloads the element on track change → autoplay the picked track.
            stream endpoint (not download) so the scrubber/seek works. */}
        <audio key={cur?.id || "none"} className="music-audio" controls autoPlay
          src={cur ? streamMusicUrl(cur.id) : undefined} />
      </div>
      <div className="music-list">
        {tracks.map((tr) => (
          <div key={tr.id} className={`music-row ${tr.id === curId ? "on" : ""}`} onClick={() => setCurId(tr.id)}>
            <span className="music-row-thumb">
              <Music size={13} strokeWidth={2.5} aria-hidden />
              <img src={musicCoverUrl(tr.id)} alt="" loading="lazy"
                onError={(e) => { e.currentTarget.style.display = "none"; }} />
            </span>
            {tr.id === curId
              ? <span className="music-row-icon playing"><Play size={11} strokeWidth={3} aria-hidden /></span>
              : <span className="music-row-icon"><Play size={11} strokeWidth={2.5} aria-hidden /></span>}
            <span className="music-row-name" title={tr.original_name || tr.stored_name}>{tr.original_name || tr.stored_name}</span>
            {tr.size_bytes != null && <span className="music-row-size">{formatBytes(tr.size_bytes)}</span>}
            <a className="icon-btn" href={downloadMusicUrl(tr.id)} download title={t("Download")} onClick={(e) => e.stopPropagation()}>
              <Download size={12} strokeWidth={2.5} />
            </a>
            <button className="icon-btn danger" disabled={busyId === tr.id} title={t("Delete")} onClick={(e) => remove(tr, e)}>
              <Trash2 size={12} strokeWidth={2.5} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// Video card — YouTube-style: 16:9 thumbnail with an inline player, title, and a
// ⋯ detail modal (format + delete). Plays the browser .mp4 preview, not the .avi.
export function VideoCard({ video, onChanged }) {
  const toast = useToast();
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [playing, setPlaying] = useState(false);   // load the <video> only on click
  const dl = downloadVideoUrl(video.id);
  const prev = videoPreviewUrl(video.id);
  const thumb = videoThumbUrl(video.id);
  const title = video.original_name || video.avi_name;

  async function remove() {
    if (busy) return;
    if (!(await toast.confirm(t("Delete '{title}'?", { title }), { confirmText: t("Delete") }))) return;
    setBusy(true);
    try { await deleteVideo(video.id); onChanged?.(); }
    catch (e) { toast.error(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="media-card">
      <div className="media-thumb">
        {playing
          ? <video className="media-player" controls autoPlay src={prev} />
          : (
            <button type="button" className="media-thumb-btn" onClick={() => setPlaying(true)} aria-label={t("Play")}>
              <img className="media-cover" src={thumb} alt="" loading="lazy" />
              <span className="media-play"><Play size={30} strokeWidth={2.5} aria-hidden /></span>
            </button>
          )}
        <span className="media-kind"><Film size={11} strokeWidth={2.5} aria-hidden /> {t("Video")}</span>
        {video.size_bytes != null && <span className="media-size">{formatBytes(video.size_bytes)}</span>}
      </div>
      <div className="media-meta">
        <div className="media-title" title={title}>{title}</div>
        <div className="media-actions">
          <button className="icon-btn" onClick={() => setOpen(true)} title={t("Details")}><MoreHorizontal size={13} strokeWidth={2.5} /></button>
          {dl && <a className="icon-btn" href={dl} download title={t("Download (.avi)")}><Download size={13} strokeWidth={2.5} /></a>}
          <button className="icon-btn danger" onClick={remove} disabled={busy} title={t("Delete")}><Trash2 size={13} strokeWidth={2.5} /></button>
        </div>
      </div>
      {open && (
        <Modal title={title} onClose={() => setOpen(false)}>
          <video className="media-detail-player" controls autoPlay poster={thumb} src={prev} />
          <dl className="media-detail-info">
            <dt>{t("Original")}</dt><dd>{video.original_name || "—"}</dd>
            <dt>{t("Device file")}</dt><dd>{video.avi_name}</dd>
            <dt>{t("Format")}</dt><dd>{t("MJPEG · AVI · 320×240 · 20fps · mono MP3 (for device)")}</dd>
            <dt>{t("Size")}</dt><dd>{video.size_bytes != null ? formatBytes(video.size_bytes) : "—"}</dd>
          </dl>
          <div className="modal-actions">
            {dl && <a className="btn ghost" href={dl} download><Download size={13} strokeWidth={2.5} /> {t("Download (.avi)")}</a>}
            <button className="btn danger" onClick={() => { setOpen(false); remove(); }}><Trash2 size={13} strokeWidth={2.5} /> {t("Delete")}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
