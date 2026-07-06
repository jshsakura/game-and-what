import React, { useEffect, useRef, useState } from "react";
import { Clock, Upload, Info, Download, ImageOff, X } from "lucide-react";
import Cropper from "react-easy-crop";
import { downloadBlob } from "../localencode.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";

// The clock screen is 320×240. Photos go on the SD card as RAW RGB565 (.565):
// exactly 320*240*2 bytes, no header — the firmware Clock app blits them straight.
const SCREEN_W = 320;
const SCREEN_H = 240;
const SCREEN_ASPECT = SCREEN_W / SCREEN_H;
// Custom-crop zoom range: below 1 zooms out past the frame → black letterbox.
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 4;
const STEM_MAX = 40;
// Breathing room between files so the browser accepts every download in a batch.
const BATCH_DOWNLOAD_GAP_MS = 300;

const FIT_MODES = [
  ["custom", "Custom (drag & zoom)"],
  ["fill", "Fill (crop)"],
  ["fit", "Fit (letterbox)"],
  ["stretch", "Stretch (distort)"],
];

// Screen-fit selector — how the source maps onto the 320×240 clock screen.
function FitSelect({ mode, setMode, t }) {
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

function prepCanvas(canvas) {
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
function drawFitted(canvas, img, mode) {
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

// User-set crop region (source pixels) → full 320×240. Zoomed-out regions extend
// past the image; those pixels stay the black fill (letterbox).
function drawCustomCrop(canvas, img, area) {
  const ctx = prepCanvas(canvas);
  try { ctx.drawImage(img, area.x, area.y, area.width, area.height, 0, 0, SCREEN_W, SCREEN_H); } catch (_) {}
}

function renderItem(canvas, item) {
  if (item.mode === "custom" && item.areaPx) drawCustomCrop(canvas, item.el, item.areaPx);
  else drawFitted(canvas, item.el, item.mode === "custom" ? "fill" : item.mode);
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

const pad2 = (n) => String(n).padStart(2, "0");

function batchStamp() {
  const d = new Date();
  return `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}_${pad2(d.getHours())}${pad2(d.getMinutes())}`;
}

// Collision-free output names for the whole batch. Names that sanitize down to
// nothing (emoji/Hangul-only → underscores) fall back to date_time_seq; duplicate
// stems get a _2/_3… suffix so no download overwrites another.
function outputNames(items, stamp) {
  const used = new Set();
  return items.map((item, i) => {
    let stem = (item.name || "")
      .replace(/\.[^.]+$/, "")
      .replace(/[^\w\-]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, STEM_MAX);
    if (stem.replace(/[_\-]/g, "").length < 2) stem = `${stamp}_${pad2(i + 1)}`;
    let name = `${stem}.565`;
    for (let n = 2; used.has(name); n++) name = `${stem}_${n}.565`;
    used.add(name);
    return name;
  });
}

// Clock photo tool: convert photos (multiple at once) into 320×240 .565 files the
// album reads. Each photo keeps its own fit mode / crop; the custom mode lets the
// user drag & zoom the region. Fully client-side — no upload, exact pixels.
export default function ClockBgTab() {
  const t = useT();
  const toast = useToast();
  const [items, setItems] = useState([]);        // { id, name, url, el, mode, crop, zoom, areaPx }
  const [selectedId, setSelectedId] = useState(null);
  const canvasRef = useRef(null);
  const idRef = useRef(0);
  const stampRef = useRef(null);
  if (stampRef.current === null) stampRef.current = batchStamp();

  const selected = items.find((it) => it.id === selectedId) || null;
  const selectedIndex = items.findIndex((it) => it.id === selectedId);
  const names = outputNames(items, stampRef.current);

  const patchItem = (id, patch) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));

  // (re)draw whenever the selected photo or its settings change — this canvas IS
  // the exact output preview.
  useEffect(() => {
    if (selected && canvasRef.current) renderItem(canvasRef.current, selected);
  }, [selected]);

  // Blob URLs live as long as the item (thumbnails + cropper) — revoke on unmount.
  const itemsRef = useRef(items);
  itemsRef.current = items;
  useEffect(() => () => { itemsRef.current.forEach((it) => URL.revokeObjectURL(it.url)); }, []);

  function handleFiles(files) {
    const images = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (!images.length) {
      toast.error(t("Pick an image file"));
      return;
    }
    images.forEach((file) => {
      const url = URL.createObjectURL(file);
      const el = new Image();
      el.onload = () => {
        const id = ++idRef.current;
        setItems((prev) => [...prev, { id, name: file.name, url, el, mode: "custom", crop: { x: 0, y: 0 }, zoom: 1, areaPx: null }]);
        setSelectedId((cur) => cur ?? id);
      };
      el.onerror = () => { toast.error(t("Couldn’t read that image")); URL.revokeObjectURL(url); };
      el.src = url;
    });
  }

  function removeItem(id) {
    const gone = items.find((it) => it.id === id);
    if (gone) URL.revokeObjectURL(gone.url);
    const next = items.filter((it) => it.id !== id);
    setItems(next);
    if (selectedId === id) setSelectedId(next[0]?.id ?? null);
  }

  function downloadOne(item, name) {
    const canvas = document.createElement("canvas");
    renderItem(canvas, item);
    downloadBlob(new Blob([canvasToRgb565(canvas)], { type: "application/octet-stream" }), name);
  }

  function downloadSelected() {
    if (!selected) return;
    downloadOne(selected, names[selectedIndex]);
    toast.success(t("Saved .565 — copy it into /clock/album on the SD card"));
  }

  async function downloadAll() {
    for (let i = 0; i < items.length; i++) {
      downloadOne(items[i], names[i]);
      await new Promise((resolve) => setTimeout(resolve, BATCH_DOWNLOAD_GAP_MS));
    }
    toast.success(t("Saved {n} .565 files — copy them into /clock/album on the SD card", { n: items.length }));
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
        multiple
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag photos here or click (multiple allowed)")}
          </span>
        }
        onFiles={handleFiles}
      />

      {items.length > 0 && (
        <div className="clock-thumbs">
          {items.map((it, i) => (
            <span key={it.id} className={`clock-thumb ${it.id === selectedId ? "on" : ""}`}>
              <button type="button" className="clock-thumb-pick" onClick={() => setSelectedId(it.id)} title={names[i]}>
                <img src={it.url} alt={it.name} />
              </button>
              <button type="button" className="clock-thumb-x" onClick={() => removeItem(it.id)} aria-label={t("Remove")} title={t("Remove")}>
                <X size={11} strokeWidth={3} aria-hidden />
              </button>
            </span>
          ))}
        </div>
      )}

      {selected && (
        <div className="stack">
          <FitSelect mode={selected.mode} setMode={(m) => patchItem(selected.id, { mode: m })} t={t} />

          {selected.mode === "custom" && (
            <>
              <div className="cropper-stage">
                <Cropper
                  key={selected.id}
                  image={selected.url}
                  crop={selected.crop}
                  zoom={selected.zoom}
                  aspect={SCREEN_ASPECT}
                  minZoom={MIN_ZOOM}
                  maxZoom={MAX_ZOOM}
                  restrictPosition={false}
                  onCropChange={(c) => patchItem(selected.id, { crop: c })}
                  onZoomChange={(z) => patchItem(selected.id, { zoom: z })}
                  onCropAreaChange={(_, areaPx) => patchItem(selected.id, { areaPx })}
                />
              </div>
              <input
                className="cropper-zoom" type="range" min={MIN_ZOOM} max={MAX_ZOOM} step="0.01"
                value={selected.zoom}
                onChange={(e) => patchItem(selected.id, { zoom: Number(e.target.value) })}
                aria-label={t("Drag to move · scroll to zoom")}
              />
              <div className="muted" style={{ textAlign: "center", fontSize: 11 }}>
                {t("Drag to move · scroll to zoom")}
              </div>
            </>
          )}

          <div className="row" style={{ justifyContent: "center" }}>
            {/* 320×240 preview — exactly the pixels that end up in the .565 */}
            <canvas
              ref={canvasRef}
              style={{ width: 320, height: 240, maxWidth: "100%", borderRadius: 8, border: "1px solid #2faa5540", background: "#000" }}
              aria-label={t("Preview")}
            />
          </div>

          <div className="row clock-file-row">
            <span className="muted clock-file-name" title={`${selected.name} → ${names[selectedIndex]}`}>
              {selected.name} → <b>{names[selectedIndex]}</b> (320×240)
            </span>
            <button type="button" className="scope-btn on" onClick={downloadSelected}>
              <Download size={14} strokeWidth={2.5} aria-hidden /> {t("Download .565")}
            </button>
            {items.length > 1 && (
              <button type="button" className="scope-btn" onClick={downloadAll}>
                <Download size={14} strokeWidth={2.5} aria-hidden /> {t("Download all ({n})", { n: items.length })}
              </button>
            )}
          </div>
        </div>
      )}

      {items.length === 0 && (
        <div className="muted" style={{ textAlign: "center", opacity: 0.6 }}>
          <ImageOff size={14} aria-hidden /> {t("No photo yet — drop one above to preview the crop.")}
        </div>
      )}
    </div>
  );
}
