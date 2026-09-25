import type { CoreSession } from "./client";

export type SessionResolution =
  | { kind: "ready"; session: CoreSession; source: "tauri" | "env" }
  | { kind: "unavailable"; reason: string };

interface TauriWindow {
  __TAURI_INTERNALS__?: unknown;
}

/** Validate the host's answer instead of trusting its shape: a wrong field name must produce a
 *  precise runtime error, not an unreachable fetch. */
export function parseSession(value: unknown): CoreSession {
  const candidate = value as Partial<CoreSession> | null;
  if (
    !candidate ||
    typeof candidate.baseUrl !== "string" ||
    !/^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(candidate.baseUrl) ||
    typeof candidate.token !== "string" ||
    candidate.token.length < 32
  ) {
    throw new Error(`host returned an invalid core session: ${JSON.stringify(value)}`);
  }
  return { baseUrl: candidate.baseUrl, token: candidate.token };
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
      const session = parseSession(await invoke<unknown>("core_session"));
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
