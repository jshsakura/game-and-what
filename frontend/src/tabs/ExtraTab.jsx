import React, { useEffect, useState } from "react";
import { FolderPlus, Upload, Download, Trash2 } from "lucide-react";
import { getExtra, uploadExtra, deleteExtra, extraDownloadUrl, formatBytes } from "../api.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";

// Arbitrary passthrough files → SD root verbatim. Pick a target folder (e.g.
// bios/nes) and the files land at <folder>/<name> in the SD ZIP.
export default function ExtraTab({ onChanged }) {
  const toast = useToast();
  const t = useT();
  const [folder, setFolder] = useState("bios/nes");
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);

  const reload = () => {
    setLoading(true);
    return getExtra().then((d) => setFiles(d.files)).catch(() => setFiles([])).finally(() => setLoading(false));
  };
  useEffect(() => { reload(); }, []);

  async function handleFiles(list, onProgress) {
    const arr = Array.from(list);
    if (!arr.length) return;
    const dir = folder.replace(/^\/+|\/+$/g, "");           // trim slashes
    const total = arr.reduce((s, f) => s + f.size, 0) || 1;
    let done = 0;
    for (const f of arr) {
      const rel = (f.webkitRelativePath || f.name).replace(/^\/+/, "");
      const path = dir ? `${dir}/${rel}` : rel;
      try {
        await uploadExtra(f, path, (loaded) => onProgress?.(done + loaded, total));
      } catch (e) {
        toast.error(`${f.name}: ${e.message}`);
      }
      done += f.size;
    }
    await reload();
    onChanged?.();
  }

  async function remove(path) {
    if (!(await toast.confirm(t("Delete the file '/{path}'?", { path }), { confirmText: t("Delete") }))) return;
    try { await deleteExtra(path); await reload(); onChanged?.(); }
    catch (e) { toast.error(e.message); }
  }

  return (
    <div className="stack">
      <div className="muted">
        <FolderPlus size={13} aria-hidden /> {t("Upload any file by")} <b>{t("setting an SD path")}</b>{t("and it goes into the SD ZIP as-is. (FDS:")} <b>bios/nes</b> {t("in")} <b>disksys.rom</b>)
      </div>

      <label className="field-label">{t("Target folder (SD path)")}</label>
      <div className="path-group">
        <span className="path-group-tag"><FolderPlus size={13} strokeWidth={2.5} aria-hidden /> SD</span>
        <span className="path-slash">/</span>
        <input
          className="path-input"
          value={folder}
          spellCheck={false}
          placeholder="bios/nes"
          onChange={(e) => setFolder(e.target.value)}
        />
        <span className="path-trail">/…</span>
      </div>

      <Dropzone
        multiple
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag & drop files or click →")} <b>/{(folder.replace(/^\/+|\/+$/g, "") || "")}/</b> {t("to save")}
          </span>
        }
        onFiles={handleFiles}
      />

      {loading ? (
        <div className="data-list">
          {Array.from({ length: 5 }).map((_, i) => (
            <div className="skel-row" key={i}>
              <div className="skel-line fill" />
              <div className="skel-line w-sm" />
              <div className="skel-line w-icon" />
              <div className="skel-line w-icon" />
            </div>
          ))}
        </div>
      ) : files.length === 0 ? (
        <div className="muted">{t("No files uploaded (not included in SD).")}</div>
      ) : (
        <div className="data-list">
          {files.map((f) => (
            <div className="data-row" key={f.path}>
              <span className="data-name">/{f.path}</span>
              <span className="data-size">{formatBytes(f.size_bytes)}</span>
              <a className="icon-btn" href={extraDownloadUrl(f.path)} download title={t("Download")}>
                <Download size={13} strokeWidth={2.5} />
              </a>
              <button className="icon-btn danger" onClick={() => remove(f.path)} title={t("Delete")}>
                <Trash2 size={13} strokeWidth={2.5} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
