import React, { useEffect, useRef, useState } from "react";
import { Clapperboard, Upload, Loader, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { uploadVideo, getJob, getHealth } from "../api.js";
import { Dropzone, ProgressBar } from "../components.jsx";
import { useT } from "../i18n.jsx";

export default function VideoTab({ onChanged }) {
  const t = useT();
  const [job, setJob] = useState(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [ffmpeg, setFfmpeg] = useState(true);
  const [mode, setMode] = useState("fit");  // fit | fill | stretch
  const timer = useRef(null);

  useEffect(() => {
    getHealth().then((h) => setFfmpeg(h.ffmpeg));
    return () => clearInterval(timer.current);
  }, []);

  async function handleFiles(files, onProgress) {
    const file = files[0];
    if (!file) return;
    setError(""); setName(file.name); setJob({ status: "encoding", progress: 0.05 });
    try {
      const res = await uploadVideo(file, onProgress, { mode });
      poll(res.job_id);
    } catch (e) {
      setError(e.message); setJob(null);
    }
  }

  function poll(jobId) {
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const j = await getJob(jobId);
        setJob(j);
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
        <Clapperboard size={13} aria-hidden /> {t("Video → encoded to MJPEG .avi (320×240·30fps·mono) and stored in /media")}
      </div>
      {!ffmpeg && (
        <div className="badge failed">
          <AlertTriangle size={11} strokeWidth={2.5} aria-hidden /> {t("ffmpeg is not available on the server")}
        </div>
      )}

      <Dropzone
        accept="video/*"
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag a video here or click (mp4/mov/mkv…)")}
          </span>
        }
        onFiles={handleFiles}
      />

      <label className="row" style={{ gap: 6 }}>
        <span className="muted">{t("Screen fit")}</span>
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="fit">{t("Fit (letterbox)")}</option>
          <option value="fill">{t("Fill (crop)")}</option>
          <option value="stretch">{t("Stretch (distort)")}</option>
        </select>
      </label>

      {job && (
        <div className="stack">
          <div className="row">
            <span className="muted">{name}</span>
            <span className="muted">
              {job.status === "done" ? (
                <><CheckCircle2 size={13} strokeWidth={2.5} aria-hidden /> {t("Done")}</>
              ) : job.status === "failed" ? (
                <><XCircle size={13} strokeWidth={2.5} aria-hidden /> {t("Failed")}</>
              ) : (
                <><Loader size={13} strokeWidth={2.5} className="spin" aria-hidden /> {t("Encoding…")}</>
              )}
            </span>
          </div>
          <ProgressBar value={job.status === "done" ? 1 : job.progress} />
          {job.status === "failed" && <div className="badge failed">{job.message}</div>}
        </div>
      )}

      {error && <div className="badge failed">{error}</div>}
    </div>
  );
}
