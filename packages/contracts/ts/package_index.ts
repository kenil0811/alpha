/* Generated from package_index.schema.json (contract 0.2). Do not edit. */

/**
 * package.index.json: platform-produced digests of every sealed file plus the identities
 * the Version was validated against. `package_sha256` is the canonical digest of the rest.
 */
export interface PackageIndex {
  app_id: string;
  contract_version?: "0.2";
  dependency_manifest_sha256: string;
  files: PackageFile[];
  package_sha256: string;
  toolchain: {
    [k: string]: string;
  };
}
export interface PackageFile {
  path: string;
  sha256: string;
  size: number;
}
