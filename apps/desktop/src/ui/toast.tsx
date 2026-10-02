/** A minimal toast stack: provider + useToast, one status region, auto-dismiss. */
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import "./toast.css";

interface Toast {
  id: number;
  message: string;
  action?: { label: string; onClick: () => void };
}

interface ToastApi {
  show: (message: string, action?: Toast["action"]) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const show = useCallback((message: string, action?: Toast["action"]) => {
    const id = nextId.current++;
    // The same message again replaces the one showing (and restarts its timer) - never a stack.
    setToasts((current) => [...current.filter((t) => t.message !== message), { id, message, action }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      {toasts.length > 0 ? (
        <div className="toast__region" role="status" aria-live="polite">
          {toasts.map((t) => (
            <div key={t.id} className="toast">
              <span className="toast__message">{t.message}</span>
              {t.action ? (
                <button type="button" className="toast__action" onClick={t.action.onClick}>
                  {t.action.label}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </ToastContext.Provider>
  );
}
