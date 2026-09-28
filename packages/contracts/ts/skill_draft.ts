/* Generated from skill_draft.schema.json (contract 0.2). Do not edit. */

/**
 * What a person (or the assistant) sends to make or change a skill.
 */
export interface SkillDraft {
  action?: string | null;
  description: string;
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
  title: string;
}
export interface SkillInput {
  description?: string;
  name: string;
  required?: boolean;
}
