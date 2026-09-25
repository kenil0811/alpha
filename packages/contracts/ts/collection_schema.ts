/* Generated from collection_schema.schema.json (contract 0.2). Do not edit. */

export type FieldKind =
  "text" | "number" | "integer" | "boolean" | "date" | "datetime" | "choice" | "reference" | "json";

export interface CollectionSchema {
  description?: string;
  /**
   * @minItems 1
   * @maxItems 64
   */
  fields: [FieldSpec, ...FieldSpec[]];
  /**
   * @maxItems 8
   */
  indexes?:
    | []
    | [string[]]
    | [string[], string[]]
    | [string[], string[], string[]]
    | [string[], string[], string[], string[]]
    | [string[], string[], string[], string[], string[]]
    | [string[], string[], string[], string[], string[], string[]]
    | [string[], string[], string[], string[], string[], string[], string[]]
    | [string[], string[], string[], string[], string[], string[], string[], string[]];
  name: string;
  /**
   * @maxItems 4
   */
  unique?:
    [] | [string[]] | [string[], string[]] | [string[], string[], string[]] | [string[], string[], string[], string[]];
}
/**
 * One declared field. Bounds default to platform policy when omitted.
 */
export interface FieldSpec {
  choices?: string[] | null;
  collection?: string | null;
  description?: string;
  kind: FieldKind;
  max_bytes?: number | null;
  max_length?: number | null;
  maximum?: number | null;
  minimum?: number | null;
  name: string;
  required?: boolean;
}
