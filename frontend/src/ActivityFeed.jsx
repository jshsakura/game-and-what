import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bell, BellOff, X, Upload, Pencil, Trash2, Languages, HardDriveDownload, XCircle, Gamepad2, RotateCcw, Loader } from "lucide-react";
import { getEvents, restoreEvent } from "./api.js";
import { SystemIcon } from "./components.jsx";
import { useT } from "./i18n.jsx";
import { useToast } from "./toast.jsx";

const SEEN_KEY = "gnw_events_seen";   // newest created_at the user has already seen
const POLL_MS = 20000;                // background refresh cadence for the badge
const FEED_LIMIT = 50;

// Server timestamps are UTC "YYYY-MM-DD HH:MM:SS" — parse as UTC, not local.
function toDate(s) {
  return s ? new Date(s.replace(" ", "T") + "Z") : null;
}

// Compact relative time: "now", "5m", "3h", "2d", else a date.
function relTime(s, t) {
  const d = toDate(s);
  if (!d || isNaN(d)) return "";
  const sec = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (sec < 45) return t("now");
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h`;
  if (sec < 86400 * 7) return `${Math.round(sec / 86400)}d`;
  return d.toLocaleDateString();
}

// PICO-8 compat status → translatable English source word (ko.js renders
// "won't run" → 구동불가, etc.).
const COMPAT_KEY = {
  good: "good", slow: "slow", partial: "partial", broken: "won't run", untested: "untested",
};

// One event → { Icon, cls, text } for the row. cls tints broken/delete rows.
function present(ev, t) {
  const name = ev.rom_name || "ROM";
  const m = ev.meta || {};
  switch (ev.event_type) {
    case "rom_upload":
      return { Icon: Upload, cls: "up", text: t("Added {name}", { name }) };
    case "rom_rename":
      return { Icon: Pencil, cls: "", text: t("Renamed → {name}", { name }) };
    case "rom_delete":
      return { Icon: Trash2, cls: "del", text: t("Deleted {name}", { name }) };
    case "rom_restore":
      return { Icon: RotateCcw, cls: "up", text: t("Restored {name}", { name }) };
    case "pico8_compat": {
      const word = t(COMPAT_KEY[m.status] || "untested");
      const broken = m.status === "broken";
      return {
        Icon: broken ? XCircle : Gamepad2, cls: broken ? "del" : "",
        text: t("PICO-8 {name}: {status}", { name, status: word }),
      };
    }
    case "lang_patch":
      return {
        Icon: Languages, cls: "",
        text: m.patched ? t("Korean patch on: {name}", { name }) : t("Korean patch off: {name}", { name }),
      };
    case "sd_exclude":
      return {
        Icon: HardDriveDownload, cls: m.exclude ? "del" : "",
        text: m.exclude ? t("Excluded from SD: {name}", { name }) : t("Back on SD: {name}", { name }),
      };
    default:
      return { Icon: Bell, cls: "", text: name };
  }
}

// Bell button (far right of the top bar) + right-side activity drawer. Self-contained:
// polls for new events and tracks an unread badge via a localStorage watermark.
// `pulse` (App's reloadKey) forces an immediate refetch right after the user's
// own actions so the feed feels live.
export default function ActivityFeed({ pulse, onChanged }) {
  const t = useT();
  const toast = useToast();
  const [events, setEvents] = useState([]);
  const [loaded, setLoaded] = useState(false);   // false until the first fetch lands
  const [open, setOpen] = useState(false);
  const [restoringId, setRestoringId] = useState(null);
  const [seen, setSeen] = useState(() => {
    try { return localStorage.getItem(SEEN_KEY) || ""; } catch { return ""; }
  });

  const refresh = useCallback(() => {
    getEvents(FEED_LIMIT)
      .then((r) => setEvents(r.events || []))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  // Undo a deletion: pull the ROM back out of _trash, then refresh feed + library.
  const doRestore = useCallback(async (ev) => {
    if (restoringId) return;
    setRestoringId(ev.id);
    try {
      await restoreEvent(ev.id);
      toast.success(t("Restored {name}", { name: ev.rom_name || "ROM" }));
      refresh();
      onChanged?.();
    } catch (e) {
      toast.error(e.message || t("Restore failed"));
    } finally {
      setRestoringId(null);
    }
  }, [restoringId, refresh, onChanged, toast, t]);

  // Initial + on every pulse (user action) + background poll.
  useEffect(() => { refresh(); }, [refresh, pulse]);
  useEffect(() => {
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const newest = events[0]?.created_at || "";
  // String compare is valid: all timestamps share the UTC "YYYY-MM-DD HH:MM:SS" form.
  const unread = useMemo(
    () => (seen ? events.filter((e) => e.created_at > seen).length : events.length),
    [events, seen]
  );

  // Opening the drawer clears the badge (watermark = newest event seen).
  const markSeen = useCallback(() => {
    if (!newest) return;
    setSeen(newest);
    try { localStorage.setItem(SEEN_KEY, newest); } catch { /* ignore */ }
  }, [newest]);

  const toggle = () => {
    setOpen((o) => {
      const next = !o;
      if (next) markSeen();
      return next;
    });
  };
  const close = () => setOpen(false);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const badge = unread > 9 ? "9+" : String(unread);

  return (
    <>
      <button
        type="button"
        className="icon-btn actfeed-bell"
        onClick={toggle}
        title={t("Activity")}
        aria-label={t("Activity")}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Bell size={14} strokeWidth={2.5} aria-hidden />
        {unread > 0 && <span className="actfeed-badge" aria-label={t("{n} new", { n: unread })}>{badge}</span>}
      </button>

      {open && (
        <>
          <div className="actfeed-backdrop" onClick={close} aria-hidden />
          <aside className="actfeed-panel" role="dialog" aria-label={t("Activity")}>
            <header className="actfeed-head">
              <span className="actfeed-title"><Bell size={14} strokeWidth={2.5} aria-hidden /> {t("Activity")}</span>
              <button className="icon-btn" onClick={close} aria-label={t("Close")}>
                <X size={14} strokeWidth={2.5} aria-hidden />
              </button>
            </header>
            {!loaded ? (
              <ul className="actfeed-list" aria-hidden>
                {Array.from({ length: 6 }).map((_, i) => (
                  <li className="actfeed-item actfeed-skel" key={i}>
                    <span className="skel-ico" />
                    <span className="skel-line fill" />
                    <span className="skel-line w-sm" />
                  </li>
                ))}
              </ul>
            ) : events.length === 0 ? (
              <div className="actfeed-empty">
                <BellOff size={26} strokeWidth={1.75} aria-hidden />
                <span>{t("No notifications")}</span>
              </div>
            ) : (
              <ul className="actfeed-list">
                {events.map((ev) => {
                  const { Icon, cls, text } = present(ev, t);
                  const del = ev.event_type === "rom_delete" ? (ev.meta || {}) : null;
                  const busy = restoringId === ev.id;
                  return (
                    <li key={ev.id} className={`actfeed-item ${cls}`}>
                      <span className="actfeed-ico"><Icon size={13} strokeWidth={2.5} aria-hidden /></span>
                      <span className="actfeed-text" title={ev.rom_name || ""}>{text}</span>
                      <span className="actfeed-meta">
                        {del?.restorable && (
                          <button type="button" className="actfeed-restore" disabled={busy}
                            onClick={() => doRestore(ev)} title={t("Restore from trash")}>
                            {busy
                              ? <Loader size={11} strokeWidth={2.5} className="spin" aria-hidden />
                              : <RotateCcw size={11} strokeWidth={2.5} aria-hidden />}
                            {t("Restore")}
                          </button>
                        )}
                        {del?.restored && <span className="actfeed-tag">{t("Restored")}</span>}
                        {del?.expired && <span className="actfeed-tag muted">{t("Expired")}</span>}
                        {ev.system_key && <SystemIcon dirname={ev.system_key} size={13} />}
                        <time className="actfeed-time">{relTime(ev.created_at, t)}</time>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>
        </>
      )}
    </>
  );
}
