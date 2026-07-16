// API client. Single SHARED library — every visitor uses the same workspace,
// so what anyone uploads is visible to everyone (no per-browser isolation).
import { DEMO, demoCoverUrl } from "./demo.js";

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
// How long an upload may make NO progress before we call it dead.
//
// Not a total timeout — a real upload legitimately takes minutes, and killing it on a clock
// would break the thing we are trying to protect. This watches for a STALL: a request the
// edge has quietly swallowed sits at "(pending)" forever, sending nothing and receiving
// nothing, and the UI used to sit there with it. A failure has to look like a failure.
const UPLOAD_STALL_MS = 60_000;

function xhrUpload(url, form, onProgress) {
  if (DEMO) return Promise.reject(new Error("Demo mode — install via Docker to enable uploads."));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);

    let lastMove = Date.now();
    let sentAll = false;
    const watchdog = setInterval(() => {
      if (Date.now() - lastMove < UPLOAD_STALL_MS) return;
      clearInterval(watchdog);
      xhr.abort();
      // Two different silences, and the difference tells you where to look.
      reject(new Error(sentAll
        ? "The server stopped responding after the files were sent. Try fewer files at once."
        : "The upload stopped making progress — it may have been blocked before reaching the server (a proxy/CDN body-size limit does this). Try fewer files at once."));
    }, 5_000);
    const settle = () => clearInterval(watchdog);

    xhr.upload.onprogress = (e) => {
      lastMove = Date.now();
      if (e.lengthComputable) {
        sentAll = e.loaded >= e.total;
        onProgress?.(e.loaded, e.total);
      }
    };
    xhr.onprogress = () => { lastMove = Date.now(); };   // the response is coming back

    xhr.onload = () => {
      settle();
      let body = {};
      try { body = JSON.parse(xhr.responseText || "{}"); } catch (_) { /* keep {} */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else if (xhr.status === 413) {
        reject(new Error("The request was too large for the server or its proxy. Try fewer files at once."));
      } else reject(new Error(body.detail || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => { settle(); reject(new Error("Upload failed due to a network error")); };
    xhr.onabort = () => settle();
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

// Runtime feature flags (korean_mode gates the Korea-specific UI,
// experimental_mode the fork-firmware extras — MEDIA tab, extra systems).
export async function getConfig() {
  const fallback = { korean_mode: false, experimental_mode: false, cover_sources: { libretro: true, igdb: false, tgdb: false, sgdb: false } };
  try {
    const res = await fetch("/api/config");
    return res.ok ? res.json() : fallback;
  } catch (_) {
    return fallback;
  }
}

// Send at most this many files per request. One giant multipart (1000s of files)
// makes the browser build a huge body and the server parse it all at once — it
// stalls. Batching keeps each request small/fast and makes progress real
// (files-completed, not just bytes-of-one-giant-body).
const UPLOAD_BATCH = 100;

// …and at most this many BYTES, which is the cap that actually bites. This app is served
// through Cloudflare, and Cloudflare rejects a request body over 100 MB at the edge — the
// server never sees it, so nothing in our logs explains it and the browser just sits at
// "uploading" until it dies. A count cap does not help: 100 GBA roms is ~1.6 GB in ONE
// request. Batch by size and every request stays comfortably under the edge's limit.
const UPLOAD_BATCH_BYTES = 80 * 1024 * 1024;

// A file this big cannot cross the edge in one request at all, so it goes up in chunks.
// The backend has had a full resumable-upload API since forever (POST /uploads → PUT
// /chunk → POST /complete) and nothing was calling it.
const CHUNK_SIZE = 8 * 1024 * 1024;          // server caps a chunk at 10 MB

async function uploadRomChunked(systemKey, file, onProgress) {
  const sid = SESSION_ID;
  const init = await fetch(`/api/sessions/${sid}/uploads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, total_size: file.size, kind: "rom", system: systemKey }),
  });
  if (!init.ok) throw new Error((await init.json().catch(() => ({}))).detail || "Upload init failed");
  const { upload_id: id } = await init.json();

  for (let i = 0, sent = 0; sent < file.size; i++) {
    const blob = file.slice(sent, Math.min(sent + CHUNK_SIZE, file.size));
    const form = new FormData();
    form.append("file", blob, file.name);
    const res = await fetch(`/api/sessions/${sid}/uploads/${id}/chunk?index=${i}`,
      { method: "PUT", body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Chunk failed");
    sent += blob.size;
    onProgress?.(sent, file.size);
  }

  const done = await fetch(`/api/sessions/${sid}/uploads/${id}/complete`, { method: "POST" });
  if (!done.ok) throw new Error((await done.json().catch(() => ({}))).detail || "Upload failed");
  return done.json();
}

// Batches that respect BOTH caps. A file bigger than the byte cap goes on its own — one
// oversized request is a failure we can report, where bundling it guarantees one.
function uploadBatches(files) {
  const batches = [];
  let batch = [];
  let bytes = 0;
  for (const f of files) {
    if (batch.length && (batch.length >= UPLOAD_BATCH || bytes + f.size > UPLOAD_BATCH_BYTES)) {
      batches.push(batch);
      batch = [];
      bytes = 0;
    }
    batch.push(f);
    bytes += f.size;
  }
  if (batch.length) batches.push(batch);
  return batches;
}

function postRomBatch(systemKey, files, onProgress) {
  const form = new FormData();
  form.append("system", systemKey);
  for (const f of files) form.append("files", f);
  return xhrUpload(`/api/sessions/${SESSION_ID}/roms`, form, onProgress);
}

export async function uploadRoms(systemKey, files, onProgress) {
  const arr = Array.from(files);
  const batches = uploadBatches(arr);
  if (batches.length <= 1 && arr.every((f) => f.size <= UPLOAD_BATCH_BYTES)) {
    return postRomBatch(systemKey, arr, onProgress);
  }
  // Upload in sequential batches; progress = files completed / total.
  const total = arr.length;
  let done = 0;
  let stored = 0;
  const results = [];
  for (const chunk of batches) {
    // A single file too big for one request goes up in chunks instead.
    if (chunk.length === 1 && chunk[0].size > UPLOAD_BATCH_BYTES) {
      try {
        const res = await uploadRomChunked(systemKey, chunk[0], (loaded, totalBytes) => {
          onProgress?.(done + (totalBytes ? loaded / totalBytes : 0), total);
        });
        stored += res.stored || 0;
        if (res.results) results.push(...res.results);
      } catch (e) {
        results.push({ name: chunk[0].name, ok: false, error: e.message });
      }
      done += 1;
      onProgress?.(done, total);
      continue;
    }
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

// Folder-per-game upload for CD systems (PC Engine CD): a game is a .cue + many
// track files (or a single .chd), stored intact as ONE library entry.
//
// Each file is sent in its OWN request: the public tunnel (Cloudflare) caps a
// single request body at ~100 MB, but a whole CD is hundreds of MB. So we POST
// the .cue/.chd first (creates the entry), then stream each track separately —
// every request stays small. Progress aggregates bytes across all requests.
const EXT = (n) => (n.includes(".") ? n.split(".").pop().toLowerCase() : "");

export async function uploadCdFolder(systemKey, files, onProgress) {
  const sid = getSessionId();
  if (!sid) throw new Error("No session");
  const arr = Array.from(files);
  if (!arr.length) throw new Error("No files");

  // Primary = the .cue (preferred) or a single .chd — the entry is built on it.
  let primIdx = arr.findIndex((f) => EXT(f.name) === "cue");
  if (primIdx < 0) primIdx = arr.findIndex((f) => EXT(f.name) === "chd");
  if (primIdx < 0) throw new Error("No .cue or .chd found in the folder");

  const totalBytes = arr.reduce((s, f) => s + (f.size || 0), 0);
  let doneBytes = 0;
  const report = (loaded) => onProgress?.(doneBytes + loaded, totalBytes);

  // 1) Create the game from the .cue/.chd.
  const primary = arr[primIdx];
  const form = new FormData();
  form.append("system", systemKey);
  form.append("files", primary);
  form.append("paths", JSON.stringify([primary.webkitRelativePath || primary.name]));
  const created = await xhrUpload(`/api/sessions/${sid}/roms/cdfolder`, form, report);
  doneBytes += primary.size || 0;
  const res = created.results?.[0];
  if (!res?.ok) return created;   // duplicate / error → nothing more to send

  // 2) Stream each remaining track file as its own small request.
  for (let i = 0; i < arr.length; i++) {
    if (i === primIdx) continue;
    const tf = new FormData();
    tf.append("files", arr[i]);
    await xhrUpload(`/api/sessions/${sid}/roms/${res.id}/cdtracks`, tf, report);
    doneBytes += arr[i].size || 0;
  }
  onProgress?.(totalBytes, totalBytes);
  return { ...created, results: [{ ...res, tracks: arr.length - 1 }] };
}

// Systems managed as a folder-per-game (disc images: .cue + tracks, or .chd).
export const FOLDER_SYSTEMS = new Set(["pcecd"]);

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

// POST a FormData, resolve the response BODY as a Blob (for one-shot file
// downloads like the clock bg.gif — nothing is stored server-side).
function xhrUploadBlob(url, form, onProgress) {
  if (DEMO) return Promise.reject(new Error("Demo mode — install via Docker to enable uploads."));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.responseType = "blob";
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded, e.total);
      };
    }
    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) { resolve(xhr.response); return; }
      // error bodies are JSON even with responseType=blob — read the detail back
      let detail = `Convert failed (${xhr.status})`;
      try { detail = JSON.parse(await xhr.response.text()).detail || detail; } catch (_) { /* keep */ }
      reject(new Error(detail));
    };
    xhr.onerror = () => reject(new Error("Convert failed due to a network error"));
    xhr.send(form);
  });
}

// Image/video → a 320×240 clock background gif. Resolves the gif Blob to download
// (stateless: the user drops it at /clock/gif/bg.gif on the SD card).
export async function uploadClockBackground(file, onProgress, { mode = "fit", crop = "" } = {}) {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", mode);  // fit | fill | stretch | custom (user crop)
  if (crop) form.append("crop", crop);  // custom: "x,y,w,h" source fractions
  return xhrUploadBlob("/api/clock/background", form, onProgress);
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

export function coverUrl(romId, ver) {
  if (DEMO) return demoCoverUrl(romId);
  const sid = getSessionId();
  if (!sid) return null;
  // ver = the library's per-rom cover_ver token: it changes the moment the cover
  // (or its flag/crop) changes, so the browser refetches then — and reuses its
  // cache while it doesn't. Without it a re-baked/flagged cover shows the stale
  // cached image.
  const q = ver != null ? `?v=${encodeURIComponent(ver)}` : "";
  return `/api/sessions/${sid}/roms/${romId}/cover${q}`;
}

// The RAW device .img (fixed size) — what the hardware actually displays.
export function deviceCoverUrl(romId) {
  if (DEMO) return demoCoverUrl(romId);   // no backend on Pages — a real URL would 404 (broken <img>)
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/roms/${romId}/cover?device=1` : null;
}

// The UNTOUCHED full original art (crop-tool source) — never the cropped display.
export function originalCoverUrl(romId) {
  if (DEMO) return demoCoverUrl(romId);
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

// One track/data file from a CD game's folder (for in-browser CD play).
export function cdTrackUrl(romId, name) {
  const sid = getSessionId();
  return sid ? `/api/sessions/${sid}/roms/${romId}/cdfile?name=${encodeURIComponent(name)}` : null;
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

export async function libretroSearch(query, system) {
  const params = new URLSearchParams({ q: query });
  if (system) params.set("system", system);
  const res = await fetch(`/api/libretro/search?${params}`);
  if (!res.ok) throw new Error("libretro search failed");
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

// Cached IGDB detail for a rom (release date / genres / dev / rating / summary /
// screenshots / videos). GET reads the cache ({} if none); POST fetches it fresh.
export async function getIgdbMeta(romId) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/igdb-meta`));
  if (!res.ok) throw new Error("Failed to load IGDB info");
  return res.json();
}

export async function fetchIgdbMeta(romId) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/igdb-meta`, { method: "POST" }));
  if (!res.ok) throw new Error((await res.json()).detail || "IGDB fetch failed");
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

// XHR (not fetch) so the Data dropzone shows real upload progress — CD images /
// archives are large and a no-progress spinner looks frozen.
export async function uploadData(files, onProgress) {
  const sid = getSessionId();
  if (!sid) throw new Error("No session");
  const form = new FormData();
  for (const f of files) form.append("files", f);
  return xhrUpload(`/api/sessions/${sid}/data`, form, onProgress);
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
export async function setIdleLoop(romId, idleLoop) {
  const res = await withSession((sid) =>
    fetch(`/api/sessions/${sid}/roms/${romId}/idle-loop`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idle_loop: !!idleLoop }),
    }));
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to set idle loop");
  return res.json();
}

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

// Build the query string shared by the package endpoints: optional system
// filter + optional Korean-patched-only flag.
// The SD-ZIP "상세 조건" (see SdFilter on the server): which cover flags to keep, a
// size cap, patched-only, favorites-only, a score floor. An empty object = no
// conditions, which is the default card.
export const EMPTY_SD_FILTER = { flags: [], maxMb: null, patched: false, favorite: false, minScore: null };

export function sdFilterCount(f) {
  if (!f) return 0;
  return (f.flags?.length ? 1 : 0) + (f.maxMb ? 1 : 0) + (f.patched ? 1 : 0)
    + (f.favorite ? 1 : 0) + (f.minScore != null ? 1 : 0);
}

function packageQuery(system, filter) {
  const p = new URLSearchParams();
  if (system) p.set("system", system);
  if (filter?.flags?.length) p.set("flags", filter.flags.join(","));
  if (filter?.maxMb) p.set("max_mb", String(filter.maxMb));
  if (filter?.patched) p.set("patched", "1");
  if (filter?.favorite) p.set("favorite", "1");
  if (filter?.minScore != null) p.set("min_score", String(filter.minScore));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function packageUrl(system, filter) {
  const sid = getSessionId();
  if (!sid) return null;
  return `/api/sessions/${sid}/package${packageQuery(system, filter)}`;
}

// Kick off (or reuse) the server-side SD-zip build. Returns {ready, job_id}:
// ready → download immediately; else poll jobUrl(job_id) for build progress.
export function packageBuildUrl(system, filter) {
  const sid = getSessionId();
  if (!sid) return null;
  return `/api/sessions/${sid}/package/build${packageQuery(system, filter)}`;
}

export const jobUrl = (id) => `/api/jobs/${id}`;
export const jobCancelUrl = (id) => `/api/jobs/${id}/cancel`;

// Estimated on-SD byte size of the (optional single-system, optional Korean-only) package.
// {bytes, zipBytes} — the card size (uncompressed, what has to FIT) and the download
// size (the built zip). zipBytes is null until that exact zip has been built: how well
// a selection compresses depends entirely on what's in it (a .nes halves, a .chd or an
// .avi barely moves), so it is reported, never guessed.
export async function packageSize(system, filter) {
  const sid = getSessionId();
  if (!sid) return null;
  const res = await fetch(`/api/sessions/${sid}/package/size${packageQuery(system, filter)}`);
  if (!res.ok) return null;
  const j = await res.json();
  return { bytes: j.bytes, zipBytes: j.zip_bytes ?? null };
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
