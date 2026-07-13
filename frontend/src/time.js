// Shared time formatting. The server always emits UTC "YYYY-MM-DD HH:MM:SS" (the
// activity feed, the Extra file list) — parse it as UTC, never as local, or every
// timestamp drifts by the viewer's offset.

export function toDate(s) {
  return s ? new Date(s.replace(" ", "T") + "Z") : null;
}

// Compact relative time: "now", "5m", "3h", "2d", else a date. `t` is the
// translator — only the "now" case needs one.
export function relTime(s, t) {
  const d = toDate(s);
  if (!d || isNaN(d)) return "";
  const sec = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (sec < 45) return t("now");
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h`;
  if (sec < 86400 * 7) return `${Math.round(sec / 86400)}d`;
  return d.toLocaleDateString();
}

// Full timestamp for a tooltip — the exact moment, in the viewer's locale.
export function fullTime(s) {
  const d = toDate(s);
  return d && !isNaN(d) ? d.toLocaleString() : "";
}
