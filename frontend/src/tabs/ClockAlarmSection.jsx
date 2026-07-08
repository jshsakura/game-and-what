import React, { useEffect, useRef, useState } from "react";
import { BellRing, Upload, Loader, Info, Download, Play, Square, X } from "lucide-react";
import { formatBytes } from "../api.js";
import {
  convertToAlarmMp3, downloadBlob, alarmName, alarmBytesPerSec, preloadEncoder,
  ALARM_KBPS, ALARM_MAX_S,
} from "../localencode.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";

// Clock alarm sound: any song/video → a short mono MP3 in /clock/alarm/.
// The firmware rings for 60s, LOOPING the file, so a few seconds of the good part
// beats the whole track. Everything happens in the browser (ffmpeg.wasm) — the
// loop preview here plays exactly the clip the device will loop.
const DEFAULT_CLIP_S = 10;
const LENGTH_PRESETS = [5, 10, 15, 30];
const DEFAULT_NAME = "alarm.mp3";

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function timecode(sec) {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function ClockAlarmSection() {
  const t = useT();
  const toast = useToast();
  const audioRef = useRef(null);
  const [src, setSrc] = useState(null);       // { file, url }
  const [srcDur, setSrcDur] = useState(0);    // 0 = unknown (browser can't decode it)
  const [start, setStart] = useState(0);
  const [clipLen, setClipLen] = useState(DEFAULT_CLIP_S);
  const [playing, setPlaying] = useState(false);
  const [useDefaultName, setUseDefaultName] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // { outBytes }

  // Blob URL lives as long as the picked source — swap/unmount revokes it.
  useEffect(() => () => { if (src) URL.revokeObjectURL(src.url); }, [src]);

  const maxClip = srcDur > 0 ? Math.min(ALARM_MAX_S, srcDur) : ALARM_MAX_S;
  const maxStart = srcDur > 0 ? Math.max(0, srcDur - clipLen) : 0;
  const end = start + clipLen;
  const outName = useDefaultName || !src ? DEFAULT_NAME : alarmName(src.file.name);
  const estBytes = clipLen * alarmBytesPerSec();

  function stop() {
    const el = audioRef.current;
    if (el) el.pause();
    setPlaying(false);
  }

  function handleFiles(files) {
    const file = Array.from(files)[0];
    if (!file || !(file.type.startsWith("audio/") || file.type.startsWith("video/"))) {
      toast.error(t("Pick an audio or video file"));
      return;
    }
    stop();
    preloadEncoder();   // fetch the 32MB ffmpeg core now, not on the Convert click
    setSrc({ file, url: URL.createObjectURL(file) });
    setSrcDur(0);
    setStart(0);
    setClipLen(DEFAULT_CLIP_S);
    setUseDefaultName(true);
    setResult(null);
  }

  function clearSrc() {
    stop();
    setSrc(null);
    setResult(null);
  }

  // Duration decides the slider ranges. A source the browser can't decode (or one
  // with no duration in its header) still converts — ffmpeg reads it — so we just
  // fall back to "unknown": clip from 0, length capped at the 60s ring.
  function onMeta() {
    const d = audioRef.current?.duration;
    if (!Number.isFinite(d) || d <= 0) return;
    setSrcDur(d);
    setClipLen((cur) => clamp(cur, 1, Math.min(ALARM_MAX_S, d)));
  }

  // Loop the selected range, exactly as the clock does while the alarm rings.
  function onTimeUpdate() {
    const el = audioRef.current;
    if (!el || !playing) return;
    if (el.currentTime >= end || el.currentTime < start - 0.25) el.currentTime = start;
  }

  async function togglePlay() {
    const el = audioRef.current;
    if (!el) return;
    if (playing) { stop(); return; }
    try {
      el.currentTime = start;
      await el.play();
      setPlaying(true);
    } catch (_) {
      toast.error(t("Your browser can’t play this file — you can still convert it"));
    }
  }

  // Keep playback inside the range while the user drags the sliders.
  function moveStart(v) {
    const next = clamp(v, 0, maxStart);
    setStart(next);
    const el = audioRef.current;
    if (el && playing) el.currentTime = next;
  }

  function setLength(v) {
    const next = clamp(v, 1, maxClip);
    setClipLen(next);
    if (srcDur > 0) setStart((cur) => clamp(cur, 0, Math.max(0, srcDur - next)));
  }

  async function convert() {
    if (!src || busy) return;
    stop();
    setBusy(true);
    setResult(null);
    try {
      const blob = await convertToAlarmMp3(src.file, { start, duration: clipLen });
      downloadBlob(blob, outName);
      setResult({ outBytes: blob.size });
      toast.success(t("Downloaded {name} — copy it into /clock/alarm on the SD card", { name: outName }));
    } catch (e) {
      toast.error(e.message || t("Convert failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="muted">
        <BellRing size={13} aria-hidden /> {t("Turn any song or video into a clock alarm sound. The alarm rings for 60 seconds, looping your clip — so a few seconds of the best part is all you need.")}
      </div>
      <div className="vtab-safe">
        <Info size={13} strokeWidth={2.5} aria-hidden />
        <span>{t("Converted in your browser (nothing is uploaded) to a mono 48 kHz MP3 — the exact format the device plays, so it never resamples your alarm — and turned up to a standard loudness, so a quiet song still wakes you. Copy it into")} <b>/clock/alarm</b> {t("on the SD card, then pick it under Settings → Alarm sound (GAME previews it).")}</span>
      </div>

      <Dropzone
        accept="audio/*,video/*"
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag a song or video here or click (mp3/wav/m4a/mp4…)")}
          </span>
        }
        onFiles={handleFiles}
      />

      {src && (
        <div className="stack">
          <audio
            ref={audioRef}
            src={src.url}
            onLoadedMetadata={onMeta}
            onTimeUpdate={onTimeUpdate}
            onEnded={stop}
            preload="metadata"
          />

          <div className="row" style={{ gap: 9, alignItems: "center" }}>
            <span className="muted">{t("Clip length")}</span>
            <span className="search-scope fit-scope" role="group" aria-label={t("Clip length")}>
              {LENGTH_PRESETS.filter((s) => s <= maxClip).map((s) => (
                <button key={s} type="button" className={`scope-btn ${clipLen === s ? "on" : ""}`} onClick={() => setLength(s)}>
                  {s}s
                </button>
              ))}
            </span>
          </div>

          <div className="clock-trim-grid">
            <label className="clock-trim-row">
              <span className="muted clock-trim-label">{t("Length")}</span>
              <input
                className="cropper-zoom" type="range" min={1} max={maxClip} step={1}
                value={clipLen}
                onChange={(e) => setLength(Number(e.target.value))}
              />
              <span className="muted clock-trim-val">{clipLen}s</span>
            </label>

            <label className="clock-trim-row">
              <span className="muted clock-trim-label">{t("Clip start")}</span>
              <input
                className="cropper-zoom" type="range" min={0} max={Math.max(maxStart, 1)} step={0.5}
                value={start}
                disabled={maxStart <= 0}
                onChange={(e) => moveStart(Number(e.target.value))}
              />
              <span className="muted clock-trim-val">{timecode(start)}–{timecode(end)}</span>
            </label>
          </div>

          <div className="row" style={{ gap: 9, alignItems: "center" }}>
            <button type="button" className={`scope-btn ${playing ? "on" : ""}`} onClick={togglePlay} disabled={busy}>
              {playing
                ? <><Square size={13} strokeWidth={3} fill="currentColor" aria-hidden /> {t("Stop")}</>
                : <><Play size={13} strokeWidth={2.5} aria-hidden /> {t("Preview the loop")}</>}
            </button>
            <span className="muted">
              {srcDur > 0 ? t("Source {dur}", { dur: timecode(srcDur) }) : t("Length unknown — clip starts at 0:00")}
              {" · "}
              {t("mono 48 kHz · {kbps} kbps · loudness-matched", { kbps: ALARM_KBPS })}
              {" · ≈"}{formatBytes(estBytes)}
            </span>
          </div>

          <div className="row" style={{ gap: 9, alignItems: "center" }}>
            <span className="muted">{t("Save as")}</span>
            <span className="search-scope fit-scope" role="group" aria-label={t("Save as")}>
              <button type="button" className={`scope-btn ${useDefaultName ? "on" : ""}`} onClick={() => setUseDefaultName(true)}>
                {DEFAULT_NAME} ({t("device default")})
              </button>
              <button type="button" className={`scope-btn ${useDefaultName ? "" : "on"}`} onClick={() => setUseDefaultName(false)}>
                {alarmName(src.file.name)}
              </button>
            </span>
          </div>

          <div className="row clock-file-row">
            <span className="muted clock-file-name" title={src.file.name}>
              {src.file.name} ({formatBytes(src.file.size)})
              {result && <> → <b>{outName}</b> {formatBytes(result.outBytes)}</>}
            </span>
            <button type="button" className="scope-btn" onClick={clearSrc} disabled={busy} aria-label={t("Remove")} title={t("Remove")}>
              <X size={14} strokeWidth={2.5} aria-hidden />
            </button>
            <button type="button" className="scope-btn on" onClick={convert} disabled={busy}>
              {busy
                ? <><Loader size={14} strokeWidth={2.5} className="spin" aria-hidden /> {t("Converting…")}</>
                : <><Download size={14} strokeWidth={2.5} aria-hidden /> {t("Convert & download")}</>}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
