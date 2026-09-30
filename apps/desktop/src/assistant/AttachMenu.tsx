/**
 * The composer's "+" button: add files, images, a folder or an audio file as context for the
 * next message, and the removable chips that show what is queued. Shared by the Chief of Staff
 * panel's composer (AssistantPanel.tsx) and the floating avatar's (AvatarWindow.tsx).
 */
import { useCallback, useEffect, useState } from "react";
import { Check, File, FileAudio, FolderClosed, Image as ImageIcon, Plus, Settings2, X } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
  IconButton,
} from "../ui";
import { isModelAccountsClient, type ModelProviderAccount } from "../core/client";
import { ACCESS_MODE_COPY, ACCESS_MODES, useAdvanced, type AccessMode, type ModelChoice } from "./advanced";
import { type PendingAttachment, pickAudioFile, pickFilesOrImages, pickFolder, sizeLabel, unclaimed } from "./attachments";
import "./attach.css";

export type { AccessMode, ModelChoice };
export { useAdvanced };

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

/** A Settings -> Models account, offered as the Advanced submenu's model choice. Only the
 *  account-level methods are used, and only when the runtime actually offers them. */
interface ModelAccountsLike {
  listModelAccounts(): Promise<ModelProviderAccount[]>;
}

function advancedLabel(advanced: AdvancedControls): string {
  const parts: string[] = [];
  if (advanced.accessMode !== "ask") parts.push(ACCESS_MODE_COPY[advanced.accessMode].title);
  if (advanced.model) parts.push(advanced.model.provider);
  return parts.join(" · ");
}

export interface AdvancedControls {
  accessMode: AccessMode;
  onAccessModeChange: (mode: AccessMode) => void;
  model: ModelChoice | null;
  onModelChange: (model: ModelChoice | null) => void;
  /** Whatever the surface already has; the Model group only shows when it lists accounts. */
  client?: unknown;
}

export function AttachMenu({
  onAdd,
  small = false,
  advanced,
}: {
  onAdd: (items: PendingAttachment[]) => void;
  small?: boolean;
  /** Present on the two composers (AssistantPanel, AvatarWindow); absent elsewhere skips the
   *  Advanced submenu entirely rather than rendering a broken one. */
  advanced?: AdvancedControls;
}) {
  const label = advanced && (advanced.accessMode !== "ask" || advanced.model) ? advancedLabel(advanced) : null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <span className="attach-trigger">
          <IconButton aria-label="Add files, folders, images or audio" size={small ? "sm" : "default"}>
            <Plus size={small ? 14 : 16} aria-hidden="true" />
          </IconButton>
          {label ? <span className="attach-trigger__chip">{label}</span> : null}
        </span>
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
        {advanced ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <Settings2 size={14} aria-hidden="true" /> Advanced
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <AdvancedMenu {...advanced} />
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function AdvancedMenu({ accessMode, onAccessModeChange, model, onModelChange, client }: AdvancedControls) {
  const [accounts, setAccounts] = useState<ModelProviderAccount[] | null>(null);
  useEffect(() => {
    const accountsClient = isModelAccountsClient(client) ? (client as ModelAccountsLike) : null;
    if (!accountsClient) return;
    let cancelled = false;
    accountsClient
      .listModelAccounts()
      .then((list) => !cancelled && setAccounts(list))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client]);

  function chooseFull() {
    if (window.confirm("Full access lets Alpha use the internet and edit any file on this computer without asking first. Continue?")) {
      onAccessModeChange("full");
    }
  }

  return (
    <>
      {accounts?.length ? (
        <>
          <DropdownMenuLabel>Model</DropdownMenuLabel>
          {accounts.map((account) => (
            <DropdownMenuItem key={account.id} onSelect={() => onModelChange(model?.provider === account.id ? null : { provider: account.id })}>
              <span className={`ui-menu__dot ui-menu__dot--${account.dot.color}`} title={account.dot.tooltip} aria-hidden="true" />
              <span className="ui-menu__body">{account.label}</span>
              {model?.provider === account.id ? <Check size={14} aria-hidden="true" className="ui-menu__check" /> : <span className="ui-menu__check" />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
        </>
      ) : null}
      <DropdownMenuLabel>Access</DropdownMenuLabel>
      {ACCESS_MODES.map((mode) => {
        const copy = ACCESS_MODE_COPY[mode];
        return (
          <DropdownMenuItem
            key={mode}
            className={mode === "full" ? "ui-menu__item--warning" : ""}
            onSelect={() => (mode === "full" ? chooseFull() : onAccessModeChange(mode))}
          >
            {accessMode === mode ? <Check size={14} aria-hidden="true" className="ui-menu__check" /> : <span className="ui-menu__check" />}
            <span className="ui-menu__body">
              {copy.title}
              <div className="ui-menu__sub-label">{copy.hint}</div>
            </span>
          </DropdownMenuItem>
        );
      })}
    </>
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
