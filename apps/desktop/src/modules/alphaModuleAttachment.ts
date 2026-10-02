/** Recognizing and installing a `.alphamodule` file wherever it shows up: dropped on the rail,
 *  or (later) attached in the assistant's composer. Standalone so the composer's attachment
 *  registry (`registerAttachmentHandler`, built on another branch) can wire this in without a
 *  dependency on the rail. */
import { isWorkflowsClient, type CoreClient } from "../core/client";

export const ALPHAMODULE_EXTENSION = ".alphamodule";

export function isAlphaModuleFile(file: File): boolean {
  return file.name.toLowerCase().endsWith(ALPHAMODULE_EXTENSION);
}

/** Installs a `.alphamodule` file as a new module. Throws a plain-language `Error` — from Core's
 *  own rejection reason when there is one — if the runtime isn't ready or the file is rejected. */
export async function handleAlphaModuleAttachment(
  client: CoreClient | null | undefined,
  file: File,
): Promise<{ app_id: string; name: string }> {
  if (!client || !isWorkflowsClient(client)) {
    throw new Error("Alpha's runtime isn't ready yet — try again in a moment.");
  }
  return client.importModuleFile(file);
}
