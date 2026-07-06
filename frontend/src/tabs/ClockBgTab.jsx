import React, { useState } from "react";
import { Clock, Upload, Loader, CheckCircle2, XCircle, Info, Download } from "lucide-react";
import { uploadClockBackground } from "../api.js";
import { downloadBlob } from "../localencode.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";

// Screen-fit selector — how the source maps onto the 320×240 clock screen.
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

// Clock background: convert one image/video into a 320×240 bg.gif and download it.
// Stateless — the result isn't part of the SD package; the user drops bg.gif into
// /clock/ themselves (the firmware Clock app reads /clock/bg.gif).
export default function ClockBgTab() {
  const t = useT();
  const toast = useToast();
  const [mode, setMode] = useState("fit");
  const [last, setLast] = useState(null); // { name, status:'ok'|'err', error }

  async function handleFiles(files, onProgress) {
    const file = Array.from(files)[0];
    if (!file) return;
    setLast({ name: file.name, status: "up" });
    try {
      const blob = await uploadClockBackground(file, onProgress, { mode });
      downloadBlob(blob, "bg.gif");
      setLast({ name: file.name, status: "ok" });
      toast.success(t("Downloaded bg.gif — copy it to /clock/ on the SD card"));
    } catch (e) {
      setLast({ name: file.name, status: "err", error: e.message });
      toast.error(e.message || t("Convert failed"));
    }
  }

  return (
    <div className="stack">
      <div className="muted">
        <Clock size={13} aria-hidden /> {t("Turn any image or video into a 320×240 clock background. A still image becomes a static background; a video/GIF loops on the device.")}
      </div>
      <div className="vtab-safe">
        <Info size={13} strokeWidth={2.5} aria-hidden /> {t("The screen is 320×240 — the output is pinned to that size (a larger source only wastes space). Download bg.gif, then copy it to")} <b>/clock/bg.gif</b> {t("on the SD card and pick “GIF” as the clock background.")}
      </div>

      <FitSelect mode={mode} setMode={setMode} t={t} />

      <Dropzone
        accept="image/*,video/*,.gif"
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag an image or video here or click")}
          </span>
        }
        onFiles={handleFiles}
      />

      {last && (
        <div className="row">
          <span className="muted">{last.name}</span>
          <span className="muted">
            {last.status === "ok" ? (
              <><CheckCircle2 size={13} strokeWidth={2.5} aria-hidden /> <Download size={13} strokeWidth={2.5} aria-hidden /> {t("bg.gif downloaded")}</>
            ) : last.status === "err" ? (
              <><XCircle size={13} strokeWidth={2.5} aria-hidden /> {last.error || t("Failed")}</>
            ) : (
              <><Loader size={13} strokeWidth={2.5} className="spin" aria-hidden /> {t("Converting…")}</>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
