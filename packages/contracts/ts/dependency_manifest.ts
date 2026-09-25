/* Generated from dependency_manifest.schema.json (contract 0.2). Do not edit. */

/**
 * Platform-produced per-Version record. No local paths, grants or secrets.
 */
export interface DependencyManifest {
  modules?: PackagePin[];
  runtime_profile_id: string;
  runtime_profile_manifest_sha256: string;
  sdk: SdkPin;
  ui_build?: UiBuildRef | null;
}
export interface PackagePin {
  artifact?: string | null;
  artifact_sha256: string;
  name: string;
  version: string;
}
export interface SdkPin {
  artifact_sha256: string;
  name: string;
  version: string;
}
export interface UiBuildRef {
  bridge: PackagePin;
  kit: PackagePin;
  manifest_sha256: string;
  profile_id: string;
}
