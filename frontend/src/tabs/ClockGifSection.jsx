import React, { useEffect, useRef, useState } from "react";
import { Clapperboard, Upload, Loader, Info, Download, Save, X } from "lucide-react";
import { uploadClockBackground, saveClockFile, formatBytes } from "../api.js";
import { downloadBlob } from "../localencode.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";
import { FitSelect, CropStage } from "./clockShared.jsx";
import ClockFileList from "./ClockFileList.jsx";

// Clock background GIF: one image/video/GIF → a device-safe 320×240 clock GIF.
// The user frames the shot with the shared drag & zoom cropper (the crop rectangle
// goes to the server as source fractions), then the server walks a quality ladder
// (palette + fps + gifsicle lossy) until the file fits the device budget — any
// source comes out playable on the clock, keeping the original loop/motion.
//
// Two endings, same conversion: KEEP it in the library (/clock/gif, listed below,
// shipped in the SD zip) or just download it. Keeping is the default — a converted
// background that lives only in the browser's Downloads folder is one you lose.
export default function ClockGifSection({ gifs = [], onChanged }) {
  const t = useT();
  const toast = useToast();
  const [mode, setMode] = useState("custom");
  const [src, setSrc] = useState(null);       // { file, url, isVideo }
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const areaPctRef = useRef(null);            // crop rect in source PERCENT (server-bound)
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // { inBytes, outBytes }

  // Blob URL lives as long as the picked source — swap/unmount revokes it.
  useEffect(() => () => { if (src) URL.revokeObjectURL(src.url); }, [src]);

  function handleFiles(files) {
    const file = Array.from(files)[0];
    if (!file || !(file.type.startsWith("image/") || file.type.startsWith("video/"))) {
      toast.error(t("Pick an image or video file"));
      return;
    }
    setSrc({ file, url: URL.createObjectURL(file), isVideo: file.type.startsWith("video/") });
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    areaPctRef.current = null;
    setResult(null);
  }

  // The cropper's rectangle as source fractions — what both endpoints take.
  function cropParam() {
    const a = areaPctRef.current;
    return mode === "custom" && a
      ? [a.x / 100, a.y / 100, a.width / 100, a.height / 100].map((v) => v.toFixed(5)).join(",")
      : "";
  }

  // Convert → store in the library. The source is cleared afterwards: the result
  // is now a row in the list below, which is the point.
  async function save() {
    if (!src || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const row = await saveClockFile("gif", src.file, null, { mode, crop: cropParam() });
      URL.revokeObjectURL(src.url);
      setSrc(null);
      onChanged?.();
      toast.success(t("Saved as {name} — it stays here and ships in the SD ZIP", { name: row.stored_name }));
    } catch (e) {
      toast.error(e.message || t("Convert failed"));
    } finally {
      setBusy(false);
    }
  }

  // Convert → download only. Nothing is stored server-side.
  async function convert() {
    if (!src || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const blob = await uploadClockBackground(src.file, null, { mode, crop: cropParam() });
      downloadBlob(blob, "bg.gif");
      setResult({ inBytes: src.file.size, outBytes: blob.size });
      toast.success(t("Downloaded bg.gif — copy it into /clock/gif on the SD card"));
    } catch (e) {
      toast.error(e.message || t("Convert failed"));
    } finally {
      setBusy(false);
    }
  }

  const savedPct = result && result.inBytes > 0
    ? Math.max(0, Math.round((1 - result.outBytes / result.inBytes) * 100))
    : 0;

  return (
    <div className="stack">
      <div className="muted">
        <Clapperboard size={13} aria-hidden /> {t("Turn any image or video into a 320×240 clock background. A still image becomes a static background; a video/GIF loops on the device.")}
      </div>
      <div className="vtab-safe">
        <Info size={13} strokeWidth={2.5} aria-hidden />
        <span>{t("The screen is 320×240 — the output is pinned to that size (a larger source only wastes space). Saved backgrounds are kept in")} <b>/clock/gif</b> {t("and travel with the SD ZIP; the clock can pick any .gif in that folder, so keep several. Or convert without saving and just download the file.")}</span>
      </div>

      <Dropzone
        accept="image/*,video/*,.gif"
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag an image or video here or click")}
          </span>
        }
        onFiles={handleFiles}
      />

      {src && (
        <div className="stack">
          <FitSelect mode={mode} setMode={setMode} t={t} />

          {mode === "custom" && (
            <CropStage
              key={src.url}
              url={src.url}
              isVideo={src.isVideo}
              crop={crop}
              zoom={zoom}
              onCrop={setCrop}
              onZoom={setZoom}
              onArea={(pct) => { areaPctRef.current = pct; }}
              t={t}
            />
          )}

          <div className="row clock-file-row">
            <span className="muted clock-file-name" title={src.file.name}>
              {src.file.name} ({formatBytes(src.file.size)})
              {result && (
                <> → <b>bg.gif</b> {formatBytes(result.outBytes)} (−{savedPct}%)</>
              )}
            </span>
            <button type="button" className="scope-btn" onClick={() => setSrc(null)} disabled={busy} aria-label={t("Remove")} title={t("Remove")}>
              <X size={14} strokeWidth={2.5} aria-hidden />
            </button>
            <button type="button" className="scope-btn" onClick={convert} disabled={busy} title={t("Nothing is stored on the server")}>
              <Download size={14} strokeWidth={2.5} aria-hidden /> {t("Download only")}
            </button>
            <button type="button" className="scope-btn on" onClick={save} disabled={busy}>
              {busy
                ? <><Loader size={14} strokeWidth={2.5} className="spin" aria-hidden /> {t("Converting…")}</>
                : <><Save size={14} strokeWidth={2.5} aria-hidden /> {t("Convert & keep")}</>}
            </button>
          </div>
        </div>
      )}

      <ClockFileList kind="gif" files={gifs} onChanged={onChanged} />
    </div>
  );
}
