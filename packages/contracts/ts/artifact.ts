/* Generated from artifact.schema.json (contract 0.2). Do not edit. */

export interface Artifact {
  artifact_id: string;
  contract_version?: "0.2";
  created_at: string;
  display_name: string;
  media_type: string;
  owner: ArtifactOwner;
  provenance: ArtifactProvenance;
  retention?: "until_deleted";
  sha256: string;
  size_bytes: number;
  storage_ref: string;
}
export interface ArtifactOwner {
  id: string;
  kind: "app" | "task";
}
export interface ArtifactProvenance {
  action_id?: string | null;
  created_by: "app_run" | "task_run" | "user";
  derived_from?: string[];
  model_call_ids?: string[];
  package_sha256?: string | null;
  run_id?: string | null;
  version_id?: string | null;
}
