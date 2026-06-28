import React, { useCallback, useEffect, useState } from "react";
import { Database, Upload, Download, Trash2 } from "lucide-react";
import { getData, uploadData, deleteData, dataDownloadUrl } from "../api.js";
import { Dropzone } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useT } from "../i18n.jsx";

function fmtSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

// DATA — temporary/reference holding area. Gray-toned; NOT part of the SD zip.
export default function DataTab({ onChanged }) {
  const toast = useToast();
  const t = useT();
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ext, setExt] = useState("all");   // extension filter

  const extOf = (name) => { const i = name.lastIndexOf("."); return i > 0 ? name.slice(i + 1).toLowerCase() : t("(none)"); };
  const exts = [...new Set(files.map((f) => extOf(f.name)))].sort();
  const shown = ext === "all" ? files : files.filter((f) => extOf(f.name) === ext);

  const reload = useCallback(() => {
    setLoading(true);
    getData()
      .then((d) => setFiles(d.files))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { reload(); }, [reload]);

  async function handleFiles(list, onProgress) {
    setBusy(true); setError("");
    try { await uploadData(list, onProgress); reload(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function remove(name) {
    if (!(await toast.confirm(t("Delete the file '{name}'?", { name }), { confirmText: t("Delete") }))) return;
    setBusy(true);
    try { await deleteData(name); reload(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="stack data-tab">
      <div className="muted">
        <Database size={13} aria-hidden /> {t("Temporary reference storage —")} <b>{t("excluded from the SD ZIP download")}</b>{t(".")}
      </div>

      <Dropzone
        multiple
        label={
          busy
            ? <span className="dz-label"><Upload size={16} aria-hidden /> {t("Uploading…")}</span>
            : <span className="dz-label"><Upload size={16} aria-hidden /> {t("Drag & drop reference files or click (any file)")}</span>
        }
        onFiles={handleFiles}
      />

      {error && <div className="badge failed">{error}</div>}

      {!loading && files.length > 0 && exts.length > 1 && (
        <div className="data-filter">
          <button className={`scope-btn ${ext === "all" ? "on" : ""}`} onClick={() => setExt("all")}>
            {t("All")} ({files.length})
          </button>
          {exts.map((e) => (
            <button key={e} className={`scope-btn ${ext === e ? "on" : ""}`} onClick={() => setExt(e)}>
              .{e} ({files.filter((f) => extOf(f.name) === e).length})
            </button>
          ))}
        </div>
      )}

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
        <div className="muted">{t("No files stored.")}</div>
      ) : (
        <div className="data-list">
          {shown.map((f) => (
            <div className="data-row" key={f.name}>
              <span className="data-name">{f.name}</span>
              <span className="data-size">{fmtSize(f.size)}</span>
              <a className="icon-btn" href={dataDownloadUrl(f.name)} download title={t("Download")}>
                <Download size={13} strokeWidth={2.5} />
              </a>
              <button className="icon-btn danger" disabled={busy} onClick={() => remove(f.name)} title={t("Delete")}>
                <Trash2 size={13} strokeWidth={2.5} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
