import React, { useEffect, useRef, useState } from "react";
import { Clock, Upload, Info, Download, ImageOff } from "lucide-react";
import { downloadBlob } from "../localencode.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";

// The clock screen is 320×240. Photos go on the SD card as RAW RGB565 (.565):
// exactly 320*240*2 bytes, no header — the firmware Clock app blits them straight.
const SCREEN_W = 320;
const SCREEN_H = 240;

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

// Place the source image onto a 320×240 canvas per the fit mode (all client-side,
// so the preview IS the exact output).
function drawFitted(canvas, img, mode) {
  canvas.width = SCREEN_W;
  canvas.height = SCREEN_H;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, SCREEN_W, SCREEN_H);
  const ir = img.naturalWidth / img.naturalHeight;
  const cr = SCREEN_W / SCREEN_H;
  let dw, dh;
  if (mode === "stretch") {
    dw = SCREEN_W; dh = SCREEN_H;
  } else if (mode === "fill") {          // cover: fill the screen, crop the overflow
    if (ir > cr) { dh = SCREEN_H; dw = SCREEN_H * ir; }
    else { dw = SCREEN_W; dh = SCREEN_W / ir; }
  } else {                                // fit: whole image, letterbox bars
    if (ir > cr) { dw = SCREEN_W; dh = SCREEN_W / ir; }
    else { dh = SCREEN_H; dw = SCREEN_H * ir; }
  }
  ctx.drawImage(img, (SCREEN_W - dw) / 2, (SCREEN_H - dh) / 2, dw, dh);
}

// Canvas RGBA -> raw RGB565 little-endian (R high), the firmware's native pixel.
function canvasToRgb565(canvas) {
  const { data } = canvas.getContext("2d").getImageData(0, 0, SCREEN_W, SCREEN_H);
  const out = new Uint8Array(SCREEN_W * SCREEN_H * 2);
  for (let i = 0, j = 0; i < data.length; i += 4, j += 2) {
    const v = ((data[i] & 0xf8) << 8) | ((data[i + 1] & 0xfc) << 3) | (data[i + 2] >> 3);
    out[j] = v & 0xff;          // little-endian: low byte first
    out[j + 1] = (v >> 8) & 0xff;
  }
  return out;
}

function safe565Name(sourceName) {
  const stem = (sourceName || "photo").replace(/\.[^.]+$/, "").replace(/[^\w\-]+/g, "_").slice(0, 40) || "photo";
  return `${stem}.565`;
}

// Clock photo tool: convert one image into a 320×240 .565 the album reads, with a
// live crop/fit preview. Fully client-side — no upload, exact pixels.
export default function ClockBgTab() {
  const t = useT();
  const toast = useToast();
  const [mode, setMode] = useState("fill");
  const [img, setImg] = useState(null);     // { el, name }
  const canvasRef = useRef(null);

  // (re)draw whenever the image or fit mode changes — this canvas IS the preview
  useEffect(() => {
    if (img && canvasRef.current) drawFitted(canvasRef.current, img.el, mode);
  }, [img, mode]);

  function handleFiles(files) {
    const file = Array.from(files)[0];
    if (!file || !file.type.startsWith("image/")) {
      toast.error(t("Pick an image file"));
      return;
    }
    const url = URL.createObjectURL(file);
    const el = new Image();
    el.onload = () => { setImg({ el, name: file.name }); URL.revokeObjectURL(url); };
    el.onerror = () => { toast.error(t("Couldn’t read that image")); URL.revokeObjectURL(url); };
    el.src = url;
  }

  function download() {
    if (!canvasRef.current || !img) return;
    const bytes = canvasToRgb565(canvasRef.current);
    downloadBlob(new Blob([bytes], { type: "application/octet-stream" }), safe565Name(img.name));
    toast.success(t("Saved .565 — copy it into /clock/album on the SD card"));
  }

  return (
    <div className="stack">
      <div className="muted">
        <Clock size={13} aria-hidden /> {t("Turn photos into clock backgrounds. Each becomes a 320×240 .565 file; the clock cycles through everything in /clock/album.")}
      </div>
      <div className="vtab-safe">
        <Info size={13} strokeWidth={2.5} aria-hidden />
        <span>{t("Converted right here in your browser (nothing is uploaded). Download the .565 and copy it into")} <b>/clock/album</b> {t("on the SD card, then pick “Photo Album” as the clock background. Add as many as you like.")}</span>
      </div>

      <Dropzone
        accept="image/*"
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag a photo here or click")}
          </span>
        }
        onFiles={handleFiles}
      />

      {img && (
        <div className="stack">
          <FitSelect mode={mode} setMode={setMode} t={t} />
          <div className="row" style={{ justifyContent: "center" }}>
            {/* 320×240 preview, shown at 2× so the crop is easy to judge */}
            <canvas
              ref={canvasRef}
              style={{ width: 320, height: 240, maxWidth: "100%", borderRadius: 8, border: "1px solid #2faa5540", background: "#000" }}
              aria-label={t("Preview")}
            />
          </div>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <span className="muted">{img.name} → <b>{safe565Name(img.name)}</b> (320×240)</span>
            <button type="button" className="scope-btn on" onClick={download}>
              <Download size={14} strokeWidth={2.5} aria-hidden /> {t("Download .565")}
            </button>
          </div>
        </div>
      )}

      {!img && (
        <div className="muted" style={{ textAlign: "center", opacity: 0.6 }}>
          <ImageOff size={14} aria-hidden /> {t("No photo yet — drop one above to preview the crop.")}
        </div>
      )}
    </div>
  );
}
