import React, { useEffect, useRef, useState } from "react";
import { Clock, Upload, Info, Download, ImageOff, X } from "lucide-react";
import { downloadBlob } from "../localencode.js";
import { buildZip } from "../zip.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";
import {
  FitSelect, CropStage, drawFitted, drawCustomCrop, canvasToRgb565,
} from "./clockShared.jsx";

// Photos go on the SD card as RAW RGB565 (.565): exactly 320*240*2 bytes, no
// header — the firmware Clock app blits them straight.
const STEM_MAX = 40;

function renderItem(canvas, item) {
  if (item.mode === "custom" && item.areaPx) drawCustomCrop(canvas, item.el, item.areaPx);
  else drawFitted(canvas, item.el, item.mode === "custom" ? "fill" : item.mode);
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

// Clock photo album: convert photos (multiple at once) into 320×240 .565 files.
// Each photo keeps its own fit mode / crop; the custom mode is the shared drag &
// zoom cropper. Fully client-side — no upload, exact pixels.
export default function ClockAlbumSection() {
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

  function renderBytes(item) {
    const canvas = document.createElement("canvas");
    renderItem(canvas, item);
    return canvasToRgb565(canvas);
  }

  function downloadSelected() {
    if (!selected) return;
    downloadBlob(new Blob([renderBytes(selected)], { type: "application/octet-stream" }), names[selectedIndex]);
    toast.success(t("Saved .565 — copy it into /clock/album on the SD card"));
  }

  // One ZIP for the whole batch — N separate downloads trip the browser's
  // multi-download blocking and shred filenames.
  function downloadAll() {
    const files = items.map((item, i) => ({ name: names[i], data: renderBytes(item) }));
    downloadBlob(buildZip(files), `clock_album_${stampRef.current}.zip`);
    toast.success(t("Saved {n} .565 files as one ZIP — unzip into /clock/album on the SD card", { n: items.length }));
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
            <CropStage
              key={selected.id}
              url={selected.url}
              crop={selected.crop}
              zoom={selected.zoom}
              onCrop={(c) => patchItem(selected.id, { crop: c })}
              onZoom={(z) => patchItem(selected.id, { zoom: z })}
              onArea={(_, areaPx) => patchItem(selected.id, { areaPx })}
              t={t}
            />
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
