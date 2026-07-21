import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Gamepad2, Loader2, Upload } from "lucide-react";
import { getSystems, getLibrary, uploadRomset, uploadCdFolder, uploadCps1, FOLDER_SYSTEMS, coverUrl } from "../api.js";
import { Dropzone, SystemSelect, RomCard } from "../components.jsx";
import { useT } from "../i18n.jsx";
import { useKoreanMode } from "../config.jsx";

const COVER_POLL_MS = 3000;

/* Systems whose layout on the card is a FOLDER PER GAME rather than one file,
 * and which therefore need saying so before the user drops anything. All three
 * fail the same way when the rule is missed — the files land, the entry
 * appears, and the game dies on the device — so none of them may be left to
 * discover it there. */
function UploadGuidance({ systemKey }) {
  const t = useT();
  if (systemKey === "cps1") {
    return (
      <div className="upload-note warn">
        <AlertTriangle size={16} strokeWidth={2.5} aria-hidden />
        <div>
          <b>{t("One arcade game = one folder, and a clone set needs its parent")}</b>
          {t("A CPS-1 game is a MAME romset: a dozen separate chip dumps that belong together. Upload the .zip as downloaded — but drop EVERY zip the game needs at once, because many romsets are MAME \"split sets\" whose own archive leaves out the chips it shares with its parent. Warriors of Fate (Japan) ships 6 of its 10 chips; the other 4 are in the World set's archive. Upload just the one and the entry appears but the game will not run.")}
        </div>
      </div>
    );
  }
  if (systemKey === "pcecd" || systemKey === "segacd") {
    return (
      <div className="upload-note warn">
        <AlertTriangle size={16} strokeWidth={2.5} aria-hidden />
        <div>
          <b>{t("One disc game = one folder — send the whole folder, not the .cue alone")}</b>
          {t("A .cue is only an index: the audio and data live in the .bin/.iso tracks beside it, and the device needs all of them in the game's own folder. Use 'Whole folder' (or drag the folder itself) so the tracks come along. A single .chd holds everything and can be dropped on its own.")}
        </div>
      </div>
    );
  }
  return null;
}

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
  const isCps1 = active === "cps1";              // arcade → romset zips, all at once
  const isFolder = FOLDER_SYSTEMS.has(active);   // CD systems → upload a game folder
  const accept = isCps1 ? ".zip"
    : (!isFolder && current?.exts?.length ? current.exts.map((e) => "." + e).join(",") : "");
  const okResults = results.filter((r) => r.ok);
  const failed = results.filter((r) => !r.ok);
  const dups = results.filter((r) => r.error === "duplicate");
  const badExt = failed.filter((r) => r.error !== "duplicate");
  const warned = okResults.filter((r) => r.warning);

  async function handleFiles(files, onProgress) {
    if (!active || !current) return;
    setBusy(true); setError(""); setExtra(null);
    try {
      const res = isCps1
        ? await uploadCps1(files, onProgress)
        : isFolder
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

      <UploadGuidance systemKey={active} />

      <Dropzone
        accept={accept}
        multiple
        folder={isFolder}
        label={
          <span className="dz-label">
            <Upload size={16} aria-hidden /> {isCps1
              ? t("Drag & drop every .zip this game needs — the clone AND its parent set")
              : isFolder
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
