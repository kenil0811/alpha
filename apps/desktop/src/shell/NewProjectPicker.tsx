import { useEffect, useState } from "react";
import { FilePlus2, FileUp, Folder } from "lucide-react";
import { isCommonsClient, type CommonsProject } from "../core/client";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/Popover";
import { Input } from "../ui/Input";
import "../ui/StandardDropdown.css";

/** "New project" opens this, Bridge-style: a search bar over Import (always first), a blank
 *  project, and the Commons projects Core lists. Commons shows nothing at all while it's empty. */
export function NewProjectPicker({
  children,
  client,
  onImport,
  onBlank,
  onCommons,
}: {
  /** The rail's New project button. */
  children: React.ReactNode;
  client: unknown;
  onImport?: () => void;
  onBlank: () => void;
  onCommons: (project: CommonsProject) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [commons, setCommons] = useState<CommonsProject[]>([]);

  useEffect(() => {
    if (!open || !isCommonsClient(client)) return;
    let live = true;
    client
      .listCommons()
      .then((all) => live && setCommons(all))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [open, client]);

  const q = query.trim().toLowerCase();
  const matches = (text: string) => !q || text.toLowerCase().includes(q);
  const shownCommons = commons.filter((c) => matches(`${c.name} ${c.summary ?? ""}`));
  const pick = (run: () => void) => () => {
    setOpen(false);
    setQuery("");
    run();
  };
  const actions = [
    ...(onImport ? [{ label: "Import a project…", Icon: FileUp, run: onImport }] : []),
    { label: "Blank project", Icon: FilePlus2, run: onBlank },
  ].filter((a) => matches(a.label));

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent align="start">
        <div className="ui-std-dropdown" aria-label="New project">
          <Input autoFocus placeholder="Search projects" aria-label="Search projects" value={query} onChange={(e) => setQuery(e.target.value)} className="ui-std-dropdown__search" />
          <div className="ui-std-dropdown__list" role="listbox" aria-label="Start from">
            {actions.map(({ label, Icon, run }) => (
              <button key={label} type="button" role="option" aria-selected={false} className="ui-std-dropdown__item ui-std-dropdown__item--icon" onClick={pick(run)}>
                <Icon size={14} strokeWidth={1.75} aria-hidden="true" />
                <span className="truncate">{label}</span>
              </button>
            ))}
            {shownCommons.length ? (
              <>
                <div className="ui-std-dropdown__section">Commons</div>
                {shownCommons.map((c) => (
                  <button key={c.id} type="button" role="option" aria-selected={false} className="ui-std-dropdown__item ui-std-dropdown__item--icon" title={c.summary ?? c.name} onClick={pick(() => onCommons(c))}>
                    <Folder size={14} strokeWidth={1.75} aria-hidden="true" />
                    <span className="truncate">{c.name}</span>
                  </button>
                ))}
              </>
            ) : null}
            {!actions.length && !shownCommons.length ? <p className="ui-std-dropdown__empty">No matches</p> : null}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
