/* Generated from dependency_profile.schema.json (contract 0.2). Do not edit. */

export type ProfileKind = "python_runtime" | "ui_build";
export type ProfileRole = "app_task_compute" | "trusted_tool";

export interface DependencyProfile {
  compatibility: ProfileCompatibility;
  kind: ProfileKind;
  locks: LockRef[];
  manifest_sha256: string;
  packages: PackagePin[];
  profile_id: string;
  role: ProfileRole;
  target: ProfileTarget;
}
export interface ProfileCompatibility {
  bridge_version?: string | null;
  contract_version: string;
  kit_version?: string | null;
  sdk_version?: string | null;
  worker_protocol?: number | null;
}
export interface LockRef {
  path: string;
  sha256: string;
}
export interface PackagePin {
  artifact?: string | null;
  artifact_sha256: string;
  name: string;
  version: string;
}
export interface ProfileTarget {
  arch: string;
  interpreter_build?: string | null;
  os: string;
  python_abi?: string | null;
  python_implementation?: string | null;
  python_version?: string | null;
  ui_toolchain?: {
    [k: string]: string;
  } | null;
}
