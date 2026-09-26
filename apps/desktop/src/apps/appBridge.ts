/**
 * The trusted shell's side of an installed App's UI session: derive the grant from the App's
 * declared UI (views and UI-callable actions) and answer bridge requests with Core. The frame
 * never sees the session token, the Core port or anything beyond its grant; Core enforces the
 * views and validates every action input again.
 */
import { BridgeError, type BridgeHandlers, type BridgeSession, type ErrorCode, type RenewOutcome } from "@alpha/ui-bridge";
import { CoreError, type AppDetail, type AppsClient } from "../core/client";

export function appSession(detail: AppDetail, minutes = 30): BridgeSession {
  return {
    session_id: `sess_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`,
    owner: { kind: "app", app_id: detail.app_id, release_id: detail.release_id },
    grant: {
      actions: [...(detail.ui?.actions ?? [])],
      read_views: (detail.ui?.views ?? []).map((v) => v.id),
    },
    expires_at: new Date(Date.now() + minutes * 60_000).toISOString(),
  };
}

function sameGrant(session: BridgeSession, detail: AppDetail): boolean {
  const actions = [...(detail.ui?.actions ?? [])].sort().join("\n");
  const views = (detail.ui?.views ?? []).map((v) => v.id).sort().join("\n");
  return actions === [...session.grant.actions].sort().join("\n") && views === [...session.grant.read_views].sort().join("\n");
}

/**
 * Renew an expired session only while it still describes the App: the same current release and
 * the same declared views and UI actions. Otherwise the session ends (M1 review finding F10).
 * A failure to ask Core is thrown, so the host keeps the session and the person can try again.
 */
export function appSessionRenewer(client: AppsClient, appId: string, minutes = 30): (session: BridgeSession) => Promise<RenewOutcome> {
  return async (session) => {
    const current = await client.appDetail(appId);
    if (current.release_id !== session.owner.release_id) return { revoke: "release_changed" };
    if (!sameGrant(session, current)) return { revoke: "grant_changed" };
    return { expires_at: new Date(Date.now() + minutes * 60_000).toISOString() };
  };
}

const CODE_BY_STATUS: Record<number, ErrorCode> = { 400: "invalid_request", 403: "forbidden", 404: "not_found", 409: "invalid_request", 422: "invalid_request" };

function toBridgeError(error: unknown): BridgeError {
  if (error instanceof CoreError) {
    const code: ErrorCode = CODE_BY_STATUS[error.status] ?? (error.status === 503 ? "unsupported" : "internal");
    return new BridgeError(code, error.message, error.status >= 500 ? "Try again in a moment." : undefined);
  }
  return new BridgeError("internal", "Alpha could not complete the request.");
}

export function appBridgeHandlers(client: AppsClient, appId: string): BridgeHandlers {
  return {
    recordsQuery: async (_session, payload) => {
      const { view, ...query } = payload;
      try {
        return await client.queryView(appId, view, query);
      } catch (error) {
        throw toBridgeError(error);
      }
    },
    actionInvoke: async (_session, payload) => {
      try {
        const run = await client.runAppAction(appId, payload.action_id, payload.input);
        return { operation_id: run.run_id };
      } catch (error) {
        throw toBridgeError(error);
      }
    },
    operationObserve: async (_session, payload) => {
      try {
        return await client.operationOutcome(payload.operation_id);
      } catch (error) {
        throw toBridgeError(error);
      }
    },
  };
}
