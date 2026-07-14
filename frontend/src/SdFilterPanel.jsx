import React, { useEffect, useRef, useState } from "react";
import { SlidersHorizontal, Star, Languages, X } from "lucide-react";
import { useT } from "./i18n.jsx";
import { FLAG_OPTIONS, langFlagUrl } from "./components.jsx";
import { sdFilterCount, EMPTY_SD_FILTER } from "./api.js";

// "상세 조건" for the SD ZIP — one place for every condition on what lands on the
// card, instead of a separate toggle per idea. Conditions are ANDed; the server
// applies the same set (SdFilter in routers/package.py), and homebrew is exempt
// from all of them because its files are what the firmware's built-in apps boot
// from, not releases with a flag or a rating.
//
// The counts next to each flag come from the library the caller already has, so
// picking a condition that would ship nothing is visible before you pick it.

const SIZE_CAPS = [2, 4, 8, 16, 32];        // MB — the useful cart-size cliffs
const SCORE_FLOORS = [60, 70, 80, 90];

export default function SdFilterPanel({ filter, onChange, flagCounts, disabled, loading }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const count = sdFilterCount(filter);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const set = (patch) => onChange({ ...filter, ...patch });
  const toggleFlag = (code) => {
    const has = filter.flags.includes(code);
    set({ flags: has ? filter.flags.filter((f) => f !== code) : [...filter.flags, code] });
  };

  return (
    <div className={`sdf ${open ? "open" : ""}`} ref={ref}>
      <button
        type="button"
        className={`btn sdf-trigger ${count ? "on" : ""} ${loading ? "is-skel" : ""}`}
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        aria-expanded={open}
        title={t("Pick exactly which ROMs go on the card")}
      >
        <SlidersHorizontal size={14} strokeWidth={2.5} aria-hidden /> {t("Conditions")}
        {count > 0 && <span className="sdf-count">{count}</span>}
      </button>

      {open && (
        <div className="sdf-panel" role="group" aria-label={t("Conditions")}>
          <div className="sdf-head">
            <span>{t("What goes on the card")}</span>
            {count > 0 && (
              <button type="button" className="sdf-reset" onClick={() => onChange(EMPTY_SD_FILTER)}>
                <X size={12} strokeWidth={3} aria-hidden /> {t("Clear")}
              </button>
            )}
          </div>

          {/* Cover flag — multi-select. "none" is a choice of its own: an unflagged
              ROM is a real category, not a missing value. */}
          <div className="sdf-block">
            <div className="sdf-label"><Languages size={12} strokeWidth={2.5} aria-hidden /> {t("Cover flag")}</div>
            <div className="sdf-flags">
              {FLAG_OPTIONS.map((opt) => {
                const code = opt.code || "none";
                const n = flagCounts?.[code] || 0;
                const on = filter.flags.includes(code);
                const url = langFlagUrl(opt.code);
                return (
                  <button
                    key={code}
                    type="button"
                    className={`sdf-flag ${on ? "on" : ""} ${n ? "" : "zero"}`}
                    onClick={() => toggleFlag(code)}
                    aria-pressed={on}
                    title={n ? t(opt.label) : `${t(opt.label)} — ${t("no ROMs")}`}
                  >
                    {url ? <img src={url} alt="" /> : <X size={11} strokeWidth={3} aria-hidden />}
                    <span className="sdf-flag-n">{n}</span>
                  </button>
                );
              })}
            </div>
            <div className="sdf-hint">{t("Nothing checked = every flag ships.")}</div>
          </div>

          {/* Size cap — the one that makes a bloated set fit a card. */}
          <div className="sdf-block">
            <div className="sdf-label">{t("ROM size at most")}</div>
            <div className="sdf-chips">
              {SIZE_CAPS.map((mb) => (
                <button
                  key={mb}
                  type="button"
                  className={`sdf-chip ${filter.maxMb === mb ? "on" : ""}`}
                  onClick={() => set({ maxMb: filter.maxMb === mb ? null : mb })}
                  aria-pressed={filter.maxMb === mb}
                >
                  {mb} MB
                </button>
              ))}
            </div>
          </div>

          {/* Score floor — an unrated ROM never passes one (it has no score). */}
          <div className="sdf-block">
            <div className="sdf-label">{t("IGDB rating at least")}</div>
            <div className="sdf-chips">
              {SCORE_FLOORS.map((sc) => (
                <button
                  key={sc}
                  type="button"
                  className={`sdf-chip ${filter.minScore === sc ? "on" : ""}`}
                  onClick={() => set({ minScore: filter.minScore === sc ? null : sc })}
                  aria-pressed={filter.minScore === sc}
                  title={t("Unrated ROMs don't pass a rating floor")}
                >
                  {sc}+
                </button>
              ))}
            </div>
          </div>

          <div className="sdf-block sdf-switches">
            <label className="sdf-switch">
              <input type="checkbox" checked={filter.favorite}
                onChange={(e) => set({ favorite: e.target.checked })} />
              <Star size={13} strokeWidth={2.5} aria-hidden /> {t("Favorites only")}
            </label>
            <label className="sdf-switch">
              <input type="checkbox" checked={filter.patched}
                onChange={(e) => set({ patched: e.target.checked })} />
              {t("User-patched only")}
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
