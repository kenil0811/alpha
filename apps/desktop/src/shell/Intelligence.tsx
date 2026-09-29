/**
 * Intelligence: what Alpha knows and can do across every module, in one place.
 *  - Second brain: the facts it holds about the person and what each module keeps.
 *  - Skills: reusable abilities that live outside any module; made, run and retired here.
 *  - Automations: every schedule across the modules, switchable in place.
 *  - Connections: which module reads which, switchable in place.
 * Nothing here is a module's own screen; each card links to where the detail lives.
 */
import { useState } from "react";
import { type AppSummary, type CoreClient, isSkillsClient } from "../core/client";
import { Automations } from "./intelligence/Automations";
import { ModuleLinks } from "./intelligence/ModuleLinks";
import { SecondBrain } from "./intelligence/SecondBrain";
import { Skills } from "./intelligence/Skills";

type Tab = "brain" | "skills" | "automations" | "connections";
const TABS: [Tab, string][] = [
  ["brain", "Second brain"],
  ["skills", "Skills"],
  ["automations", "Automations"],
  ["connections", "Connections"],
];

export function Intelligence({
  client,
  modules,
  icons,
  onOpenModule,
  onOpenAbout,
  onOpenAccounts,
}: {
  client: CoreClient;
  modules: AppSummary[];
  icons: Record<string, string>;
  onOpenModule: (appId: string) => void;
  onOpenAbout: () => void;
  onOpenAccounts: () => void;
}) {
  const [tab, setTab] = useState<Tab>("brain");
  return (
    <section className="page" aria-labelledby="intel-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div>
            <h2 id="intel-heading">Intelligence</h2>
            <div className="faint">What Alpha knows and can do across your modules.</div>
          </div>
        </div>
      </div>
      <div className="subtabs" role="tablist" aria-label="Intelligence sections">
        {TABS.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "brain" ? <SecondBrain client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} onOpenAbout={onOpenAbout} /> : null}
      {tab === "skills" ? isSkillsClient(client) ? <Skills client={client} /> : <p className="empty">Skills arrive with a newer runtime.</p> : null}
      {tab === "automations" ? <Automations client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} /> : null}
      {tab === "connections" ? <ModuleLinks client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} onOpenAccounts={onOpenAccounts} /> : null}
    </section>
  );
}
