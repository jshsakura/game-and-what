import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Gamepad2, Loader2, Upload } from "lucide-react";
import { getSystems, getLibrary, uploadRomset, uploadCdFolder, FOLDER_SYSTEMS, coverUrl } from "../api.js";
import { Dropzone, SystemSelect, RomCard } from "../components.jsx";
import { useT } from "../i18n.jsx";
import { useKoreanMode } from "../config.jsx";

const COVER_POLL_MS = 3000;

export default function RomTab({ onChanged }) {
  const t = useT();
  const koreanMode = useKoreanMode();   // auto-naming is Korean only on a Korean deploy
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

  // Covers are fetched in the background after the upload responds, so the cards
  // land as 'pending'. Poll the library until each one resolves and swap the
  // spinner for the artwork in place — no manual refresh, nothing to guess at.
  const searching = useMemo(
    () => results.filter((r) => r.ok && r.cover_status === "pending").length,
    [results],
  );
  useEffect(() => {
    if (!searching) return undefined;
    const id = setInterval(async () => {
      try {
        const lib = await getLibrary();
        const status = new Map(lib.roms.map((r) => [r.id, r.cover_status]));
        setResults((prev) => prev.map((r) => (
          status.has(r.id) && status.get(r.id) !== r.cover_status
            ? { ...r, cover_status: status.get(r.id) }
            : r
        )));
        onChanged?.();
      } catch { /* transient — the next tick retries */ }
    }, COVER_POLL_MS);
    return () => clearInterval(id);
  }, [searching, onChanged]);

  const current = systems.find((s) => s.key === active);
  const isFolder = FOLDER_SYSTEMS.has(active);   // CD systems → upload a game folder
  const accept = !isFolder && current?.exts?.length ? current.exts.map((e) => "." + e).join(",") : "";
  const okResults = results.filter((r) => r.ok);
  const failed = results.filter((r) => !r.ok);
  const dups = results.filter((r) => r.error === "duplicate");
  const badExt = failed.filter((r) => r.error !== "duplicate");
  const warned = okResults.filter((r) => r.warning);

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
        <Gamepad2 size={13} aria-hidden /> {t(koreanMode
          ? "Pick a platform → upload ROMs for automatic Korean names & covers. Upload a whole folder to use bundled images (.png) as covers; alt dumps ([a1]) are skipped"
          : "Pick a platform → upload ROMs for automatic covers. Upload a whole folder to use bundled images (.png) as covers; alt dumps ([a1]) are skipped")}
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

      {searching > 0 && (
        <div className="muted cover-searching">
          <Loader2 size={13} className="spin" aria-hidden />
          {" "}{t("Searching covers for {n} ROM(s)… they appear here as they arrive", { n: searching })}
        </div>
      )}

      {/* A full-width verdict on what just happened, not a chip. It was borrowing the
          10px `.badge` used for inline tags, which is unreadable at the width of a
          sentence — and this is the one line that tells you which files did NOT land. */}
      {dups.length > 0 && (
        <div className="upload-note warn">
          <AlertTriangle size={16} strokeWidth={2.5} aria-hidden />
          <div>
            <b>{t("Skipped {n} duplicate ROM(s) already in the library", { n: dups.length })}</b>
            <ul>{dups.map((f) => <li key={f.name}>{f.name}</li>)}</ul>
          </div>
        </div>
      )}

      {badExt.length > 0 && (
        <div className="muted">{t("Skipped:")} {badExt.map((f) => f.name).join(", ")} {t("(unsupported extension)")}</div>
      )}

      {warned.length > 0 && (
        <div className="badge failed">
          {warned.map((r) => (<div key={r.id}>⚠ {r.stored_name}: {r.warning}</div>))}
        </div>
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
