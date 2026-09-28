/* Generated from skill_spec.schema.json (contract 0.2). Do not edit. */

export interface SkillSpec {
  action?: string | null;
  created_at: string;
  created_by?: "person" | "assistant";
  description: string;
  id: string;
  /**
   * @maxItems 8
   */
  inputs?:
    | []
    | [SkillInput]
    | [SkillInput, SkillInput]
    | [SkillInput, SkillInput, SkillInput]
    | [SkillInput, SkillInput, SkillInput, SkillInput]
    | [SkillInput, SkillInput, SkillInput, SkillInput, SkillInput]
    | [SkillInput, SkillInput, SkillInput, SkillInput, SkillInput, SkillInput]
    | [SkillInput, SkillInput, SkillInput, SkillInput, SkillInput, SkillInput, SkillInput]
    | [SkillInput, SkillInput, SkillInput, SkillInput, SkillInput, SkillInput, SkillInput, SkillInput];
  instructions?: string;
  kind?: "procedure" | "code";
  module?: string | null;
  produces?: string;
  /**
   * @maxItems 12
   */
  sources?:
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
    | [string, string, string, string, string, string, string, string, string, string, string, string];
  state?: "active" | "retired";
  title: string;
  updated_at: string;
}
export interface SkillInput {
  description?: string;
  name: string;
  required?: boolean;
}
