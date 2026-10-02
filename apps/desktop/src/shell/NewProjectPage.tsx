import { FileUp, FolderPlus } from "lucide-react";
import { useRef, useState } from "react";
import { isAlphaModuleFile } from "../modules/alphaModuleAttachment";
import { Button } from "../ui/Button";
import "./pages.css";
import "../modules/module.css";

/**
 * The blank project New project opens: an editable name, one "Describe your project" box and
 * Import. What the person types goes to the Chief of Staff as their first message (the project
 * is made then), and the page moves on to the project, where Alpha's questions and options show.
 */
export function NewProjectPage({
  title,
  onTitleChange,
  onStart,
  onImport,
}: {
  title: string;
  onTitleChange: (title: string) => void;
  /** The first message, handed to the chat panel and sent there. */
  onStart: (text: string) => void;
  /** Absent when the runtime can't install a project file. */
  onImport?: (file: File) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function save() {
    setEditing(false);
    const value = draft.trim();
    if (value) onTitleChange(value);
    else setDraft(title);
  }

  function start() {
    const clean = text.trim();
    if (clean) onStart(clean);
  }

  return (
    <section className="page" aria-labelledby="new-project-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div className="modhead__ico" aria-hidden="true">
            <FolderPlus size={18} strokeWidth={1.75} />
          </div>
          {editing ? (
            <input
              autoFocus
              aria-label="Project name"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={save}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
                if (e.key === "Escape") {
                  setDraft(title);
                  setEditing(false);
                }
              }}
            />
          ) : (
            <h2
              id="new-project-heading"
              className="editable"
              onClick={() => {
                setDraft(title);
                setEditing(true);
              }}
            >
              {title}
            </h2>
          )}
        </div>
      </div>

      <form
        className="newproject"
        onSubmit={(e) => {
          e.preventDefault();
          start();
        }}
      >
        <textarea
          autoFocus
          className="newproject__input"
          aria-label="Describe your project"
          placeholder="Describe your project"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              start();
            }
          }}
        />
        <div className="row newproject__actions">
          {onImport ? (
            <>
              <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
                <FileUp size={14} strokeWidth={1.75} aria-hidden="true" /> Import a project…
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept=".alphamodule"
                hidden
                aria-label="Project file"
                onChange={(e) => {
                  const file = Array.from(e.target.files ?? []).find(isAlphaModuleFile);
                  if (file) onImport(file);
                  e.target.value = "";
                }}
              />
            </>
          ) : null}
          <span className="rail__spacer" />
          <Button type="submit" size="sm" disabled={!text.trim()}>
            Start
          </Button>
        </div>
      </form>
    </section>
  );
}
