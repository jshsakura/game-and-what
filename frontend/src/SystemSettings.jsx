import React, { useEffect, useRef, useState } from "react";
import { Settings, Eye, EyeOff, X } from "lucide-react";
import { getSystems, setSystemVisibility } from "./api.js";
import { useT } from "./i18n.jsx";
import { SystemIcon } from "./components.jsx";

export default function SystemSettings({ hiddenSystems, onChanged }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [systems, setSystems] = useState([]);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const closeRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    getSystems().then(setSystems).catch((e) => setError(e.message));
    closeRef.current?.focus();
    const escape = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [open]);
  const toggle = async (key) => {
    setBusy(key); setError("");
    try { onChanged(await setSystemVisibility(key, !hiddenSystems.includes(key))); }
    catch (e) { setError(e.message); }
    finally { setBusy(null); }
  };
  return <>
    <button type="button" className="icon-btn header-settings" onClick={() => setOpen(true)} title={t("Settings")} aria-label={t("Settings")} aria-haspopup="dialog" aria-expanded={open}><Settings size={15} aria-hidden="true" /></button>
    {open && <div className="modal-backdrop" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
      <section className="modal system-settings-modal" role="dialog" aria-modal="true" aria-label={t("Platform visibility")}>
        <div className="modal-head"><span>{t("Platform visibility")}</span><button ref={closeRef} className="icon-btn" onClick={() => setOpen(false)} aria-label={t("Close")}><X size={18} /></button></div>
        <div className="modal-body">
          <p className="system-settings-help">{t("Hidden platforms are excluded from the library and SD downloads.")}</p>
          {error && <p role="alert">{error}</p>}
          <div className="system-visibility-grid">
          {systems.slice().sort((a, b) => a.name.localeCompare(b.name)).map((s) => {
            const hidden = hiddenSystems.includes(s.key);
            return <div className="system-visibility-row" key={s.key}>
              <span className="system-visibility-name"><SystemIcon dirname={s.dirname || s.key} size={20} /><span>{s.name}</span></span>
              <button className="btn" role="switch" aria-checked={!hidden} aria-label={s.name} disabled={busy !== null} onClick={() => toggle(s.key)}>
                {hidden ? <EyeOff size={15} /> : <Eye size={15} />} {t(hidden ? "Hide" : "Show")}
              </button>
            </div>;
          })}
          </div>
        </div>
      </section>
    </div>}
  </>;
}
