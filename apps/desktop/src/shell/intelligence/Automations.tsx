import type { LucideIcon } from "lucide-react";
import { ModuleIcon } from "../../ui/ModuleIcon";
/** Automations: every schedule across the modules, switchable in place. */
import { useEffect, useState } from "react";
import type { AppSummary, CoreClient, SchedulesClient, ScheduleStatus } from "../../core/client";
import "../../modules/views/views.css";

export function Automations({ client: core, modules, icons, onOpenModule }: { client: CoreClient; modules: AppSummary[]; icons: Record<string, LucideIcon>; onOpenModule: (appId: string) => void }) {
  const client = core as CoreClient & SchedulesClient;
  const [rows, setRows] = useState<{ module: AppSummary; schedule: ScheduleStatus }[] | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!client.listSchedules) {
      setRows([]);
      return;
    }
    let cancelled = false;
    Promise.all(modules.map((m) => client.listSchedules!(m.app_id).then((all) => all.map((schedule) => ({ module: m, schedule }))).catch(() => [])))
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
  if (rows === null) return <p className="faint">Loading…</p>;
  if (!rows.length) return <p className="empty">Nothing runs on its own yet.</p>;
  return (
    <div className="card">
      <div className="tablewrap">
      <table className="table dv-table" aria-label="Automations">
        <thead>
          <tr>
            <th>Module</th>
            <th>What</th>
            <th>When</th>
            <th>Last ran</th>
            <th>On</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ module, schedule }) => (
            <tr key={`${module.app_id}:${schedule.id}`} className="dv-row">
              <td>
                <button type="button" className="linklike" onClick={() => onOpenModule(module.app_id)}>
                  <ModuleIcon icon={icons[module.app_id]} /> {module.name}
                </button>
              </td>
              <td title={schedule.title}>{schedule.title}</td>
              <td>{schedule.when}</td>
              <td className={schedule.last_error ? "notice" : undefined} title={schedule.last_error ?? undefined}>
                {schedule.last_error ? "Failed last time" : schedule.last_run_at ? new Date(schedule.last_run_at).toLocaleString() : "Not yet"}
              </td>
              <td>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={schedule.enabled}
                    aria-label={`${schedule.title} on`}
                    onChange={(e) => {
                      if (!client.setSchedule) return;
                      client
                        .setSchedule(module.app_id, schedule.id, e.target.checked)
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
  );
}

