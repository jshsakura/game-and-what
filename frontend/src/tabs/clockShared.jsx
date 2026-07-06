import React from "react";
import Cropper from "react-easy-crop";

// The clock screen is 320×240 — both clock tools (bg.gif and the .565 album)
// target exactly that frame, and share the drag & zoom cropper below.
export const SCREEN_W = 320;
export const SCREEN_H = 240;
export const SCREEN_ASPECT = SCREEN_W / SCREEN_H;
// Zoom 1 = the largest 4:3 window that fits the source; the crop box is position-
// restricted so it can never leave the original frame (no accidental black bars).
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 4;

export const FIT_MODES = [
  ["custom", "Custom (drag & zoom)"],
  ["fill", "Fill (crop)"],
  ["fit", "Fit (letterbox)"],
  ["stretch", "Stretch (distort)"],
];

// Screen-fit selector — how the source maps onto the 320×240 clock screen.
export function FitSelect({ mode, setMode, t }) {
  return (
    <div className="row" style={{ gap: 9, alignItems: "center" }}>
      <span className="muted">{t("Screen fit")}</span>
      <span className="search-scope fit-scope" role="group" aria-label={t("Screen fit")}>
        {FIT_MODES.map(([key, label]) => (
          <button key={key} type="button" className={`scope-btn ${mode === key ? "on" : ""}`} onClick={() => setMode(key)}>
            {t(label)}
          </button>
        ))}
      </span>
    </div>
  );
}

// Drag & zoom crop stage locked to the clock's 4:3 and to the source frame.
// Takes an image/GIF (url) or a video (url + isVideo) and reports the selected
// area via onArea(areaPct, areaPx) — percent for the server, pixels for canvases.
export function CropStage({ url, isVideo, crop, zoom, onCrop, onZoom, onArea, t }) {
  const media = isVideo ? { video: url } : { image: url };
  return (
    <>
      <div className="cropper-stage">
        <Cropper
          {...media}
          crop={crop}
          zoom={zoom}
          aspect={SCREEN_ASPECT}
          minZoom={MIN_ZOOM}
          maxZoom={MAX_ZOOM}
          onCropChange={onCrop}
          onZoomChange={onZoom}
          onCropAreaChange={onArea}
        />
      </div>
      <input
        className="cropper-zoom" type="range" min={MIN_ZOOM} max={MAX_ZOOM} step="0.01"
        value={zoom}
        onChange={(e) => onZoom(Number(e.target.value))}
        aria-label={t("Drag to move · scroll to zoom")}
      />
      <div className="muted" style={{ textAlign: "center", fontSize: 11 }}>
        {t("Drag to move · scroll to zoom")}
      </div>
    </>
  );
}

export function prepCanvas(canvas) {
  canvas.width = SCREEN_W;
  canvas.height = SCREEN_H;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingQuality = "high";
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, SCREEN_W, SCREEN_H);
  return ctx;
}

// Place the source image onto a 320×240 canvas per the fit mode (all client-side,
// so the preview IS the exact output).
export function drawFitted(canvas, img, mode) {
  const ctx = prepCanvas(canvas);
  const ir = img.naturalWidth / img.naturalHeight;
  let dw, dh;
  if (mode === "stretch") {
    dw = SCREEN_W; dh = SCREEN_H;
  } else if (mode === "fill") {          // cover: fill the screen, crop the overflow
    if (ir > SCREEN_ASPECT) { dh = SCREEN_H; dw = SCREEN_H * ir; }
    else { dw = SCREEN_W; dh = SCREEN_W / ir; }
  } else {                                // fit: whole image, letterbox bars
    if (ir > SCREEN_ASPECT) { dw = SCREEN_W; dh = SCREEN_W / ir; }
    else { dh = SCREEN_H; dw = SCREEN_H * ir; }
  }
  ctx.drawImage(img, (SCREEN_W - dw) / 2, (SCREEN_H - dh) / 2, dw, dh);
}

// User-set crop region (source pixels) → full 320×240.
export function drawCustomCrop(canvas, img, area) {
  const ctx = prepCanvas(canvas);
  try { ctx.drawImage(img, area.x, area.y, area.width, area.height, 0, 0, SCREEN_W, SCREEN_H); } catch (_) {}
}

// Canvas RGBA -> raw RGB565 little-endian (R high), the firmware's native pixel.
export function canvasToRgb565(canvas) {
  const { data } = canvas.getContext("2d").getImageData(0, 0, SCREEN_W, SCREEN_H);
  const out = new Uint8Array(SCREEN_W * SCREEN_H * 2);
  for (let i = 0, j = 0; i < data.length; i += 4, j += 2) {
    const v = ((data[i] & 0xf8) << 8) | ((data[i + 1] & 0xfc) << 3) | (data[i + 2] >> 3);
    out[j] = v & 0xff;          // little-endian: low byte first
    out[j + 1] = (v >> 8) & 0xff;
  }
  return out;
}
