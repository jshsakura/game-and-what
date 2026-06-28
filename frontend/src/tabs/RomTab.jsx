import React, { useEffect, useState } from "react";
import { Gamepad2, Upload } from "lucide-react";
import { getSystems, uploadRomset, uploadCdFolder, FOLDER_SYSTEMS, coverUrl } from "../api.js";
import { Dropzone, SystemSelect, RomCard } from "../components.jsx";
import { useT } from "../i18n.jsx";

export default function RomTab({ onChanged }) {
  const t = useT();
  const [systems, setSystems] = useState([]);
  const [active, setActive] = useState(null);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState([]);
  const [extra, setExtra] = useState(null);   // {covers, skippedAlt}
  const [error, setError] = useState("");

  useEffect(() => {
    getSystems()
      .then((s) => { setSystems(s); setActive(s[0]?.key ?? null); })
      .catch((e) => setError(e.message));
  }, []);

  const current = systems.find((s) => s.key === active);
  const isFolder = FOLDER_SYSTEMS.has(active);   // CD systems → upload a game folder
  const accept = !isFolder && current?.exts?.length ? current.exts.map((e) => "." + e).join(",") : "";
  const okResults = results.filter((r) => r.ok);
  const failed = results.filter((r) => !r.ok);
  const dups = results.filter((r) => r.error === "duplicate");
  const badExt = failed.filter((r) => r.error !== "duplicate");

  async function handleFiles(files, onProgress) {
    if (!active || !current) return;
    setBusy(true); setError(""); setExtra(null);
    try {
      const res = isFolder
        ? await uploadCdFolder(active, files, onProgress)
        : await uploadRomset(active, current.exts, files, onProgress);
      setResults(res.results);
      setExtra({ covers: res.covers || 0, skippedAlt: res.skippedAlt || 0 });
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="muted">
        <Gamepad2 size={13} aria-hidden /> {t("Pick a platform → upload ROMs for automatic Korean names & covers. Upload a whole folder to use bundled images (.png) as covers; alt dumps ([a1]) are skipped")}
      </div>

      {systems.length === 0 && !error ? (
        <div className="skel-sysselect">
          <div className="skel-line tag" />
          <div className="skel-line cart" />
          <div className="skel-line name" />
          <div className="skel-line chev" />
        </div>
      ) : (
        <SystemSelect systems={systems} value={active} onChange={setActive} />
      )}

      <Dropzone
        accept={accept}
        multiple
        folder={isFolder}
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {isFolder
              ? t("Drag & drop a {name} game folder (.cue + tracks) or use 'Whole folder'", { name: current?.name ?? "" })
              : t("Drag & drop {name} ROMs here or click", { name: current?.name ?? "" })}
          </span>
        }
        onFiles={handleFiles}
      />

      {error && <div className="badge failed">{error}</div>}

      {results.length > 0 && (
        <div className="muted">
          ✓ {t("{n} saved", { n: okResults.length })}
          {extra?.covers > 0 ? ` · ${t("🖼 {n} bundled covers", { n: extra.covers })}` : ""}
          {extra?.skippedAlt > 0 ? ` · ${t("{n} alt dumps skipped", { n: extra.skippedAlt })}` : ""}
          {failed.length > 0 ? ` · ${t("{n} skipped", { n: failed.length })}` : ""}
        </div>
      )}

      {dups.length > 0 && (
        <div className="badge failed">
          ⚠ {t("Skipped {n} duplicate ROM(s) already in the library", { n: dups.length })}: {dups.map((f) => f.name).join(", ")}
        </div>
      )}

      {badExt.length > 0 && (
        <div className="muted">{t("Skipped:")} {badExt.map((f) => f.name).join(", ")} {t("(unsupported extension)")}</div>
      )}

      {okResults.length > 0 && (
        <div className="grid">
          {okResults.map((r) => (
            <RomCard
              key={r.id}
              rom={r}
              previewSrc={r.cover_status === "ok" ? coverUrl(r.id) : r.screenshot_url}
              onChanged={onChanged}
            />
          ))}
        </div>
      )}
    </div>
  );
}
