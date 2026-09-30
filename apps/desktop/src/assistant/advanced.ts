/**
 * The + menu's Advanced choices: which model answers, and how much Alpha may do before it asks.
 * Persisted per session (localStorage) so leaving and coming back keeps the choice; a session
 * that never chose starts from Settings -> Access's default.
 */
import { useCallback, useEffect, useState } from "react";

export type AccessMode = "ask" | "approve_for_me" | "full";
export const ACCESS_MODES: AccessMode[] = ["ask", "approve_for_me", "full"];

export const ACCESS_MODE_COPY: Record<AccessMode, { title: string; hint: string }> = {
  ask: { title: "Ask for approval", hint: "Always ask to edit external files and use the internet" },
  approve_for_me: { title: "Approve for me", hint: "Only ask for actions detected as potentially unsafe" },
  full: { title: "Full access", hint: "Unrestricted access to the internet and any file on your computer" },
};

export interface ModelChoice {
  provider: string;
  model?: string;
}

interface Persisted {
  accessMode?: AccessMode;
  model?: ModelChoice;
}

function key(sessionKey: string): string {
  return `alpha.advanced.${sessionKey}`;
}

function load(sessionKey: string): Persisted | null {
  try {
    const raw = localStorage.getItem(key(sessionKey));
    return raw ? (JSON.parse(raw) as Persisted) : null;
  } catch {
    return null;
  }
}

function save(sessionKey: string, value: Persisted): void {
  try {
    localStorage.setItem(key(sessionKey), JSON.stringify(value));
  } catch {
    /* private mode, storage full: the choice just doesn't survive a reload */
  }
}

/** `client` is whatever the surface already has (ActClient or SessionsClient); only
 *  `getSettings` (if the runtime offers it) seeds the Settings -> Access default for a session
 *  that hasn't chosen its own. */
export function useAdvanced(sessionKey: string, client?: unknown) {
  const [accessMode, setAccessModeState] = useState<AccessMode>(() => load(sessionKey)?.accessMode ?? "ask");
  const [model, setModelState] = useState<ModelChoice | null>(() => load(sessionKey)?.model ?? null);

  useEffect(() => {
    const persisted = load(sessionKey);
    if (persisted?.accessMode) {
      setAccessModeState(persisted.accessMode);
      return;
    }
    const getSettings = (client as { getSettings?: () => Promise<{ id: string; value: unknown }[]> } | undefined)?.getSettings;
    if (typeof getSettings !== "function") return;
    let cancelled = false;
    getSettings()
      .then((settings) => {
        const found = settings.find((s) => s.id === "access.mode");
        const value = found?.value;
        if (!cancelled && typeof value === "string" && (ACCESS_MODES as string[]).includes(value)) {
          setAccessModeState(value as AccessMode);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // sessionKey change re-seeds; client identity is stable for a surface's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionKey]);

  const setAccessMode = useCallback(
    (next: AccessMode) => {
      setAccessModeState(next);
      save(sessionKey, { accessMode: next, model: model ?? undefined });
    },
    [sessionKey, model],
  );
  const setModel = useCallback(
    (next: ModelChoice | null) => {
      setModelState(next);
      save(sessionKey, { accessMode, model: next ?? undefined });
    },
    [sessionKey, accessMode],
  );

  return { accessMode, setAccessMode, model, setModel };
}
