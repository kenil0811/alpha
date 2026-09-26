/**
 * An App's own screen: its sealed static UI, served by the native host from the App's current
 * Version at `alpha-ui://<app_id>/<version_id>/index.html` (its own origin and strict CSP), in a
 * frame sandboxed to scripts only. The frame reaches Core only through this session's bridge:
 * the views and UI actions the App declared, answered by the shell with its own credential.
 */
import { useEffect, useRef, useState } from "react";
import { BridgeHost } from "@alpha/ui-bridge";
import type { AppDetail, AppsClient } from "../core/client";
import { hasTauri } from "../core/session";
import { appBridgeHandlers, appSession, appSessionRenewer } from "../apps/appBridge";

/** What the shell adds around an App's own screen when a request fails. Ordinary failures (a
 *  refused input, a failed save) are the screen's to show; the shell speaks only about what the
 *  screen cannot explain: a blocked request or an App that cannot run at the moment. */
export function screenProblem(detail: Record<string, unknown> | undefined): string | null {
  const code = typeof detail?.code === "string" ? detail.code : null;
  if (code === "forbidden") return "Alpha blocked a request from this screen that it is not allowed to make.";
  if (code === "unsupported") return "This App can't run right now: its runtime on this Mac needs attention. Your saved data is safe.";
  return null;
}

/** When the shell ends a screen's session because the workflow changed underneath it. */
export function revokedProblem(detail: Record<string, unknown> | undefined): string | null {
  const reason = typeof detail?.reason === "string" ? detail.reason : null;
  if (reason === "release_changed" || reason === "grant_changed") {
    return "This workflow was updated while its screen was open. Reopen it to continue; what you typed is still on the screen.";
  }
  return null;
}

export function screenUrl(detail: AppDetail): string {
  return `alpha-ui://${detail.app_id}/${detail.version_id}/index.html`;
}

export function GeneratedScreen({ client, detail }: { client: AppsClient; detail: AppDetail }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let host: BridgeHost | null = null;
    const onMessage = (event: MessageEvent) => {
      const data = event.data as { type?: string; protocol_version?: string } | null;
      const target = frame.current?.contentWindow;
      if (!target || event.source !== target || data?.type !== "bridge.hello" || data.protocol_version !== "0.2") return;
      host?.revoke("reconnected");
      host = new BridgeHost({
        session: appSession(detail),
        handlers: appBridgeHandlers(client, detail.app_id),
        renew: appSessionRenewer(client, detail.app_id),
        onEvent: (e) => {
          const problem = e.kind === "error" ? screenProblem(e.detail) : e.kind === "revoked" ? revokedProblem(e.detail) : null;
          if (problem) setProblem(problem);
        },
      });
      host.attachToWindow(target);
    };
    window.addEventListener("message", onMessage);
    return () => {
      window.removeEventListener("message", onMessage);
      host?.revoke("closed");
    };
  }, [client, detail]);

  if (!hasTauri()) {
    return (
      <p className="notice">
        This App's screen opens in the Alpha window on your Mac. In a plain browser only its actions are available below.
      </p>
    );
  }
  return (
    <>
      {problem ? <p className="notice">{problem}</p> : null}
      <iframe
        ref={frame}
        className="app-screen"
        title={`${detail.name} screen`}
        sandbox="allow-scripts"
        src={screenUrl(detail)}
      />
    </>
  );
}
