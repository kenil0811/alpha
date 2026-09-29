/** Connections between modules: which module reads which, switchable in place. */
import { useEffect, useState } from "react";
import { type AppSummary, type CoreClient, type ModuleConnection, isConnectionsClient } from "../../core/client";

export function ModuleLinks({ client, modules, icons, onOpenModule, onOpenAccounts }: { client: CoreClient; modules: AppSummary[]; icons: Record<string, string>; onOpenModule: (appId: string) => void; onOpenAccounts: () => void }) {
  const [rows, setRows] = useState<{ module: AppSummary; link: ModuleConnection }[] | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!isConnectionsClient(client)) {
      setRows([]);
      return;
    }
    let cancelled = false;
    Promise.all(modules.map((m) => client.connections(m.app_id).then((all) => all.map((link) => ({ module: m, link }))).catch(() => [])))
      .then((groups) => {
        if (!cancelled) setRows(groups.flat());
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, modules, version]);
  return (
    <div className="stack">
      <div className="row">
        <p className="faint" style={{ flex: 1, margin: 0 }}>
          A module reads another only when it asked to and you left it on. Accounts and signed-in sites live on their own page.
        </p>
        <button type="button" className="btn btn--sm" onClick={onOpenAccounts}>
          Accounts and sites
        </button>
      </div>
      {rows === null ? <p className="faint">Loading…</p> : null}
      {rows && !rows.length ? <p className="empty">No module reads another yet. When one asks to, it shows here and in its Settings.</p> : null}
      {rows && rows.length ? (
        <div className="card">
          <table className="table" aria-label="Module connections">
            <thead>
              <tr>
                <th>Module</th>
                <th>Reads</th>
                <th>Why</th>
                <th>On</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ module, link }) => (
                <tr key={`${module.app_id}:${link.module}`}>
                  <td>
                    <button type="button" className="linklike" onClick={() => onOpenModule(module.app_id)}>
                      <span aria-hidden="true">{icons[module.app_id] ?? "▦"}</span> {module.name}
                    </button>
                  </td>
                  <td title={link.views.map((v) => v.id).join(", ")}>
                    {link.name}
                    {link.installed ? "" : " (not installed)"}
                    <span className="faint"> · {link.views.map((v) => v.collection ?? v.id).join(", ")}</span>
                  </td>
                  <td title={link.purpose}>{link.purpose}</td>
                  <td>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={link.enabled}
                        disabled={!link.installed}
                        aria-label={`${module.name} reads ${link.name}`}
                        onChange={(e) => {
                          if (!isConnectionsClient(client)) return;
                          client
                            .setConnection(module.app_id, link.module, e.target.checked)
                            .then(() => setVersion((v) => v + 1))
                            .catch(() => setVersion((v) => v + 1));
                        }}
                      />
                      <span />
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
