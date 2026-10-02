import type { LucideIcon } from "lucide-react";
import { ModuleIcon } from "../../ui/ModuleIcon";
/** Connections between modules: which module reads which, switchable in place. */
import { useEffect, useState } from "react";
import { type AppSummary, type CoreClient, type ModuleConnection, isConnectionsClient } from "../../core/client";
import "../../modules/views/views.css";

export function ModuleLinks({ client, modules, icons, onOpenModule }: { client: CoreClient; modules: AppSummary[]; icons: Record<string, LucideIcon>; onOpenModule: (appId: string) => void }) {
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
      {rows === null ? <p className="faint">Loading…</p> : null}
      {rows && !rows.length ? <p className="empty">No project reads another yet.</p> : null}
      {rows && rows.length ? (
        <div className="card">
          <div className="tablewrap">
          <table className="table dv-table" aria-label="Project connections">
            <thead>
              <tr>
                <th>Project</th>
                <th>Reads</th>
                <th>Why</th>
                <th>On</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ module, link }) => (
                <tr key={`${module.app_id}:${link.module}`} className="dv-row">
                  <td>
                    <button type="button" className="linklike" onClick={() => onOpenModule(module.app_id)}>
                      <ModuleIcon icon={icons[module.app_id]} /> {module.name}
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
        </div>
      ) : null}
    </div>
  );
}
