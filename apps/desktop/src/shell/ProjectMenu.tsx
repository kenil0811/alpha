/**
 * Rename, Change icon and Delete for a project: the same menu items and dialogs on the rail's
 * project row (right-click or its options button) and on the project page's "…" menu.
 */
import { useEffect, useState } from "react";
import { Pencil, Shapes, Trash2 } from "lucide-react";
import type { Project, SessionsClient } from "../core/client";
import { DropdownMenuItem } from "../ui/DropdownMenu";
import { Dialog, DialogContent } from "../ui/Dialog";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { PROJECT_ICONS } from "./projectIcons";
import "./pages.css";

export type ProjectEdit = "rename" | "icon" | "delete";

export function ProjectMenuItems({ onPick }: { onPick: (edit: ProjectEdit) => void }) {
  return (
    <>
      <DropdownMenuItem onSelect={() => onPick("rename")}>
        <Pencil size={14} strokeWidth={1.75} aria-hidden="true" /> Rename
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onPick("icon")}>
        <Shapes size={14} strokeWidth={1.75} aria-hidden="true" /> Change icon
      </DropdownMenuItem>
      <DropdownMenuItem className="ui-menu__item--danger" onSelect={() => onPick("delete")}>
        <Trash2 size={14} strokeWidth={1.75} aria-hidden="true" /> Delete
      </DropdownMenuItem>
    </>
  );
}

/** One dialog for whichever edit was picked. Core keeps no hard delete for a project: Delete
 *  archives it, and its sub projects go back to the top level with nothing of theirs lost. */
export function ProjectEditDialog({
  client,
  project,
  edit,
  onClose,
  onChanged,
  onDeleted,
}: {
  client: SessionsClient;
  project: Project | null;
  edit: ProjectEdit | null;
  onClose: () => void;
  onChanged?: (project: Project) => void;
  onDeleted?: (projectId: string) => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setName(project?.name ?? "");
    setError(null);
  }, [project, edit]);

  async function run(patch: { name?: string; icon?: string; archived?: boolean }) {
    if (!project) return;
    setBusy(true);
    setError(null);
    try {
      const next = await client.updateProject(project.project_id, patch);
      if (patch.archived) onDeleted?.(project.project_id);
      else onChanged?.(next);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save that.");
    } finally {
      setBusy(false);
    }
  }

  const open = project !== null && edit !== null;
  const title = edit === "rename" ? "Rename project" : edit === "icon" ? "Change icon" : `Delete ${project?.name ?? "project"}?`;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      {open ? (
        <DialogContent title={title}>
          {edit === "rename" ? (
            <form
              className="projedit"
              onSubmit={(e) => {
                e.preventDefault();
                const clean = name.trim();
                if (clean && clean !== project.name) void run({ name: clean });
                else onClose();
              }}
            >
              <Input autoFocus aria-label="Project name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} onFocus={(e) => e.target.select()} />
              <div className="projedit__actions">
                <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" disabled={busy || !name.trim()}>
                  Save
                </Button>
              </div>
            </form>
          ) : edit === "icon" ? (
            <div className="projicons" role="group" aria-label="Project icons">
              {Object.entries(PROJECT_ICONS).map(([key, Icon]) => (
                <button
                  key={key}
                  type="button"
                  className={`projicons__btn${(project.icon ?? "folder") === key ? " projicons__btn--current" : ""}`}
                  aria-label={key.replace(/-/g, " ")}
                  aria-pressed={(project.icon ?? "folder") === key}
                  disabled={busy}
                  onClick={() => void run({ icon: key })}
                >
                  <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
                </button>
              ))}
            </div>
          ) : (
            <>
              <p className="panel__hint">Removes the project from Alpha. Its sub projects move back to the top level.</p>
              <div className="projedit__actions">
                <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
                  Cancel
                </Button>
                <Button variant="destructive" size="sm" onClick={() => void run({ archived: true })} disabled={busy}>
                  Delete
                </Button>
              </div>
            </>
          )}
          {error ? (
            <p className="notice" role="alert">
              {error}
            </p>
          ) : null}
        </DialogContent>
      ) : null}
    </Dialog>
  );
}
