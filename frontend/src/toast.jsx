import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { CheckCircle2, XCircle, Info, AlertTriangle } from "lucide-react";
import { useT } from "./i18n.jsx";

// Pretty in-app notifications + a promise-based confirm dialog.
// Replaces window.alert / window.confirm everywhere.
const ToastCtx = createContext(null);
export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

const ICONS = { success: CheckCircle2, error: XCircle, info: Info, warn: AlertTriangle };
const TTL = { success: 3500, info: 3500, warn: 5000, error: 6000 };

// Toast text is translated HERE rather than at each call site, because most error
// toasts carry `err.message`, and that message came from the API — where the source
// language is English, exactly like every t() key in the app. Translating at the one
// place they all pass through is what lets a 400 from the backend read Korean for a
// Korean user and German for a German one, without threading t() through api.js.
//
// Calling t() on an already-translated string is harmless: it misses the dictionary
// and comes back unchanged.
//
// The ": " rule is for messages that carry a value — a filename, an ffmpeg error. The
// whole string can never be a key (the value differs every time), so the part before
// the colon is looked up and the value is pasted back on. Backend messages are written
// to put the variable last for this reason (see routers/*.py).
function translateMessage(t, message) {
  if (typeof message !== "string" || !message) return message;
  const direct = t(message);
  if (direct !== message) return direct;
  const at = message.indexOf(": ");
  if (at > 0) {
    const stem = message.slice(0, at);
    const translated = t(stem);
    if (translated !== stem) return `${translated}: ${message.slice(at + 2)}`;
  }
  return message;
}

let seq = 0;

export function ToastProvider({ children }) {
  const t = useT();
  const [toasts, setToasts] = useState([]);
  const [confirmState, setConfirmState] = useState(null);

  const remove = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((message, type) => {
    const id = ++seq;
    setToasts((list) => [...list, { id, message, type }]);
    window.setTimeout(() => remove(id), TTL[type] ?? 3500);
    return id;
  }, [remove]);

  const api = useMemo(() => ({
    success: (m) => push(m, "success"),
    error: (m) => push(m, "error"),
    info: (m) => push(m, "info"),
    warn: (m) => push(m, "warn"),
    // confirm(message, { detail, confirmText, cancelText, danger }) → Promise<bool>
    confirm: (message, opts = {}) =>
      new Promise((resolve) => setConfirmState({ message, opts, resolve })),
  }), [push]);

  function settle(result) {
    confirmState?.resolve(result);
    setConfirmState(null);
  }

  const c = confirmState?.opts ?? {};

  return (
    <ToastCtx.Provider value={api}>
      {children}

      <div className="toast-stack" aria-live="polite">
        {toasts.map((toast) => {
          const Icon = ICONS[toast.type] ?? Info;
          return (
            <div key={toast.id} className={`toast toast-${toast.type}`} role="status" onClick={() => remove(toast.id)}>
              <Icon size={15} strokeWidth={2.5} aria-hidden />
              <span>{translateMessage(t, toast.message)}</span>
            </div>
          );
        })}
      </div>

      {confirmState && (
        <div className="modal-backdrop" onClick={() => settle(false)}>
          <div className="confirm" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-msg">{confirmState.message}</div>
            {c.detail && <div className="confirm-detail">{c.detail}</div>}
            <div className="confirm-actions">
              <button className="btn ghost" onClick={() => settle(false)}>{c.cancelText ?? t("Cancel")}</button>
              <button className={`btn ${c.danger ? "danger" : ""}`} onClick={() => settle(true)}>
                {c.confirmText ?? t("OK")}
              </button>
            </div>
          </div>
        </div>
      )}
    </ToastCtx.Provider>
  );
}
