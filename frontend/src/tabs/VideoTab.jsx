import React, { useEffect, useRef, useState } from "react";
import { Clapperboard, Upload, Loader, CheckCircle2, XCircle, AlertTriangle, Download, Server, ShieldCheck, Clock, Ban, Square } from "lucide-react";
import { uploadVideo, getJob, getHealth } from "../api.js";
import { Dropzone, ProgressBar } from "../components.jsx";
import { convertToDeviceAvi, downloadBlob, aviName, preloadEncoder, isMultiThread, cancelEncode } from "../localencode.js";
import { useT } from "../i18n.jsx";

// Screen-fit selector — shared by both sections (it's about how the source maps
// onto the 320×240 screen, the same either way).
function FitSelect({ mode, setMode, t }) {
  return (
    <div className="row" style={{ gap: 9, alignItems: "center" }}>
      <span className="muted">{t("Screen fit")}</span>
      <span className="search-scope fit-scope" role="group" aria-label={t("Screen fit")}>
        <button type="button" className={`scope-btn ${mode === "fit" ? "on" : ""}`} onClick={() => setMode("fit")}>{t("Fit (letterbox)")}</button>
        <button type="button" className={`scope-btn ${mode === "fill" ? "on" : ""}`} onClick={() => setMode("fill")}>{t("Fill (crop)")}</button>
        <button type="button" className={`scope-btn ${mode === "stretch" ? "on" : ""}`} onClick={() => setMode("stretch")}>{t("Stretch (distort)")}</button>
      </span>
    </div>
  );
}

// Browser-convert queue list — many files dropped at once convert one-by-one
// (ffmpeg.wasm is a single instance) and each .avi downloads as it finishes.
function QueueList({ queue, onCancel, t }) {
  if (!queue.length) return null;
  const done = queue.filter((i) => i.status === "done").length;
  const failed = queue.filter((i) => i.status === "failed").length;
  const cancelled = queue.filter((i) => i.status === "cancelled").length;
  const active = queue.some((i) => i.status === "pending" || i.status === "converting");
  return (
    <div className="vtab-queue stack">
      <div className="row">
        <span className="muted">{active ? t("Converting…") : t("Done")}</span>
        <span className="row" style={{ gap: 8 }}>
          <span className="muted">{done}/{queue.length}{failed ? ` · ${failed} ${t("failed")}` : ""}{cancelled ? ` · ${cancelled} ${t("cancelled")}` : ""}</span>
          {active && (
            <button type="button" className="vtab-stop" onClick={onCancel} title={t("Stop")}>
              <Square size={11} strokeWidth={3} fill="currentColor" aria-hidden /> {t("Stop")}
            </button>
          )}
        </span>
      </div>
      <ul className="vtab-qlist">
        {queue.map((it, i) => (
          <li key={i} className={`vtab-qitem ${it.status}`}>
            <span className="vtab-qicon">
              {it.status === "done" ? <CheckCircle2 size={12} strokeWidth={2.5} aria-hidden />
                : it.status === "failed" ? <XCircle size={12} strokeWidth={2.5} aria-hidden />
                : it.status === "cancelled" ? <Ban size={12} strokeWidth={2.5} aria-hidden />
                : it.status === "converting" ? <Loader size={12} strokeWidth={2.5} className="spin" aria-hidden />
                : <Clock size={12} strokeWidth={2.5} aria-hidden />}
            </span>
            <span className="vtab-qname" title={it.name}>{it.name}</span>
            {it.status === "converting" && <span className="vtab-qpct">{Math.round((it.progress || 0) * 100)}%</span>}
            {it.status === "failed" && <span className="vtab-qpct err">{it.error || t("Failed")}</span>}
            {it.status === "cancelled" && <span className="vtab-qpct">{t("cancelled")}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function JobStatus({ job, name, busyLabel, doneLabel, t }) {
  if (!job) return null;
  return (
    <div className="stack">
      <div className="row">
        <span className="muted">{name}</span>
        <span className="muted">
          {job.status === "done" ? (
            <><CheckCircle2 size={13} strokeWidth={2.5} aria-hidden /> {doneLabel}</>
          ) : job.status === "failed" ? (
            <><XCircle size={13} strokeWidth={2.5} aria-hidden /> {t("Failed")}</>
          ) : (
            <><Loader size={13} strokeWidth={2.5} className="spin" aria-hidden /> {busyLabel}</>
          )}
        </span>
      </div>
      <ProgressBar value={job.status === "done" ? 1 : job.progress} />
      {job.status === "failed" && <div className="badge failed">{job.message}</div>}
    </div>
  );
}

export default function VideoTab({ onChanged }) {
  const t = useT();
  const [mode, setMode] = useState("fit");      // fit | fill | stretch (shared)
  const [ffmpeg, setFfmpeg] = useState(true);
  // Browser-convert section (local → download, no upload). queue = many files
  // dropped at once, converted sequentially.
  const [queue, setQueue] = useState([]);  // [{name, status:'pending'|'converting'|'done'|'failed'|'cancelled', progress, error}]
  const cancelRef = useRef(false);
  // Shared-storage section (upload → server ffmpeg → /media)
  const [srvJob, setSrvJob] = useState(null);
  const [srvName, setSrvName] = useState("");
  const [srvError, setSrvError] = useState("");
  const timer = useRef(null);

  useEffect(() => {
    getHealth().then((h) => setFfmpeg(h.ffmpeg));
    return () => clearInterval(timer.current);
  }, []);

  // Browser: convert every dropped file with ffmpeg.wasm and download each .avi —
  // no upload. Sequential (one wasm instance); each file's FS is freed after, so
  // even 10+ files at once stay within memory.
  async function handleLocal(files) {
    const list = Array.from(files);
    if (!list.length) return;
    cancelRef.current = false;
    setQueue(list.map((f) => ({ name: f.name, status: "pending", progress: 0 })));
    const set = (i, patch) => setQueue((q) => q.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));
    for (let i = 0; i < list.length; i++) {
      if (cancelRef.current) { set(i, { status: "cancelled" }); continue; }
      set(i, { status: "converting", progress: 0.02 });
      try {
        const blob = await convertToDeviceAvi(list[i], mode, {
          onProgress: (p) => set(i, { progress: Math.max(0.02, p) }),
        });
        if (cancelRef.current) { set(i, { status: "cancelled" }); continue; }
        downloadBlob(blob, aviName(list[i].name));
        set(i, { status: "done", progress: 1 });
      } catch (e) {
        set(i, cancelRef.current ? { status: "cancelled" } : { status: "failed", error: e.message || String(e) });
      }
    }
  }

  // Stop the queue: flag it, then terminate the in-flight ffmpeg.wasm exec.
  function cancelLocal() {
    cancelRef.current = true;
    cancelEncode();
  }

  // Shared storage: upload the source, the server encodes it into /media (visible
  // to everyone using this library).
  async function handleServer(files, onProgress) {
    const file = files[0];
    if (!file) return;
    setSrvError(""); setSrvName(file.name);
    setSrvJob({ status: "encoding", progress: 0.05 });
    try {
      const res = await uploadVideo(file, onProgress, { mode });
      poll(res.job_id);
    } catch (e) {
      setSrvError(e.message); setSrvJob(null);
    }
  }

  function poll(jobId) {
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const j = await getJob(jobId);
        setSrvJob(j);
        if (j.status === "done" || j.status === "failed") {
          clearInterval(timer.current);
          onChanged?.();
        }
      } catch {
        clearInterval(timer.current);
      }
    }, 1200);
  }

  return (
    <div className="stack">
      <div className="muted">
        <Clapperboard size={13} aria-hidden /> {t("For the device's /media player")} · <b>MJPEG · AVI · 320×240 · 20fps · mono MP3 (q17)</b>
      </div>

      <FitSelect mode={mode} setMode={setMode} t={t} />

      {/* ── TOP: convert in the browser, download the .avi (no upload) ── */}
      <section className="vtab-section" onMouseEnter={preloadEncoder}>
        <div className="vtab-head">
          <Download size={14} strokeWidth={2.5} aria-hidden /> {t("Convert in browser (download)")}
          <span className={`vtab-mode ${isMultiThread() ? "fast" : ""}`}>
            {isMultiThread() ? t("fast (multi-thread)") : t("compatibility mode")}
          </span>
        </div>
        <div className="vtab-safe">
          <ShieldCheck size={13} strokeWidth={2.5} aria-hidden /> {t("Your video is NOT uploaded — it's processed entirely in your browser and only the .avi downloads.")}
        </div>
        <div className="muted vtab-note">
          {t("Very large files may hit the browser's memory limit — use Shared storage below for those. After it downloads, copy the .avi into the SD card's /media folder.")}
        </div>
        <Dropzone
          accept="video/*"
          multiple
          busyLabel={t("Converting…")}
          label={<span className="dz-label"><Upload size={16} aria-hidden /> {t("Drag videos here or click — multiple at once (mp4/mov/mkv…)")}</span>}
          onFiles={handleLocal}
        />
        <QueueList queue={queue} onCancel={cancelLocal} t={t} />
      </section>

      {/* ── BOTTOM: upload to the shared library (server encodes into /media) ── */}
      <section className="vtab-section">
        <div className="vtab-head">
          <Server size={14} strokeWidth={2.5} aria-hidden /> {t("Shared storage (saved to /media)")}
        </div>
        <div className="muted vtab-note">
          {t("Uploads the source; the server encodes it into the shared /media library (everyone sees it).")}
        </div>
        {!ffmpeg && (
          <div className="badge failed">
            <AlertTriangle size={11} strokeWidth={2.5} aria-hidden /> {t("ffmpeg is not available on the server")}
          </div>
        )}
        <Dropzone
          accept="video/*"
          label={<span className="dz-label"><Upload size={16} aria-hidden /> {t("Drag a video here or click (mp4/mov/mkv…)")}</span>}
          onFiles={handleServer}
        />
        <JobStatus job={srvJob} name={srvName} busyLabel={t("Encoding…")} doneLabel={t("Done")} t={t} />
        {srvError && <div className="badge failed">{srvError}</div>}
      </section>
    </div>
  );
}
