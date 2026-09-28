/**
 * The avatar window's own entry: it resolves the Core session like the main window, then
 * renders the character with the host's layout commands. Outside Tauri (a browser tab with
 * `#avatar`) it still works against the Vite env session, without the host.
 */
import { useEffect, useState } from "react";
import { HttpCoreClient } from "../core/client";
import { hasTauri, resolveSession } from "../core/session";
import { AvatarWindow, type AvatarHost } from "./AvatarWindow";

/** Whether this webview is the avatar's: the host's window label, or `#avatar` in a browser. */
export async function isAvatarWindow(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (window.location.hash === "#avatar") return true;
  if (!hasTauri()) return false;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    return getCurrentWindow().label === "avatar";
  } catch {
    return false;
  }
}

async function tauriHost(): Promise<AvatarHost | undefined> {
  if (!hasTauri()) return undefined;
  const { invoke } = await import("@tauri-apps/api/core");
  return {
    layout: (expanded) => invoke("avatar_layout", { expanded }),
    showMain: () => invoke("show_main"),
  };
}

export function AvatarBoot() {
  const [state, setState] = useState<{ client: HttpCoreClient; host?: AvatarHost } | { reason: string } | null>(null);
  useEffect(() => {
    document.body.classList.add("avatar-window");
    let cancelled = false;
    (async () => {
      const [resolution, host] = await Promise.all([resolveSession(), tauriHost()]);
      if (cancelled) return;
      if (resolution.kind === "unavailable") {
        setState({ reason: resolution.reason });
        setTimeout(() => !cancelled && setState(null), 5000);
        return;
      }
      setState({ client: new HttpCoreClient(resolution.session), host });
    })();
    return () => {
      cancelled = true;
    };
  }, [state === null]);
  if (!state) return <div className="avatar avatar--waiting" aria-label="Alpha is starting" />;
  if ("reason" in state) return <div className="avatar avatar--waiting" title={state.reason} aria-label="Alpha is starting" />;
  return <AvatarWindow client={state.client} host={state.host} />;
}
