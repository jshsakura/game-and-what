import React, { createContext, useContext, useState, useCallback, useRef } from "react";
import { formatBytes } from "./api.js";
import { useT } from "./i18n.jsx";

// Streams a download with a centered 8-bit progress bar (instead of a plain
// browser <a download>, which shows nothing while a big SD ZIP is built/sent).
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

export function DownloadProvider({ children }) {
  const t = useT();
  const [job, setJob] = useState(null);   // {label, received, total, building, error}
  const abortRef = useRef(null);
  const activeRef = useRef(false);

  const download = useCallback(async (url, fallbackName = "download.zip", knownTotal = 0) => {
    if (activeRef.current) return;          // one at a time
    activeRef.current = true;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setJob({ label: fallbackName, received: 0, total: knownTotal, building: true });
    try {
      const res = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
      if (!res.ok) throw new Error(t("Download failed ({status})", { status: res.status }));
      const total = Number(res.headers.get("Content-Length")) || knownTotal || 0;
      const name = filenameFromHeader(res.headers.get("Content-Disposition"), fallbackName);
      const reader = res.body.getReader();
      const chunks = [];
      let received = 0;
      setJob({ label: name, received: 0, total, building: false });
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.length;
        setJob({ label: name, received, total, building: false });
      }
      const blob = new Blob(chunks, { type: res.headers.get("Content-Type") || "application/octet-stream" });
      const obj = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = obj;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(obj), 1000);
      setJob(null);
    } catch (e) {
      if (e.name === "AbortError") {
        setJob(null);
      } else {
        setJob((j) => (j ? { ...j, error: e.message || t("Download failed") } : null));
        setTimeout(() => setJob(null), 2600);
      }
    } finally {
      activeRef.current = false;
      abortRef.current = null;
    }
  }, [t]);

  const cancel = () => {
    abortRef.current?.abort();
  };

  const pct = job && job.total ? Math.min(100, Math.round((job.received / job.total) * 100)) : 0;
  const indeterminate = !!job && (job.building || !job.total);

  return (
    <DownloadCtx.Provider value={{ download, busy: !!job }}>
      {children}
      {job && (
        <div className="dl-overlay" role="dialog" aria-label={t("Download progress")}>
          <div className="dl-panel">
            <div className="dl-title">
              {job.error ? t("● Failed") : job.building ? t("Preparing…") : t("Downloading…")}
            </div>
            <div className={`dl-bar ${indeterminate && !job.error ? "indet" : ""} ${job.error ? "err" : ""}`}>
              <div className="dl-fill" style={indeterminate ? undefined : { width: `${pct}%` }} />
            </div>
            <div className="dl-meta">
              {job.error
                ? job.error
                : job.total
                  ? `${pct}%  ·  ${formatBytes(job.received)} / ${formatBytes(job.total)}`
                  : t("Receiving {size}…", { size: formatBytes(job.received) })}
            </div>
            {!job.error && (
              <button type="button" className="dl-cancel" onClick={cancel}>{t("Cancel")}</button>
            )}
          </div>
        </div>
      )}
    </DownloadCtx.Provider>
  );
}
