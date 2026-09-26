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
import { appBridgeHandlers, appSession } from "../apps/appBridge";

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
        onEvent: (e) => {
          if (e.kind === "error") setProblem("The screen asked for something it is not allowed to do.");
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
