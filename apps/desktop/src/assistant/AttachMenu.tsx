/**
 * The composer's "+" button: add files, images, a folder or an audio file as context for the
 * next message, and the removable chips that show what is queued. Shared by the Chief of Staff
 * panel's composer (AssistantPanel.tsx) and the floating avatar's (AvatarWindow.tsx).
 */
import { useCallback, useState } from "react";
import { File, FileAudio, FolderClosed, Image as ImageIcon, Plus, X } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, IconButton } from "../ui";
import { type PendingAttachment, pickAudioFile, pickFilesOrImages, pickFolder, sizeLabel, unclaimed } from "./attachments";
import "./attach.css";

/** Queued attachments for one composer: add (via a pick, a drop, or a paste), remove, clear on
 *  send. Files claimed by a registered handler (see `registerAttachmentHandler`) never appear. */
export function useAttachments() {
  const [items, setItems] = useState<PendingAttachment[]>([]);
  const add = useCallback((incoming: PendingAttachment[]) => {
    setItems((cur) => [...cur, ...unclaimed(incoming, cur.length)]);
  }, []);
  const remove = useCallback((id: string) => setItems((cur) => cur.filter((a) => a.id !== id)), []);
  const clear = useCallback(() => setItems([]), []);
  return { items, add, remove, clear };
}

export function AttachMenu({ onAdd, small = false }: { onAdd: (items: PendingAttachment[]) => void; small?: boolean }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <IconButton aria-label="Add files, folders, images or audio" size={small ? "sm" : "default"}>
          <Plus size={small ? 14 : 16} aria-hidden="true" />
        </IconButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onSelect={() => void pickFilesOrImages().then(onAdd)}>
          <ImageIcon size={14} aria-hidden="true" /> Add files or images
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void pickFolder().then(onAdd)}>
          <FolderClosed size={14} aria-hidden="true" /> Add a folder
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void pickAudioFile().then(onAdd)}>
          <FileAudio size={14} aria-hidden="true" /> Add audio file
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function iconFor(kind: PendingAttachment["kind"]) {
  if (kind === "image") return <ImageIcon size={14} aria-hidden="true" />;
  if (kind === "audio") return <FileAudio size={14} aria-hidden="true" />;
  if (kind === "folder") return <FolderClosed size={14} aria-hidden="true" />;
  return <File size={14} aria-hidden="true" />;
}

export function AttachmentChips({ items, onRemove }: { items: PendingAttachment[]; onRemove: (id: string) => void }) {
  if (!items.length) return null;
  return (
    <div className="attach-chips" aria-label="Attached">
      {items.map((a) => (
        <span key={a.id} className="attach-chip" title={a.name}>
          {a.previewUrl ? (
            <img src={a.previewUrl} alt="" className="attach-chip__thumb" />
          ) : (
            <span className="attach-chip__icon">{iconFor(a.kind)}</span>
          )}
          <span className="attach-chip__name">{a.name}</span>
          {typeof a.size === "number" ? <span className="attach-chip__size">{sizeLabel(a.size)}</span> : null}
          <button type="button" className="attach-chip__remove" aria-label={`Remove ${a.name}`} onClick={() => onRemove(a.id)}>
            <X size={11} aria-hidden="true" />
          </button>
        </span>
      ))}
    </div>
  );
}
