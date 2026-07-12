import React, { createContext, useContext, useState, useCallback, useRef } from "react";
import { formatBytes, packageBuildUrl, packageUrl, jobUrl, jobCancelUrl } from "./api.js";
import { useT } from "./i18n.jsx";

// A centered 8-bit progress overlay for big downloads. A full SD ZIP is built
// server-side first (minutes of compression), then streamed. Instead of a plain
// <a download> — which shows nothing while the zip is built and can't be
// cancelled — this drives an explicit two-phase flow:
//   1. "building"     — poll the build job, show real % + MB (so it never looks
//                        frozen), cancellable server-side.
//   2. "downloading"  — stream the finished zip, show received / total.
const DownloadCtx = createContext(null);
export function useDownload() {
  return useContext(DownloadCtx);
}

function filenameFromHeader(cd, fallback) {
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd || "");
  if (!m) return fallback;
  try {
    return decodeURIComponent(m[1]);
  } catch (_) {
    return m[1] || fallback;
  }
}

// Build job reports message like "689/3281 MB"; pull the two numbers out.
function parseMB(message) {
  const m = /(\d+)\s*\/\s*(\d+)\s*MB/i.exec(message || "");
  return m ? { doneMB: Number(m[1]), totalMB: Number(m[2]) } : null;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function DownloadProvider({ children }) {
  const t = useT();
  // job.phase: "building" | "downloading" | "error"
  const [job, setJob] = useState(null);
  const abortRef = useRef(null);      // aborts the streaming download fetch
  const jobIdRef = useRef(null);      // server build job id (for cancel)
  const cancelledRef = useRef(false); // set by cancel() during the build phase
  const activeRef = useRef(false);    // one download at a time

  // Stream a ready (cached) zip to disk with progress. The build already ran, so
  // headers arrive promptly.
  const streamDownload = useCallback(async (url, fallbackName, knownTotal) => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const res = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) throw new Error(t("Download failed ({status})", { status: res.status }));
    const total = Number(res.headers.get("Content-Length")) || knownTotal || 0;
    const name = filenameFromHeader(res.headers.get("Content-Disposition"), fallbackName);
    const reader = res.body.getReader();
    const chunks = [];
    let received = 0;
    setJob({ phase: "downloading", label: name, received: 0, total });
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      setJob({ phase: "downloading", label: name, received, total });
    }
    const blob = new Blob(chunks, { type: res.headers.get("Content-Type") || "application/zip" });
    const obj = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = obj;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(obj), 1000);
    setJob(null);
  }, [t]);

  // Plain streaming download for direct endpoints (a ROM card's zip, a video
  // file): no build job to poll, just the progress overlay while it streams.
  const download = useCallback(async (url, fallbackName = "download.zip") => {
    if (activeRef.current) return;
    activeRef.current = true;
    cancelledRef.current = false;
    try {
      await streamDownload(url, fallbackName, 0);
    } catch (e) {
      if (e.name === "AbortError") {
        setJob(null);
      } else {
        setJob({ phase: "error", error: e.message || t("Download failed") });
        setTimeout(() => setJob(null), 2600);
      }
    } finally {
      activeRef.current = false;
      abortRef.current = null;
    }
  }, [t, streamDownload]);

  // Full flow: build (with progress) then download. `system` is undefined for
  // the whole-SD package, or a platform dirname for a single system. `korean`
  // ships only 한글패치 roms.
  const downloadPackage = useCallback(async (system, fallbackName = "gnw-sd.zip", knownTotal = 0,
                                             korean = false) => {
    if (activeRef.current) return;
    activeRef.current = true;
    cancelledRef.current = false;
    jobIdRef.current = null;
    setJob({ phase: "building", label: fallbackName, progress: 0, doneMB: 0, totalMB: 0 });
    try {
      const buildRes = await fetch(packageBuildUrl(system, korean), { method: "POST" });
      if (!buildRes.ok) {
        const detail = await buildRes.json().catch(() => ({}));
        throw new Error(detail.detail || t("Download failed ({status})", { status: buildRes.status }));
      }
      const { ready, job_id } = await buildRes.json();

      if (!ready && job_id) {
        jobIdRef.current = job_id;
        for (;;) {
          if (cancelledRef.current) { setJob(null); return; }
          const jr = await fetch(jobUrl(job_id), { cache: "no-store" });
          if (!jr.ok) throw new Error(t("Download failed ({status})", { status: jr.status }));
          const jd = await jr.json();
          if (jd.status === "done") break;
          if (jd.status === "cancelled") { setJob(null); return; }
          if (jd.status === "failed") throw new Error(jd.message || t("Download failed"));
          const mb = parseMB(jd.message);
          setJob({
            phase: "building", label: fallbackName,
            progress: jd.progress || 0,
            doneMB: mb ? mb.doneMB : 0, totalMB: mb ? mb.totalMB : 0,
          });
          await sleep(500);
        }
      }
      jobIdRef.current = null;
      await streamDownload(packageUrl(system, korean), fallbackName, knownTotal);
    } catch (e) {
      if (e.name === "AbortError") {
        setJob(null);
      } else {
        setJob({ phase: "error", error: e.message || t("Download failed") });
        setTimeout(() => setJob(null), 2600);
      }
    } finally {
      activeRef.current = false;
      abortRef.current = null;
      jobIdRef.current = null;
    }
  }, [t, streamDownload]);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    // Building: tell the server to stop compressing (frees the worker + temp file).
    if (jobIdRef.current) {
      fetch(jobCancelUrl(jobIdRef.current), { method: "POST" }).catch(() => {});
    }
    // Downloading: abort the in-flight stream.
    abortRef.current?.abort();
  }, []);

  const phase = job?.phase;
  const building = phase === "building";
  const pct = building
    ? Math.round((job.progress || 0) * 100)
    : (job && job.total ? Math.min(100, Math.round((job.received / job.total) * 100)) : 0);
  const indeterminate = building && !job.totalMB;   // before the first progress tick

  const title = phase === "error" ? t("● Failed")
    : building ? t("Compressing…")
    : t("Downloading…");
  const meta = phase === "error" ? job.error
    : building
      ? (job.totalMB ? `${pct}%  ·  ${job.doneMB} / ${job.totalMB} MB` : t("Preparing…"))
      : (job && job.total
          ? `${pct}%  ·  ${formatBytes(job.received)} / ${formatBytes(job.total)}`
          : t("Receiving {size}…", { size: formatBytes(job?.received || 0) }));

  return (
    <DownloadCtx.Provider value={{ download, downloadPackage, busy: !!job }}>
      {children}
      {job && (
        <div className="dl-overlay" role="dialog" aria-label={t("Download progress")}>
          <div className="dl-panel">
            <div className="dl-title">{title}</div>
            <div className={`dl-bar ${indeterminate && phase !== "error" ? "indet" : ""} ${phase === "error" ? "err" : ""}`}>
              <div className="dl-fill" style={indeterminate ? undefined : { width: `${pct}%` }} />
            </div>
            <div className="dl-meta">{meta}</div>
            {phase !== "error" && (
              <button type="button" className="dl-cancel" onClick={cancel}>{t("Cancel")}</button>
            )}
          </div>
        </div>
      )}
    </DownloadCtx.Provider>
  );
}
