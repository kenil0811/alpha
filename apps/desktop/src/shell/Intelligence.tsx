import type { LucideIcon } from "lucide-react";
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
import { Connections } from "./Info";
import { Automations } from "./intelligence/Automations";
import { ModuleLinks } from "./intelligence/ModuleLinks";
import { SecondBrain } from "./intelligence/SecondBrain";
import { Skills } from "./intelligence/Skills";
import { InfoTip } from "../ui/InfoTip";
import "../modules/module.css";

type Tab = "brain" | "skills" | "automations" | "connections";
const TABS: [Tab, string, string][] = [
  ["brain", "Second brain", "Every module and every fact Alpha holds, and how they connect."],
  ["skills", "Skills", "A reusable ability outside any module: on its own, or when a sentence calls for it."],
  ["automations", "Automations", "Every schedule across your modules, switchable in place."],
  ["connections", "Connections", "A module reads another only when it asked to and you left it on."],
];
const isTab = (t?: string): t is Tab => t === "brain" || t === "skills" || t === "automations" || t === "connections";

export function Intelligence({
  client,
  modules,
  icons,
  initialTab,
  onOpenModule,
  onOpenAbout,
}: {
  client: CoreClient;
  modules: AppSummary[];
  icons: Record<string, LucideIcon>;
  initialTab?: string;
  onOpenModule: (appId: string) => void;
  onOpenAbout: () => void;
}) {
  const [tab, setTab] = useState<Tab>(isTab(initialTab) ? initialTab : "brain");
  return (
    <section className="page" aria-labelledby="intel-heading">
      <div className="modhead">
        <div className="modhead__title">
          <h2 id="intel-heading">
            Intelligence
            <InfoTip content="What Alpha knows and can do across your modules." label="About Intelligence" />
          </h2>
        </div>
      </div>
      <div className="subtabs" role="tablist" aria-label="Intelligence sections">
        {TABS.map(([id, label, hint]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} title={hint} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "brain" ? <SecondBrain client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} onOpenAbout={onOpenAbout} /> : null}
      {tab === "skills" ? isSkillsClient(client) ? <Skills client={client} /> : <p className="empty">Skills arrive with a newer runtime.</p> : null}
      {tab === "automations" ? <Automations client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} /> : null}
      {tab === "connections" ? (
        <div className="stack">
          <Connections client={client} embedded />
          <ModuleLinks client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} />
        </div>
      ) : null}
    </section>
  );
}
