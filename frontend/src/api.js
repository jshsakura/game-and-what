// API client. Single SHARED library — every visitor uses the same workspace,
// so what anyone uploads is visible to everyone (no per-browser isolation).
import { DEMO, PLACEHOLDER_COVER } from "./demo.js";

const SESSION_ID = "public";

export function getSessionId() {
  return SESSION_ID;
}

// Kept for call-site compatibility; always targets the shared workspace.
async function withSession(makeRequest) {
  return makeRequest(SESSION_ID);
}

// POST a FormData via XHR so we get real UPLOAD progress (fetch can't report it).
// onProgress(loaded, total) fires as bytes go up. Resolves the parsed JSON body.
function xhrUpload(url, form, onProgress) {
  if (DEMO) return Promise.reject(new Error("Demo mode — install via Docker to enable uploads."));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded, e.total);
      };
    }
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText || "{}"); } catch (_) { /* keep {} */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body.detail || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Upload failed due to a network error"));
    xhr.send(form);
  });
}

export async function getSystems() {
  const res = await fetch("/api/systems");
  if (!res.ok) throw new Error("Failed to load platform list");
  return (await res.json()).systems;
}

export async function getHealth() {
  const res = await fetch("/api/health");
  return res.ok ? res.json() : { status: "down", ffmpeg: false };
}

// Runtime feature flags (korean_mode gates the Korea-specific UI).
export async function getConfig() {
  try {
    const res = await fetch("/api/config");
    return res.ok ? res.json() : { korean_mode: false };
  } catch (_) {
    return { korean_mode: false };
  }
}

// Send at most this many files per request. One giant multipart (1000s of files)
// makes the browser build a huge body and the server parse it all at once — it
// stalls. Batching keeps each request small/fast and makes progress real
// (files-completed, not just bytes-of-one-giant-body).
const UPLOAD_BATCH = 100;

function postRomBatch(systemKey, files, onProgress) {
  const form = new FormData();
  form.append("system", systemKey);
  for (const f of files) form.append("files", f);
  return xhrUpload(`/api/sessions/${SESSION_ID}/roms`, form, onProgress);
}

export async function uploadRoms(systemKey, files, onProgress) {
  const arr = Array.from(files);
  if (arr.length <= UPLOAD_BATCH) {
    return postRomBatch(systemKey, arr, onProgress);
  }
  // Upload in sequential batches; progress = files completed / total.
  const total = arr.length;
  let done = 0;
  let stored = 0;
  const results = [];
  for (let i = 0; i < total; i += UPLOAD_BATCH) {
    const chunk = arr.slice(i, i + UPLOAD_BATCH);
    const res = await postRomBatch(systemKey, chunk, (loaded, totalBytes) => {
      const frac = totalBytes ? loaded / totalBytes : 0;
      onProgress?.(done + chunk.length * frac, total);   // smooth within a batch
    });
    done += chunk.length;
    stored += res.stored || 0;
    if (res.results) results.push(...res.results);
    onProgress?.(done, total);
  }
  return { session_id: SESSION_ID, stored, results };
}

// Goodtools/No-Intro alt-or-bad dump tags ([a1]/[b1]/[h1]/[o1]/[t1]/[f1]/[p1]).
const ALT_DUMP_RE = /\[(?:a|b|h|o|t|f|p)\d*\]/i;
const SIDECAR_IMG_RE = /\.(png|jpe?g|bmp)$/i;
const extOf = (name) => { const i = name.lastIndexOf("."); return i >= 0 ? name.slice(i + 1).toLowerCase() : ""; };

// Smart romset upload: keep only accepted-extension ROMs (skipping alt/bad dumps),
// then pair each ROM with its sidecar cover image ("<name>.col.png" / "<name>.png")
// and set it as that ROM's cover. Other files (.sta save states, etc.) are ignored.
export async function uploadRomset(systemKey, exts, files, onProgress) {
  const arr = Array.from(files);
  const roms = arr.filter((f) => exts.includes(extOf(f.name)) && !ALT_DUMP_RE.test(f.name));
  const skippedAlt = arr.filter((f) => exts.includes(extOf(f.name)) && ALT_DUMP_RE.test(f.name)).length;

  // images keyed by base name (strip .png, then a trailing rom-ext like .col)
  const imgMap = new Map();
  for (const f of arr) {
    if (!SIDECAR_IMG_RE.test(f.name)) continue;
    let base = f.name.replace(SIDECAR_IMG_RE, "");
    if (exts.includes(extOf(base))) base = base.slice(0, base.lastIndexOf("."));
    imgMap.set(base.toLowerCase(), f);
  }

  if (!roms.length) return { stored: 0, results: [], covers: 0, skippedAlt, ignored: arr.length };
  const res = await uploadRoms(systemKey, roms, onProgress);

  const romExtRe = new RegExp(`\\.(${exts.join("|")})$`, "i");
  let covers = 0;
  for (const r of (res.results || [])) {
    if (!r.ok) continue;
    const img = imgMap.get(r.name.replace(romExtRe, "").toLowerCase());
    if (img) {
      try { await uploadCover(r.id, img); covers++; } catch (_) { /* keep going */ }
    }
  }
  return { ...res, covers, skippedAlt };
}

export async function uploadVideo(file, onProgress, { mode = "fit" } = {}) {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", mode);  // fit (letterbox) | fill (crop) | stretch (distort)
  return xhrUpload(`/api/sessions/${SESSION_ID}/videos`, form, onProgress);
}

// MP3 → /music (no conversion; the firmware plays it directly).
export async function uploadMusic(file, onProgress) {
  const form = new FormData();
  form.append("file", file);
  return xhrUpload(`/api/sessions/${SESSION_ID}/music`, form, onProgress);
}


export async function uploadCover(romId, file, crop) {
  const res = await withSession((sid) => {
    const form = new FormData();
    form.append("file", file);
    if (crop) form.append("crop", JSON.stringify(crop));
    return fetch(`/api/sessions/${sid}/roms/${romId}/cover`, { method: "POST", body: form });
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Cover upload failed");
  return res.json();
}

export function coverUrl(romId) {
  if (DEMO) return PLACEHOLDER_COVER;
  const sid = getSessionId();
  // cache-bust so a freshly uploaded cover shows immediately
  return sid ? `/api/sessions/${sid}/roms/${romId}/cover` : null;
}

// The RAW device .img (fixed size) — what the hardware actually displays.
export function deviceCoverUrl(romId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/roms/${romId}/cover?device=1` : null;
}

// The UNTOUCHED full original art (crop-tool source) — never the cropped display.
export function originalCoverUrl(romId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/roms/${romId}/cover?full=1` : null;
}

// Force-download a cover as a file. variant: "device" (.img) | "original" (full art).
export function coverDownloadUrl(romId, variant = "device") {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/roms/${romId}/cover/download?variant=${variant}` : null;
}

export async function getJob(jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) throw new Error("Failed to get job status");
  return res.json();
}

export async function getLibrary() {
  const res = await withSession((sid) => fetch(`/api/sessions/${sid}/library`));
  if (!res.ok) throw new Error("Failed to load library");
  return res.json();
}

// Activity feed — recent library changes (uploads, renames, PICO-8 compat…),
// newest-first. Returns { events: [...] }.
export async function getEvents(limit = 50) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/events?limit=${encodeURIComponent(limit)}`));
  if (!res.ok) throw new Error("Failed to load activity");
  return res.json();
}

// Undo a deletion from the feed: restore the ROM's files from _trash + DB row.
export async function restoreEvent(eventId) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/events/${eventId}/restore`, { method: "POST" }));
  if (!res.ok) throw new Error((await res.json()).detail || "Restore failed");
  return res.json();
}

export function downloadRomUrl(romId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/roms/${romId}/download` : null;
}

// Raw ROM bytes (no zip/cover) — for the in-browser emulator to load directly.
export function romFileUrl(romId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/roms/${romId}/rom` : null;
}

export function downloadVideoUrl(videoId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/videos/${videoId}/download` : null;
}

export function downloadMusicUrl(musicId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/music/${musicId}/download` : null;
}

// 16:9 thumbnail + browser-playable .mp4 preview for a video (built lazily server-side).
export function videoThumbUrl(videoId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/videos/${videoId}/thumb` : null;
}
export function videoPreviewUrl(videoId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/videos/${videoId}/preview` : null;
}
// Embedded MP3 album art (404 if none → card falls back to an icon).
export function musicCoverUrl(musicId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/music/${musicId}/cover` : null;
}
// Range-capable MP3 stream for the in-app player (seek/scrub works, unlike download).
export function streamMusicUrl(musicId) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/music/${musicId}/stream` : null;
}

export async function igdbSearch(query, system) {
  const params = new URLSearchParams({ q: query });
  if (system) params.set("system", system);
  const res = await fetch(`/api/igdb/search?${params}`);
  if (!res.ok) throw new Error("IGDB search failed");
  return res.json();
}

export async function tgdbSearch(query, system) {
  const params = new URLSearchParams({ q: query });
  if (system) params.set("system", system);
  const res = await fetch(`/api/tgdb/search?${params}`);
  if (!res.ok) throw new Error("TheGamesDB search failed");
  return res.json();
}

export async function sgdbSearch(query, system) {
  const params = new URLSearchParams({ q: query });
  if (system) params.set("system", system);
  const res = await fetch(`/api/sgdb/search?${params}`);
  if (!res.ok) throw new Error("SteamGridDB search failed");
  return res.json();
}

export async function setCoverFromUrl(romId, url, crop) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/cover/from-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(crop ? { url, crop } : { url }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to set cover");
  return res.json();
}

// Re-pick the crop region of the EXISTING cover (no re-download). crop=null resets.
export async function recropCover(romId, crop) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/cover/recrop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(crop ? { crop } : {}),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to adjust cover position");
  return res.json();
}

export async function deleteCover(romId) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/cover`, { method: "DELETE" }));
  if (!res.ok) throw new Error("Failed to remove cover");
  return res.json();
}

export async function renameRom(romId, name) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Rename failed");
  return res.json();
}

export async function deleteRom(romId) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}`, { method: "DELETE" }));
  if (!res.ok) throw new Error("Failed to delete");
  return res.json();
}

// Firmware update file (single retro-go_update.bin → SD root).
export async function getFirmware() {
  const res = await fetch(`/api/sessions/${SESSION_ID}/firmware`);
  if (!res.ok) throw new Error("Failed to load firmware info");
  return res.json();
}

export async function uploadFirmware(file, onProgress) {
  const form = new FormData();
  form.append("file", file);
  return xhrUpload(`/api/sessions/${SESSION_ID}/firmware`, form, onProgress);
}

export function downloadFirmwareUrl() {
  return `/api/sessions/${SESSION_ID}/firmware/download`;
}

// Extra passthrough files → SD root at the given path (e.g. bios/nes/disksys.rom).
export async function getExtra() {
  const res = await fetch(`/api/sessions/${SESSION_ID}/extra`);
  if (!res.ok) throw new Error("Failed to load extra file list");
  return res.json();
}
export async function uploadExtra(file, path, onProgress) {
  const form = new FormData();
  form.append("file", file);
  form.append("path", path);
  return xhrUpload(`/api/sessions/${SESSION_ID}/extra`, form, onProgress);
}
export async function deleteExtra(path) {
  const res = await fetch(`/api/sessions/${SESSION_ID}/extra?path=${encodeURIComponent(path)}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete");
  return res.json();
}
export function extraDownloadUrl(path) {
  return `/api/sessions/${SESSION_ID}/extra/download?path=${encodeURIComponent(path)}`;
}

export async function deleteFirmware() {
  const res = await fetch(`/api/sessions/${SESSION_ID}/firmware`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete");
  return res.json();
}

// Swap a ROM's underlying binary, keeping its name/cover/slot.
export async function replaceRomFile(romId, file) {
  const res = await withSession((sid) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`/api/sessions/${sid}/roms/${romId}/replace`, { method: "POST", body: form });
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "File replace failed");
  return res.json();
}

export async function deleteMusic(musicId) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/music/${musicId}`, { method: "DELETE" }));
  if (!res.ok) throw new Error("Failed to delete");
  return res.json();
}

export async function deleteVideo(videoId) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/videos/${videoId}`, { method: "DELETE" }));
  if (!res.ok) throw new Error("Failed to delete");
  return res.json();
}

// DATA — scratch/reference files (excluded from the SD zip).
export async function getData() {
  const res = await withSession((sid) => fetch(`/api/sessions/${sid}/data`));
  if (!res.ok) throw new Error("Failed to load data files");
  return res.json();
}

export async function uploadData(files) {
  const res = await withSession((sid) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    return fetch(`/api/sessions/${sid}/data`, { method: "POST", body: form });
  });
  if (!res.ok) throw new Error("Data upload failed");
  return res.json();
}

export async function deleteData(name) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/data/${encodeURIComponent(name)}`, { method: "DELETE" }));
  if (!res.ok) throw new Error("Failed to delete");
  return res.json();
}

export function dataDownloadUrl(name) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/data/${encodeURIComponent(name)}/download` : null;
}

// gamelist.xml → bulk Korean rename of matching library rom files.
export async function gamelistPreview(filename) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/gamelist/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Preview failed");
  return res.json();
}

export async function gamelistApply(filename) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/gamelist/apply`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Apply failed");
  return res.json();
}

// Manually override a rom's Korean-patch flag. Detection is otherwise automatic
// (upload-time + startup backfill), so there is no scan/sync call here.
export async function setRomLang(romId, isKoreanPatched) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/lang`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_korean_patched: isKoreanPatched }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to change patch mark");
  return res.json();
}

// Set the cover's corner flag/country EXPLICITLY (independent of Korean patch).
// coverFlag = "ko"|"ja"|"en"|... or "" / null to clear. Re-bakes the device .img.
export async function setCoverFlag(romId, coverFlag) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/cover/flag`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cover_flag: coverFlag || null }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to change flag");
  return res.json();
}

// Attach / replace an extra data file on a card (e.g. smw_assets.dat next to the
// read-only .bin template). Replacing = upload a file with the same name.
export async function addRomFile(romId, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/files`, { method: "POST", body: form }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to add file");
  return res.json();
}

// Remove an extra data file from a card (the .bin template is never touched).
export async function deleteRomFile(romId, name) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/files/${encodeURIComponent(name)}`, { method: "DELETE" }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to delete file");
  return res.json();
}

// Opt a homebrew ROM into the SD ZIP (its ROM file, not just the cover).
export async function setSdInclude(romId, include) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/sd-include`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include: !!include }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to set SD include");
  return res.json();
}

// Opt a (non-homebrew) ROM OUT of the SD ZIP without deleting it.
export async function setSdExclude(romId, exclude) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/sd-exclude`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exclude: !!exclude }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to set SD exclude");
  return res.json();
}

// Mark/unmark a rom as favorite (★) — UI sort + cover star.
export async function setFavorite(romId, favorite) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/favorite`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ favorite: !!favorite }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to set favorite");
  return res.json();
}

// Manually set a PICO-8 cart's real-device (G&W) compatibility.
// status: "good" | "partial" | "broken" | null (null clears → untested).
export async function setPico8Compat(romId, status) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/pico8-compat`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: status || null }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to set compatibility status");
  return res.json();
}

// Batch-fetch IGDB covers for roms missing one (optionally one system).
// force=true RE-fetches auto covers too (regenerates previews); manual covers kept.
export async function autocover(system, force = false) {
  const body = {};
  if (system) body.system = system;
  if (force) body.force = true;
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/autocover`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Auto-cover failed");
  return res.json();
}

// IGDB fill for roms still without a Korean name: rename (if IGDB has a Korean
// alt name) + cover. Returns counts + the list IGDB couldn't find.
export async function autoresolve(system) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/autoresolve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(system ? { system } : {}),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Auto-resolve failed");
  return res.json();
}

export function packageUrl(system) {
  const sid = getSessionId();
  if (!sid) return null;
  return system
    ? `/api/sessions/${sid}/package?system=${encodeURIComponent(system)}`
    : `/api/sessions/${sid}/package`;
}

// Estimated on-SD byte size of the (optional single-system) package.
export async function packageSize(system) {
  const sid = getSessionId();
  if (!sid) return null;
  const q = system ? `?system=${encodeURIComponent(system)}` : "";
  const res = await fetch(`/api/sessions/${sid}/package/size${q}`);
  if (!res.ok) return null;
  return (await res.json()).bytes;
}

// Human-readable byte size (KB/MB/GB/TB).
export function formatBytes(n) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB", "PB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}
