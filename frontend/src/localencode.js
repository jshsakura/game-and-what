// Browser-side media → device conversion via ffmpeg.wasm, entirely client-side:
// no upload, no server encode. Two outputs share the one loaded core —
//   • video → MJPEG .avi, byte-identical to the server (backend/app/services/video.py)
//   • audio → a mono clock alarm .mp3 for /clock/alarm/
//
// Uses the MULTI-THREAD core (/public/ffmpeg-mt, 2–4× faster) when the page is
// cross-origin isolated (COOP/COEP set — see vite.config.js + backend middleware);
// otherwise falls back to the single-thread core (/public/ffmpeg) — e.g. Safari,
// which doesn't support COEP credentialless. Both are self-hosted.
import { FFmpeg } from "@ffmpeg/ffmpeg";
import { fetchFile, toBlobURL } from "@ffmpeg/util";

// SharedArrayBuffer (hence the MT core) only works on a cross-origin-isolated page.
const MT = typeof globalThis !== "undefined" && globalThis.crossOriginIsolated === true;

// How many worker threads ffmpeg may use. Without an explicit -threads the MT core
// decodes/encodes effectively single-threaded (the slow path the user hit on an
// 11MB clip) — H.264 frame-decode in particular scales with this. Cap at 8 so we
// don't oversubscribe the emscripten pthread pool; the single-thread core is 1.
const THREADS = String(MT ? Math.min(navigator.hardwareConcurrency || 4, 8) : 1);

// Screen-fit filters — kept byte-identical to the server's _VIDEO_FILTERS.
const FILTERS = {
  fit: "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:-1:-1:color=black,fps=20",
  fill: "scale=320:240:force_original_aspect_ratio=increase,crop=320:240,fps=20",
  stretch: "scale=320:240,fps=20",
};

// device-verified params (mirror video.py: VIDEO_QSCALE 17, mono MP3 96k/48000).
// 48000 = the device's own rate, so its nearest-sample resampler passes the audio
// through untouched — see the alarm section below for what 44100 cost.
const VIDEO_ARGS = ["-c:v", "mjpeg", "-q:v", "17"];
const AUDIO_ARGS = ["-c:a", "libmp3lame", "-ac", "1", "-b:a", "96k", "-ar", "48000"];

let _ff = null;          // single shared instance (the 32MB core loads once)
let _loading = null;
let _usedMT = MT;        // which core actually loaded (MT may fall back to single)
let _onProgress = null;  // current run's progress cb (listeners registered once)
let _onLog = null;

// Load one core (mt=true → ffmpeg-mt with pthread worker; false → single-thread).
// Core files are loaded as BLOB urls (toBlobURL fetches the static /public file
// and wraps it blob:) — a plain path would be intercepted by Vite's module
// transform (`?import`) and fail. `?v=` busts any stale-cached old core.
// BASE_URL, not a leading "/": the demo build is served from a GitHub Pages
// subpath, where an absolute path 404s and no convert can ever load its core.
async function loadCore(mt) {
  const ff = new FFmpeg();
  ff.on("log", ({ message }) => { _onLog && _onLog(message); });
  ff.on("progress", ({ progress }) => {
    if (_onProgress) _onProgress(Math.max(0, Math.min(1, progress || 0)));
  });
  const base = `${import.meta.env.BASE_URL}${mt ? "ffmpeg-mt" : "ffmpeg"}`;
  const v = "?v=esm1";
  const opts = {
    coreURL: await toBlobURL(`${base}/ffmpeg-core.js${v}`, "text/javascript"),
    wasmURL: await toBlobURL(`${base}/ffmpeg-core.wasm${v}`, "application/wasm"),
  };
  if (mt) opts.workerURL = await toBlobURL(`${base}/ffmpeg-core.worker.js${v}`, "text/javascript");
  await ff.load(opts);
  _usedMT = mt;
  return ff;
}

async function getFFmpeg() {
  if (_ff) return _ff;
  if (_loading) return _loading;
  _loading = (async () => {
    // Prefer the fast MT core when the page is cross-origin isolated, but FALL BACK
    // to single-thread if it fails to load — e.g. behind a proxy (Cloudflare
    // Access) that drops the COEP header or blocks the pthread worker/SAB, where MT
    // would otherwise die with no recovery and the convert just "doesn't work".
    try {
      _ff = await loadCore(MT);
    } catch (e) {
      if (!MT) throw e;
      _ff = await loadCore(false);
    }
    return _ff;
  })().catch((e) => { _loading = null; throw e; });   // failed load → allow retry
  return _loading;
}

// Preload the core (e.g. when the user opens the local-convert UI) so the first
// convert doesn't eat the 32MB download time.
export function preloadEncoder() { return getFFmpeg().catch(() => {}); }

export function encoderReady() { return !!_ff; }

// true = the fast multi-thread core is in use (page is cross-origin isolated).
export function isMultiThread() { return _ff ? _usedMT : MT; }

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
      "-threads", THREADS,           // decode threads (H.264 → big win on the MT core)
      "-i", inName,
      ...VIDEO_ARGS,
      "-vf", FILTERS[mode] || FILTERS.fit,
      "-threads", THREADS,           // encode/output threads
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

// --- clock alarm sound (/clock/alarm/*.mp3) ---------------------------------
// Shaped by what the firmware's decoder actually does (music_audio.c, shared
// with the Music app):
//
//   ring_push(g_mono[g_phase >> 16]);   // nearest sample. no interpolation.
//   g_phase += g_step;                  // g_step = (src_hz << 16) / 48000
//
//   • MONO — every source is downmixed, so stereo is pure waste.
//   • 48 kHz — the ONLY rate where g_step lands on exactly 65536, i.e. one
//     source sample per output sample, untouched. At 44.1 kHz g_step is 60211
//     and that zero-order-hold repeats samples, folding an image of the source
//     back into the audible band (a 1 kHz tone grows a −37 dBc spur at 4.9 kHz;
//     measured SINAD 27.7 dB vs 74.4 dB at 48 kHz — and the spur is identical
//     with the MP3 encoder removed, so no bitrate can buy it back).
const ALARM_HZ = 48000;
export const ALARM_KBPS = 64;
export const ALARM_MAX_S = 60;    // the clock auto-dismisses at 60s (ALARM_RING_MS)
const ALARM_ARGS = [
  "-vn",                          // a video source contributes its audio only
  "-ac", "1", "-ar", String(ALARM_HZ),
  "-c:a", "libmp3lame", "-b:a",   // (bitrate appended per call)
];
// An alarm's job is to wake you, so the clip is loudness-matched rather than
// left at whatever level the source happened to sit at. EBU R128 two-pass with
// linear=true applies ONE gain to the whole clip (no pumping, no squashing);
// ffmpeg only falls back to dynamic mode if that single gain would clip.
const ALARM_LUFS = -12;           // louder than streaming's -14, short of squashed
const ALARM_PEAK_DBTP = -1.0;     // headroom so the 16-bit path never clips
// The clock LOOPS the file until the ring ends, so a clip that starts or ends
// mid-waveform clicks at every seam. Ramping both ends to zero costs 40ms, which
// is far too short to hear as a fade.
const ALARM_FADE_S = 0.04;

// Bytes per second of encoded MP3 — for the live size estimate.
export const alarmBytesPerSec = (kbps = ALARM_KBPS) => (kbps * 1000) / 8;

// "My Song.flac" → "My_Song.mp3"; unnamable stems fall back to "alarm.mp3".
export function alarmName(sourceName) {
  const stem = (sourceName || "")
    .replace(/\.[^.]+$/, "")
    .replace(/[^\w\-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);
  return stem.replace(/[_\-]/g, "").length < 2 ? "alarm.mp3" : `${stem}.mp3`;
}

const loudnormBase = `loudnorm=I=${ALARM_LUFS}:TP=${ALARM_PEAK_DBTP}:LRA=11`;

// Pass 1 of the loudness match: analyse the CLIP (not the whole song) and read
// back the four measurements loudnorm needs to compute its single gain. The
// filter prints them as a JSON block on the log, which is the only channel out.
// Returns null when anything is off — the caller then ships the clip unmatched
// rather than failing the whole convert over a cosmetic step.
async function measureLoudness(ff, inName, seek, duration) {
  const lines = [];
  _onLog = (m) => lines.push(m);
  try {
    const code = await ff.exec([
      "-hide_banner", "-y", "-ss", seek, "-i", inName, "-t", duration,
      "-vn", "-ac", "1",
      "-af", `${loudnormBase}:print_format=json`,
      "-f", "null", "nul",
    ]);
    if (code !== 0) return null;
    const log = lines.join("\n");
    const json = log.slice(log.lastIndexOf("{"), log.lastIndexOf("}") + 1);
    const m = JSON.parse(json);
    const out = {
      i: m.input_i, tp: m.input_tp, lra: m.input_lra,
      thresh: m.input_thresh, offset: m.target_offset,
    };
    // A silent clip measures -inf and would ask for infinite gain.
    return Object.values(out).every((v) => Number.isFinite(parseFloat(v))) ? out : null;
  } catch (_) {
    return null;                 // unparseable log / no JSON block → skip matching
  } finally {
    _onLog = null;
  }
}

/**
 * Trim an audio/video File to [start, start+duration], loudness-match it and
 * encode a device-optimal mono 48 kHz MP3 for /clock/alarm/. All in the browser.
 * No progress callback: an alarm clip is seconds long, so the caller shows a
 * spinner (ffmpeg's own progress is a fraction of the SOURCE length here, which
 * would read as stuck at a few percent for a 10s cut of a 4-minute song).
 * @returns {Promise<Blob>} the .mp3 blob (caller triggers the download).
 */
export async function convertToAlarmMp3(file, { start = 0, duration = 10, kbps = ALARM_KBPS } = {}) {
  if (!file) throw new Error("No file");
  if (!(duration > 0)) throw new Error("Clip length must be greater than zero");
  const ff = await getFFmpeg();
  const ext = (file.name.match(/\.[^.]+$/) || [".mp3"])[0];
  const inName = "input" + ext;
  const outName = "output.mp3";
  const seek = start.toFixed(3);
  const dur = duration.toFixed(3);
  try {
    await ff.writeFile(inName, await fetchFile(file));

    const measured = await measureLoudness(ff, inName, seek, dur);
    // Fades come AFTER loudnorm: normalising a faded clip would just undo the ramp.
    // Too short to fade both ends without eating the clip → skip the fades.
    const chain = [
      measured
        ? `${loudnormBase}:measured_I=${measured.i}:measured_TP=${measured.tp}`
          + `:measured_LRA=${measured.lra}:measured_thresh=${measured.thresh}`
          + `:offset=${measured.offset}:linear=true`
        : null,
      duration > ALARM_FADE_S * 4
        ? `afade=t=in:st=0:d=${ALARM_FADE_S},afade=t=out:st=${(duration - ALARM_FADE_S).toFixed(3)}:d=${ALARM_FADE_S}`
        : null,
    ].filter(Boolean).join(",");

    const code = await ff.exec([
      "-hide_banner", "-y",
      "-ss", seek,                   // input seek: decode starts at the clip
      "-i", inName,
      "-t", dur,
      "-threads", THREADS,
      ...ALARM_ARGS, `${kbps}k`,
      ...(chain ? ["-af", chain] : []),
      "-map_metadata", "-1",         // strip tags/cover art — pure audio bytes
      "-id3v2_version", "0",
      outName,
    ]);
    if (code !== 0) throw new Error("ffmpeg exited with code " + code);
    const data = await ff.readFile(outName);
    if (!data || !data.length) throw new Error("Encode produced no output");
    return new Blob([data.buffer], { type: "audio/mpeg" });
  } finally {
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
