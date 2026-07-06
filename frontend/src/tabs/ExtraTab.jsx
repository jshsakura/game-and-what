import React, { useEffect, useState } from "react";
import { FolderPlus, Upload, Download, Trash2, Cpu, ChevronDown } from "lucide-react";
import { getExtra, uploadExtra, deleteExtra, extraDownloadUrl, formatBytes } from "../api.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";
import { useExperimentalMode } from "../config.jsx";
import { BIOS_CATALOG } from "../bios.js";

// Arbitrary passthrough files → SD root verbatim. Pick a target folder (e.g.
// bios/nes) and the files land at <folder>/<name> in the SD ZIP.
export default function ExtraTab({ onChanged }) {
  const toast = useToast();
  const t = useT();
  const experimental = useExperimentalMode();
  // Official deploys don't list fork-only systems' BIOS paths (pcecd, c64, …).
  const biosEntries = BIOS_CATALOG.filter((b) => experimental || !b.experimental);
  const [folder, setFolder] = useState("");
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);

  const reload = () => {
    setLoading(true);
    return getExtra().then((d) => setFiles(d.files)).catch(() => setFiles([])).finally(() => setLoading(false));
  };
  useEffect(() => { reload(); }, []);

  const trimmed = folder.replace(/^\/+|\/+$/g, "");        // trimmed target; empty = SD root
  const isFilePath = /\.[^/.]+$/.test(trimmed.split("/").pop() || "");  // ends in a filename
  const targetDir = isFilePath ? trimmed.replace(/\/?[^/]+$/, "") : trimmed;  // the folder part

  async function handleFiles(list, onProgress) {
    const arr = Array.from(list);
    if (!arr.length) return;
    const total = arr.reduce((s, f) => s + f.size, 0) || 1;
    // A full file path + exactly one dropped file → save it AS that path (rename),
    // so a BIOS dump named differently still lands as e.g. bios/nes/disksys.rom.
    const renameSingle = isFilePath && arr.length === 1;
    let done = 0;
    for (const f of arr) {
      const rel = (f.webkitRelativePath || f.name).replace(/^\/+/, "");
      const path = renameSingle ? trimmed : (targetDir ? `${targetDir}/${rel}` : rel);
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
        <FolderPlus size={13} aria-hidden /> {t("Upload passthrough files — BIOS / system ROMs, configs, anything. Enter a folder (files keep their names) OR a full file path incl. the filename — then one dropped file is saved under that exact name. See the BIOS list in the INFO (정보) tab and paste a path straight in.")}
      </div>

      {/* Required-BIOS path accordion — the cheat sheet for the path input
          below. Collapsed by default to keep the tab compact. */}
      <details className="bios-ref">
        <summary className="bios-ref-head">
          <Cpu size={14} strokeWidth={2.5} aria-hidden /> {t("Required BIOS file paths")}
          <ChevronDown size={14} strokeWidth={2.5} aria-hidden className="bios-ref-chev" />
        </summary>
        <table className="bios-ref-table">
          <thead>
            <tr>
              <th>{t("System")}</th>
              <th>{t("SD path")}</th>
              <th>{t("Size")}</th>
            </tr>
          </thead>
          <tbody>
            {biosEntries.flatMap((b) =>
              b.files.map((f, i) => (
                <tr key={f.sdPath}>
                  {i === 0 && (
                    <td className="bios-ref-sys" rowSpan={b.files.length}>
                      {t(b.label)}
                      {b.tag && <span className="bios-ref-tag">{t(b.tag)}</span>}
                    </td>
                  )}
                  <td className="bios-ref-path">/{f.sdPath}</td>
                  <td className="bios-ref-size">{f.size}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {/* Narrow screens: the 3-column table cramps, so stack paths under
            each system name instead (CSS swaps the two views at 640px). */}
        <div className="bios-ref-stack">
          {biosEntries.map((b) => (
            <div className="bios-ref-group" key={b.key}>
              <div className="bios-ref-group-head">
                {t(b.label)}
                {b.tag && <span className="bios-ref-tag">{t(b.tag)}</span>}
              </div>
              {b.files.map((f) => (
                <div className="bios-ref-row" key={f.sdPath}>
                  <span className="bios-ref-path">/{f.sdPath}</span>
                  <span className="bios-ref-size">{f.size}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </details>

      <label className="field-label">{t("Target SD path")}</label>
      <div className="path-group">
        <span className="path-group-tag"><FolderPlus size={13} strokeWidth={2.5} aria-hidden /> SD</span>
        <span className="path-slash">/</span>
        <input
          className="path-input"
          value={folder}
          spellCheck={false}
          placeholder={t("e.g. bios/nes/disksys.rom (or a folder) — empty = SD root")}
          onChange={(e) => setFolder(e.target.value)}
        />
      </div>
      <div className="muted path-hint">
        {isFilePath
          ? t("Full file path → drop ONE file and it's saved as this exact name (a differently-named dump still works).")
          : t("Folder path → files keep their own names. Add a filename (e.g. …/disksys.rom) to rename a single upload. Empty = SD root.")}
      </div>

      <Dropzone
        multiple
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {t("Drag & drop files or click →")}{" "}
            {isFilePath ? <b>/{trimmed}</b> : targetDir ? <b>/{targetDir}/</b> : <b>{t("the SD root")}</b>}{" "}
            {t("to save")}
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
