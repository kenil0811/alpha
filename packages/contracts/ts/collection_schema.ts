/* Generated from collection_schema.schema.json (contract 0.2). Do not edit. */

export type FieldKind =
  | "text"
  | "long_text"
  | "number"
  | "integer"
  | "boolean"
  | "date"
  | "datetime"
  | "choice"
  | "status"
  | "multiselect"
  | "url"
  | "reference"
  | "json";

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
  page?: PageSpec | null;
  title_field?: string | null;
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
  done_choices?: string[] | null;
  kind: FieldKind;
  max_bytes?: number | null;
  max_length?: number | null;
  maximum?: number | null;
  minimum?: number | null;
  name: string;
  required?: boolean;
}
/**
 * How the collection's derived page opens. Every collection gets a page (table first,
 * with the other views a click away); this only sets the starting point and what to hide.
 */
export interface PageSpec {
  columns?: string[] | null;
  date_field?: string | null;
  group_field?: string | null;
  quick_entry?: QuickEntrySpec | null;
  sort?: SortKey | null;
  view?: "table" | "board" | "list" | "calendar" | "chart";
}
export interface QuickEntrySpec {
  action: string;
  input: string;
  placeholder: string;
}
export interface SortKey {
  direction?: "asc" | "desc";
  field: string;
}
