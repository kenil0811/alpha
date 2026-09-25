import type { CoreSession } from "./client";

export type SessionResolution =
  | { kind: "ready"; session: CoreSession; source: "tauri" | "env" }
  | { kind: "unavailable"; reason: string };

interface TauriWindow {
  __TAURI_INTERNALS__?: unknown;
}

export function hasTauri(): boolean {
  return typeof window !== "undefined" && (window as unknown as TauriWindow).__TAURI_INTERNALS__ !== undefined;
}

/** The trusted shell obtains its Core credential only from the native host (typed command) or,
 *  for browser-only development, from explicit Vite env variables. Never from a URL. */
export async function resolveSession(): Promise<SessionResolution> {
  if (hasTauri()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const session = await invoke<CoreSession>("core_session");
      return { kind: "ready", session, source: "tauri" };
    } catch (error) {
      return { kind: "unavailable", reason: `Runtime did not start: ${String(error)}` };
    }
  }
  const baseUrl = import.meta.env.VITE_ALPHA_CORE_URL as string | undefined;
  const token = import.meta.env.VITE_ALPHA_CORE_TOKEN as string | undefined;
  if (baseUrl && token) {
    return { kind: "ready", session: { baseUrl, token }, source: "env" };
  }
  return {
    kind: "unavailable",
    reason: "No runtime session. Start the desktop app (just dev) or set VITE_ALPHA_CORE_URL/TOKEN.",
  };
}
