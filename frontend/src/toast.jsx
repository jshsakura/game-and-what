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
              <span>{toast.message}</span>
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
