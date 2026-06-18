import React, { useState } from "react";
import { Music, Upload, Loader, CheckCircle2, XCircle } from "lucide-react";
import { uploadMusic } from "../api.js";
import { Dropzone } from "../components.jsx";
import { useT } from "../i18n.jsx";

// MP3 → /music. No conversion: the firmware's Music app reads ID3 tags, album
// art and .lrc lyrics straight from the file, so we just store and ship it.
export default function MusicTab({ onChanged }) {
  const t = useT();
  const [items, setItems] = useState([]); // [{name, status:'up'|'ok'|'err', error}]

  async function handleFiles(files, onProgress) {
    const list = Array.from(files);
    if (!list.length) return;
    const total = list.reduce((s, f) => s + f.size, 0) || 1;
    let done = 0;
    setItems((prev) => [...list.map((f) => ({ name: f.name, status: "up" })), ...prev]);
    for (const f of list) {
      try {
        await uploadMusic(f, (loaded) => onProgress?.(done + loaded, total));
        setItems((prev) => prev.map((it) => (it.name === f.name && it.status === "up" ? { ...it, status: "ok" } : it)));
      } catch (e) {
        setItems((prev) => prev.map((it) => (it.name === f.name && it.status === "up" ? { ...it, status: "err", error: e.message } : it)));
      }
      done += f.size;
    }
    onChanged?.();
  }

  return (
    <div className="stack">
      <div className="muted">
        <Music size={13} aria-hidden /> {t("Keep MP3 as-is,")} <b>{t("extract MP3 from video")}</b>{t(" and store in /music (the device's Music app reads ID3 tags and album art directly)")}
      </div>

      <Dropzone
        accept="audio/mpeg,.mp3,video/*"
        multiple
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag an MP3 or video here or click (video is extracted to mp3)")}
          </span>
        }
        onFiles={handleFiles}
      />

      {items.length > 0 && (
        <div className="stack">
          {items.map((it, i) => (
            <div className="row" key={`${it.name}-${i}`}>
              <span className="muted">{it.name}</span>
              <span className="muted">
                {it.status === "ok" ? (
                  <><CheckCircle2 size={13} strokeWidth={2.5} aria-hidden /> {t("Done")}</>
                ) : it.status === "err" ? (
                  <><XCircle size={13} strokeWidth={2.5} aria-hidden /> {it.error || t("Failed")}</>
                ) : (
                  <><Loader size={13} strokeWidth={2.5} className="spin" aria-hidden /> {t("Uploading…")}</>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
