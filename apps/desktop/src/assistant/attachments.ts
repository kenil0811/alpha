/**
 * Attaching files, folders, images and audio to a message: picking (native dialogs under Tauri,
 * <input type=file> on the web), drag-and-drop and paste, the wire shape Core reads them as, and
 * a hook point so another feature (importing an exported module file, extension `.alphamodule`)
 * can claim a picked file before it becomes a plain attachment.
 *
 * Raw bytes stay local: a desktop pick hands Core a path it reads itself; only a web pick, drop
 * or paste (no filesystem path to give instead) reads bytes into memory here, to send as one
 * message's payload.
 */
import { useCallback, useEffect } from "react";
import type { AttachmentWire } from "../core/client";
import { hasTauri } from "../core/session";

export type AttachmentKind = "file" | "image" | "folder" | "audio";

/** One thing attached to a message, as the composer holds it before sending. */
export interface PendingAttachment {
  id: string;
  kind: AttachmentKind;
  name: string;
  size?: number;
  mime?: string;
  /** Desktop: an absolute local path Core reads directly. */
  path?: string;
  /** Web, a drop, or a paste: the file's bytes, base64 (there is no path to hand over instead). */
  contentB64?: string;
  /** A thumbnail for an image chip, when the bytes are already in hand. */
  previewUrl?: string;
}

export function toWire(a: PendingAttachment): AttachmentWire {
  return {
    kind: a.kind,
    name: a.name,
    size: a.size ?? null,
    mime: a.mime ?? null,
    path: a.path ?? null,
    content_b64: a.contentB64 ?? null,
  };
}

export const MAX_ATTACHMENTS = 10;
// A generous client-side cap on what gets read into memory; Core caps further per kind.
const MAX_READ_BYTES = 8_000_000;

let uid = 0;
function nextId(): string {
  uid += 1;
  return `att_${Date.now()}_${uid}`;
}

const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "heic"]);
const AUDIO_EXTS = new Set(["mp3", "wav", "m4a", "aac", "flac", "ogg", "webm"]);

function extOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
}

export function kindOfName(name: string, mime?: string): AttachmentKind {
  if (mime?.startsWith("image/") || IMAGE_EXTS.has(extOf(name))) return "image";
  if (mime?.startsWith("audio/") || AUDIO_EXTS.has(extOf(name))) return "audio";
  return "file";
}

export function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("could not read the file"));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

/** A browser File (a web pick, a drop, or a paste) becomes a pending attachment. */
export async function fromBrowserFile(file: File, nameOverride?: string): Promise<PendingAttachment> {
  const name = nameOverride || file.name || "pasted";
  const kind = kindOfName(name, file.type);
  const attachment: PendingAttachment = { id: nextId(), kind, name, size: file.size, mime: file.type || undefined };
  if (kind === "image") attachment.previewUrl = URL.createObjectURL(file);
  if (kind !== "audio" && file.size <= MAX_READ_BYTES) {
    try {
      attachment.contentB64 = await readAsBase64(file);
    } catch {
      /* sent without content; Core says plainly that it could not be read */
    }
  }
  return attachment;
}

export function attachmentFromPath(path: string, kindHint?: AttachmentKind): PendingAttachment {
  const name = path.split(/[\\/]/).pop() || path;
  return { id: nextId(), kind: kindHint ?? kindOfName(name), name, path };
}

// ----- the hook point: another feature may claim a picked file first -----------------------

export interface AttachmentHandlerEntry {
  match: (file: PendingAttachment) => boolean;
  handle: (file: PendingAttachment) => void;
}
const handlers: AttachmentHandlerEntry[] = [];

/** Register a claim on picked files (for example, importing a `.alphamodule` export) before
 *  they become plain message attachments. Returns a function to unregister it. */
export function registerAttachmentHandler(
  match: AttachmentHandlerEntry["match"],
  handle: AttachmentHandlerEntry["handle"],
): () => void {
  const entry = { match, handle };
  handlers.push(entry);
  return () => {
    const at = handlers.indexOf(entry);
    if (at !== -1) handlers.splice(at, 1);
  };
}

/** Files no registered handler claimed, capped to the room left on the message. */
export function unclaimed(files: PendingAttachment[], already: number): PendingAttachment[] {
  const room = Math.max(0, MAX_ATTACHMENTS - already);
  const rest: PendingAttachment[] = [];
  for (const file of files) {
    const handler = handlers.find((h) => h.match(file));
    if (handler) handler.handle(file);
    else rest.push(file);
  }
  return rest.slice(0, room);
}

// ----- picking -------------------------------------------------------------------------

function pickWithInput(opts: { multiple?: boolean; accept?: string; directory?: boolean }): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    if (opts.multiple) input.multiple = true;
    if (opts.accept) input.accept = opts.accept;
    if (opts.directory) {
      input.webkitdirectory = true;
      (input as unknown as { directory?: boolean }).directory = true;
    }
    input.style.display = "none";
    input.addEventListener(
      "change",
      () => {
        resolve(Array.from(input.files ?? []));
        input.remove();
      },
      { once: true },
    );
    document.body.appendChild(input);
    input.click();
  });
}

async function tauriDialog(): Promise<typeof import("@tauri-apps/plugin-dialog") | null> {
  if (!hasTauri()) return null;
  try {
    return await import("@tauri-apps/plugin-dialog");
  } catch {
    return null;
  }
}

/** "Add files or images": a native multi-select under Tauri (paths only, nothing read here); a
 *  plain <input type=file multiple> on the web. */
export async function pickFilesOrImages(): Promise<PendingAttachment[]> {
  const dialog = await tauriDialog();
  if (dialog) {
    const picked = await dialog.open({ multiple: true, title: "Add files or images" });
    const paths = picked ? (Array.isArray(picked) ? picked : [picked]) : [];
    return paths.map((path) => attachmentFromPath(path));
  }
  const files = await pickWithInput({ multiple: true });
  return Promise.all(files.map((f) => fromBrowserFile(f)));
}

/** "Add a folder": a native folder picker under Tauri, handed to Core as one path it walks
 *  itself. The web has no folder path to hand over, so its files are picked individually and
 *  sent as ordinary file attachments (capped) instead. */
export async function pickFolder(): Promise<PendingAttachment[]> {
  const dialog = await tauriDialog();
  if (dialog) {
    const picked = await dialog.open({ directory: true, title: "Add a folder" });
    if (!picked || Array.isArray(picked)) return [];
    return [attachmentFromPath(picked, "folder")];
  }
  const files = await pickWithInput({ multiple: true, directory: true });
  return Promise.all(
    files
      .slice(0, MAX_ATTACHMENTS)
      .map((f) => fromBrowserFile(f, (f as unknown as { webkitRelativePath?: string }).webkitRelativePath || f.name)),
  );
}

/** "Add audio file": a file picker filtered to audio. Live capture (a "Record audio" item) is
 *  not wired up here.
 *  ponytail: no recorder yet; add a MediaRecorder-backed one here if live capture is wanted. */
export async function pickAudioFile(): Promise<PendingAttachment[]> {
  const dialog = await tauriDialog();
  if (dialog) {
    const picked = await dialog.open({
      multiple: true,
      title: "Add audio",
      filters: [{ name: "Audio", extensions: Array.from(AUDIO_EXTS) }],
    });
    const paths = picked ? (Array.isArray(picked) ? picked : [picked]) : [];
    return paths.map((path) => attachmentFromPath(path, "audio"));
  }
  const files = await pickWithInput({ multiple: true, accept: "audio/*" });
  return Promise.all(files.map((f) => fromBrowserFile(f)));
}

// ----- drag-and-drop and paste -----------------------------------------------------------

/** Drop a file (or several) onto the composer. Under Tauri, native OS drag-drop is on by
 *  default (see tauri.conf.json), which disables the webview's own DOM drop events in favour of
 *  `onDragDropEvent` (real filesystem paths, no bytes read); the web falls back to plain HTML5
 *  drag-and-drop (`dataTransfer.files`, read into memory since there is no path). */
export function useComposerDrop(onAdd: (items: PendingAttachment[]) => void) {
  useEffect(() => {
    if (!hasTauri()) return;
    let unlisten: (() => void) | undefined;
    let cancelled = false;
    void import("@tauri-apps/api/webview")
      .then(({ getCurrentWebview }) =>
        getCurrentWebview().onDragDropEvent((event) => {
          if (event.payload.type !== "drop") return;
          onAdd(event.payload.paths.map((p) => attachmentFromPath(p)));
        }),
      )
      .then((un) => {
        if (cancelled) un();
        else unlisten = un;
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [onAdd]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      if (hasTauri()) return; // the native listener above handles it
      e.preventDefault();
      const files = Array.from(e.dataTransfer?.files ?? []);
      if (files.length) void Promise.all(files.map((f) => fromBrowserFile(f))).then(onAdd);
    },
    [onAdd],
  );
  const onDragOver = useCallback((e: React.DragEvent) => {
    if (!hasTauri()) e.preventDefault();
  }, []);
  return { onDrop, onDragOver };
}

/** Paste an image (or any file) onto the composer: clipboard bytes, read into memory either
 *  way (a pasted item never has a path to hand over instead). */
export function usePasteAttachments(onAdd: (items: PendingAttachment[]) => void) {
  return useCallback(
    (e: React.ClipboardEvent) => {
      const files = Array.from(e.clipboardData?.items ?? [])
        .map((item) => item.getAsFile())
        .filter((f): f is File => f !== null);
      if (!files.length) return;
      e.preventDefault();
      void Promise.all(files.map((f, i) => fromBrowserFile(f, f.name || `pasted-${i + 1}.png`))).then(onAdd);
    },
    [onAdd],
  );
}
