import React, { useEffect, useState } from "react";
import { Download, Trash2, Pencil, Repeat, Image as ImageIcon, Star, BellRing } from "lucide-react";
import {
  clockFileUrl, clockPreviewUrl, downloadClockFileUrl, deleteClockFile, renameClockFile,
  formatBytes,
} from "../api.js";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";

// What is kept in /clock/<kind>, as a picked-row list with a stage on top.
//
// The stage shows the real thing, not a rendition of it: a GIF and a photo are
// already exactly the 320×240 the device blits (the photo via a server-rendered
// PNG, since a headerless .565 is nothing a browser can display), and an alarm
// plays the very MP3 the clock will loop. Naming matters on the device — the
// Clock app defaults to bg.gif and alarm.mp3 — so the stage carries a rename
// field with those names spelled out.
const KINDS = {
  gif: { defaultName: "bg.gif", Icon: Repeat },
  album: { defaultName: null, Icon: ImageIcon },
  alarm: { defaultName: "alarm.mp3", Icon: BellRing },
};

const stemOf = (name) => name.replace(/\.[^.]+$/, "");

export default function ClockFileList({ kind, files, onChanged }) {
  const t = useT();
  const toast = useToast();
  const [selId, setSelId] = useState(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const conf = KINDS[kind];
  const sel = files.find((f) => f.id === selId) || files[0] || null;

  // A fresh convert lands at the top of the list — drop the manual pick so the
  // stage shows what was just made, not whatever was picked before it.
  const newestId = files[0]?.id;
  useEffect(() => { setSelId(null); }, [newestId]);

  // Follow the selection: the rename field always edits the shown file's name.
  useEffect(() => {
    setName(sel ? stemOf(sel.stored_name) : "");
  }, [sel?.id, sel?.stored_name]);

  if (!files.length) return null;

  const suffix = sel ? sel.stored_name.slice(stemOf(sel.stored_name).length) : "";

  async function rename() {
    const next = name.trim();
    if (!sel || busy || !next || `${next}${suffix}` === sel.stored_name) return;
    setBusy(true);
    try {
      await renameClockFile(kind, sel.id, next);
      onChanged?.();
      toast.success(t("Renamed to {name}", { name: `${next}${suffix}` }));
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  }

  async function remove(file, e) {
    e?.stopPropagation();
    if (busy) return;
    if (!(await toast.confirm(t("Delete '{name}'?", { name: file.stored_name }), { confirmText: t("Delete") }))) return;
    setBusy(true);
    try {
      await deleteClockFile(kind, file.id);
      if (selId === file.id) setSelId(null);
      onChanged?.();
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  }

  const savedPct = (f) => (f.source_bytes > 0
    ? Math.max(0, Math.round((1 - f.size_bytes / f.source_bytes) * 100))
    : null);

  function stageBadge(f) {
    if (kind === "gif") {
      return f.animated
        ? <><Repeat size={11} strokeWidth={2.5} aria-hidden /> {t("Loops")}</>
        : <><ImageIcon size={11} strokeWidth={2.5} aria-hidden /> {t("Still")}</>;
    }
    if (kind === "alarm") {
      return <><BellRing size={11} strokeWidth={2.5} aria-hidden /> {f.duration_s ? `${Math.round(f.duration_s)}s` : t("Loops")}</>;
    }
    return <><ImageIcon size={11} strokeWidth={2.5} aria-hidden /> 320×240</>;
  }

  return (
    <div className="clock-gif-lib">
      {sel && (
        <div className="clock-gif-stage">
          {kind === "alarm" ? (
            <audio key={sel.id} className="music-audio" controls src={clockFileUrl(kind, sel.id)} />
          ) : (
            <img className="clock-gif-big" src={clockPreviewUrl(kind, sel.id)} alt={sel.stored_name} />
          )}
          <div className="clock-gif-stage-meta">
            <span className="clock-gif-badge">{stageBadge(sel)}</span>
            <span className="muted">
              {formatBytes(sel.size_bytes)}
              {savedPct(sel) != null && ` (−${savedPct(sel)}%)`}
            </span>
            <span className="muted clock-gif-origin" title={sel.original_name}>{sel.original_name}</span>
          </div>
          <div className="rename-row">
            <span className="path-prefix">/clock/{kind}/</span>
            <input
              className="text-input"
              value={name}
              disabled={busy}
              spellCheck={false}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && rename()}
            />
            <span className="muted">{suffix}</span>
            <button className="btn" disabled={busy || !name.trim() || `${name.trim()}${suffix}` === sel.stored_name} onClick={rename}>
              <Pencil size={13} strokeWidth={2.5} aria-hidden /> {t("Change")}
            </button>
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            {kind === "gif" && t("Name it bg.gif to make it the one the clock picks by default — every other .gif here can still be chosen on the device.")}
            {kind === "alarm" && t("Name it alarm.mp3 to make it the ring the clock uses by default — every other .mp3 here can still be picked on the device.")}
            {kind === "album" && t("The clock cycles through every photo kept here — /clock/album on the card.")}
          </div>
        </div>
      )}

      <div className="clock-gif-list">
        {files.map((f) => (
          <div
            key={f.id}
            className={`clock-gif-row ${f.id === sel?.id ? "on" : ""}`}
            onClick={() => setSelId(f.id)}
          >
            <span className="clock-gif-row-thumb">
              {kind === "alarm"
                ? <span className="clock-gif-row-icon"><BellRing size={14} strokeWidth={2.5} aria-hidden /></span>
                : <img src={clockPreviewUrl(kind, f.id)} alt="" loading="lazy" />}
            </span>
            <span className="clock-gif-row-name" title={f.original_name}>
              {f.stored_name}
              {f.stored_name === conf.defaultName && (
                <span className="clock-gif-default" title={t("The clock's default pick")}>
                  <Star size={9} strokeWidth={3} aria-hidden /> {t("default")}
                </span>
              )}
            </span>
            <span className="music-row-size">{formatBytes(f.size_bytes)}</span>
            <a className="icon-btn" href={downloadClockFileUrl(kind, f.id)} download title={t("Download")} onClick={(e) => e.stopPropagation()}>
              <Download size={12} strokeWidth={2.5} />
            </a>
            <button className="icon-btn danger" disabled={busy} title={t("Delete")} onClick={(e) => remove(f, e)}>
              <Trash2 size={12} strokeWidth={2.5} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
