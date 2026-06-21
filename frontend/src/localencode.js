// Browser-side video → device MJPEG/.avi conversion via ffmpeg.wasm. Produces the
// EXACT same output as the server (see backend/app/services/video.py) but entirely
// client-side, then hands back a Blob to download — no upload, no server encode.
//
// Uses the MULTI-THREAD core (/public/ffmpeg-mt, 2–4× faster) when the page is
// cross-origin isolated (COOP/COEP set — see vite.config.js + backend middleware);
// otherwise falls back to the single-thread core (/public/ffmpeg) — e.g. Safari,
// which doesn't support COEP credentialless. Both are self-hosted.
import { FFmpeg } from "@ffmpeg/ffmpeg";
import { fetchFile, toBlobURL } from "@ffmpeg/util";

// SharedArrayBuffer (hence the MT core) only works on a cross-origin-isolated page.
const MT = typeof globalThis !== "undefined" && globalThis.crossOriginIsolated === true;

// Screen-fit filters — kept byte-identical to the server's _VIDEO_FILTERS.
const FILTERS = {
  fit: "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:-1:-1:color=black,fps=20",
  fill: "scale=320:240:force_original_aspect_ratio=increase,crop=320:240,fps=20",
  stretch: "scale=320:240,fps=20",
};

// device-verified params (mirror video.py: VIDEO_QSCALE 17, mono MP3 96k/44100)
const VIDEO_ARGS = ["-c:v", "mjpeg", "-q:v", "17"];
const AUDIO_ARGS = ["-c:a", "libmp3lame", "-ac", "1", "-b:a", "96k", "-ar", "44100"];

let _ff = null;          // single shared instance (the 32MB core loads once)
let _loading = null;
let _onProgress = null;  // current run's progress cb (listeners registered once)
let _onLog = null;

async function getFFmpeg() {
  if (_ff) return _ff;
  if (_loading) return _loading;
  _loading = (async () => {
    const ff = new FFmpeg();
    ff.on("log", ({ message }) => { _onLog && _onLog(message); });
    ff.on("progress", ({ progress }) => {
      if (_onProgress) _onProgress(Math.max(0, Math.min(1, progress || 0)));
    });
    // Load the core as BLOB urls (toBlobURL fetches the static /public file and
    // wraps it in a blob:) — a plain path would be intercepted by Vite's module
    // transform (`?import`) and fail. Blob urls bypass that in dev AND prod.
    // The `?v=` busts any stale-cached old core (v1.3.0 shipped a broken UMD core
    // at the same path → browsers that cached it must refetch the ESM one).
    const base = MT ? "/ffmpeg-mt" : "/ffmpeg";
    const v = "?v=esm1";
    const opts = {
      coreURL: await toBlobURL(`${base}/ffmpeg-core.js${v}`, "text/javascript"),
      wasmURL: await toBlobURL(`${base}/ffmpeg-core.wasm${v}`, "application/wasm"),
    };
    if (MT) {  // emscripten pthread worker (MT core only)
      opts.workerURL = await toBlobURL(`${base}/ffmpeg-core.worker.js${v}`, "text/javascript");
    }
    await ff.load(opts);
    _ff = ff;
    return ff;
  })().catch((e) => { _loading = null; throw e; });   // failed load → allow retry
  return _loading;
}

// Preload the core (e.g. when the user opens the local-convert UI) so the first
// convert doesn't eat the 32MB download time.
export function preloadEncoder() { return getFFmpeg().catch(() => {}); }

export function encoderReady() { return !!_ff; }

// true = the fast multi-thread core is in use (page is cross-origin isolated).
export function isMultiThread() { return MT; }

// Abort the in-flight conversion: terminating the worker rejects the running
// exec() (caller catches it). The instance is dropped so the NEXT convert reloads
// a fresh core (terminate() leaves it unusable).
export function cancelEncode() {
  const ff = _ff;
  _ff = null;
  _loading = null;
  if (ff) { try { ff.terminate(); } catch { /* already gone */ } }
}

/**
 * Convert a video File to a device-playable MJPEG .avi entirely in the browser.
 * @returns {Promise<Blob>} the .avi blob (caller triggers the download).
 */
export async function convertToDeviceAvi(file, mode = "fit", { onProgress, onLog } = {}) {
  if (!file) throw new Error("No file");
  const ff = await getFFmpeg();
  _onProgress = onProgress || null;
  _onLog = onLog || null;
  const ext = (file.name.match(/\.[^.]+$/) || [".mp4"])[0];
  const inName = "input" + ext;
  const outName = "output.avi";
  try {
    await ff.writeFile(inName, await fetchFile(file));
    const code = await ff.exec([
      "-hide_banner", "-y",
      "-i", inName,
      ...VIDEO_ARGS,
      "-vf", FILTERS[mode] || FILTERS.fit,
      ...AUDIO_ARGS,
      outName,
    ]);
    if (code !== 0) throw new Error("ffmpeg exited with code " + code);
    const data = await ff.readFile(outName);
    if (!data || !data.length) throw new Error("Encode produced no output");
    return new Blob([data.buffer], { type: "video/x-msvideo" });
  } finally {
    _onProgress = null; _onLog = null;
    ff.deleteFile(inName).catch(() => {});
    ff.deleteFile(outName).catch(() => {});
  }
}

// Trigger a browser download of a blob under `filename`.
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

// "My Clip.mp4" → "My Clip.avi"
export function aviName(sourceName) {
  return (sourceName || "video").replace(/\.[^.]+$/, "") + ".avi";
}
