/* Generated from verification_report.schema.json (contract 0.2). Do not edit. */

export type BuildResultStatus = "candidate" | "failed" | "cancelled";
export type CheckStatus = "passed" | "failed" | "skipped";

export interface VerificationReport {
  attempt_id: string;
  attempt_number: number;
  build_id: string;
  builder_status: BuildResultStatus;
  checks?: CheckResult[];
  contract_version?: "0.2";
  dependency_manifest_sha256?: string | null;
  environment?: {
    [k: string]: string;
  };
  /**
   * @minItems 1
   */
  lineage: [string, ...string[]];
  package_sha256?: string | null;
  passed: boolean;
  qualification_requests?: DependencyQualificationRequest[];
  runtime_profile_id?: string | null;
  supplementary?: CheckResult[];
  ui_build_profile_id?: string | null;
  unresolved_limits?: string[];
  version_id?: string | null;
}
export interface CheckResult {
  detail?: {
    [k: string]: unknown;
  };
  /**
   * @maxItems 20
   */
  evidence?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  id: string;
  required?: boolean;
  stage: string;
  status: CheckStatus;
  summary: string;
}
/**
 * A bounded request to qualify a package outside the installed profile. Recording it never
 * changes a shared environment; a new profile must be built and qualified first.
 */
export interface DependencyQualificationRequest {
  found_in: "app.yaml modules" | "import";
  package: string;
  reason: string;
  runtime_profile_id: string;
  version?: string | null;
  where: string;
}
