/** Saving a module's exported `.alphamodule` file: the native Downloads folder on desktop
 *  (revealed in Finder), a plain browser download on web. */
import { hasTauri } from "../core/session";

export function moduleFilename(appId: string): string {
  return `${appId}.alphamodule`;
}

/** Writes `blob` to disk and tells the person where it landed. Returns the saved path on
 *  desktop (for the toast), or nothing on web (the browser owns the download UI there). */
export async function saveExportedModule(filename: string, blob: Blob): Promise<{ savedTo?: string }> {
  if (hasTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    const bytes = Array.from(new Uint8Array(await blob.arrayBuffer()));
    const savedTo = await invoke<string>("save_to_downloads", { filename, data: bytes });
    return { savedTo };
  }
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
  return {};
}
