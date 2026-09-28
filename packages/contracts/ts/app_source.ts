/* Generated from app_source.schema.json (contract 0.2). Do not edit. */

export type EffectClass = "none" | "local_write" | "external_read" | "external_write";
export type Invocable = "assistant" | "ui" | "manual" | "trigger";
export type RetryClass = "pure" | "idempotent" | "requires_reconciliation";
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
export type ColumnFormat = "text" | "number" | "date" | "datetime" | "pill" | "link" | "check";
export type FilterOp = "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "contains" | "starts_with" | "is_null";
export type Bucket = "day" | "week" | "month";
export type ViewKind = "records" | "aggregate";
export type MetricFn = "count" | "sum" | "avg" | "min" | "max";

export interface AppSource {
  /**
   * @minItems 1
   * @maxItems 50
   */
  actions: [ActionDefinition, ...ActionDefinition[]];
  app_id: string;
  /**
   * @maxItems 16
   */
  capabilities?:
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
      ];
  /**
   * @maxItems 32
   */
  collections?: CollectionSchema[];
  config_schema?: {
    [k: string]: unknown;
  };
  contract_version: "0.2";
  description: string;
  modules?: {
    [k: string]: string;
  };
  name: string;
  primary_action?: string | null;
  runtime_profile: string;
  /**
   * @maxItems 8
   */
  schedules?:
    | []
    | [ScheduleSpec]
    | [ScheduleSpec, ScheduleSpec]
    | [ScheduleSpec, ScheduleSpec, ScheduleSpec]
    | [ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec]
    | [ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec]
    | [ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec]
    | [ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec]
    | [ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec, ScheduleSpec];
  screen?: ScreenDeclaration | null;
  sdk_version: string;
  /**
   * @maxItems 8
   */
  summary?:
    | []
    | [MetricsBlock | ProgressBlock | TrendBlock | TextBlock]
    | [MetricsBlock | ProgressBlock | TrendBlock | TextBlock, MetricsBlock | ProgressBlock | TrendBlock | TextBlock]
    | [
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock
      ]
    | [
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock
      ]
    | [
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock
      ]
    | [
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock
      ]
    | [
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock
      ]
    | [
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
        MetricsBlock | ProgressBlock | TrendBlock | TextBlock
      ];
  /**
   * @maxItems 8
   */
  trigger_templates?:
    | []
    | [
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ];
  ui?: UiDeclaration | null;
  /**
   * @maxItems 32
   */
  views?: ViewSpec[];
}
export interface ActionDefinition {
  /**
   * @maxItems 8
   */
  capability_requirements?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
  description: string;
  effect_class?: EffectClass;
  handler: string;
  id: string;
  input_schema: {
    [k: string]: unknown;
  };
  /**
   * @minItems 1
   */
  invocable_from: [Invocable, ...Invocable[]];
  output_schema: {
    [k: string]: unknown;
  };
  retry_class?: RetryClass;
  timeout_seconds?: number;
  title: string;
}
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
/**
 * A local schedule: while Alpha is running, run `action` with `input` every N minutes or
 * once a day at a local time. Missed occurrences are never caught up.
 */
export interface ScheduleSpec {
  action: string;
  daily_at?: string | null;
  enabled?: boolean;
  every_minutes?: number | null;
  id: string;
  input?: {
    [k: string]: unknown;
  };
  title: string;
}
export interface ScreenDeclaration {
  assistant_hint?: string | null;
  icon?: string | null;
  /**
   * @minItems 1
   * @maxItems 8
   */
  tabs:
    | [Tab]
    | [Tab, Tab]
    | [Tab, Tab, Tab]
    | [Tab, Tab, Tab, Tab]
    | [Tab, Tab, Tab, Tab, Tab]
    | [Tab, Tab, Tab, Tab, Tab, Tab]
    | [Tab, Tab, Tab, Tab, Tab, Tab, Tab]
    | [Tab, Tab, Tab, Tab, Tab, Tab, Tab, Tab];
}
export interface Tab {
  /**
   * @minItems 1
   * @maxItems 12
   */
  blocks:
    | [
        | QuickEntryBlock
        | TableBlock
        | MetricsBlock
        | TrendBlock
        | BoardBlock
        | ListBlock
        | FormBlock
        | TextBlock
        | ProgressBlock
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ]
    | [
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        ),
        (
          | QuickEntryBlock
          | TableBlock
          | MetricsBlock
          | TrendBlock
          | BoardBlock
          | ListBlock
          | FormBlock
          | TextBlock
          | ProgressBlock
        )
      ];
  id: string;
  title: string;
}
export interface QuickEntryBlock {
  action: string;
  extra?: {
    [k: string]: unknown;
  };
  input: string;
  kind: "quick_entry";
  placeholder: string;
  voice?: boolean;
}
export interface TableBlock {
  /**
   * @minItems 1
   * @maxItems 24
   */
  columns: [Column, ...Column[]];
  delete?: ActionBinding | null;
  detail?: DetailSpec | null;
  edit?: ActionBinding | null;
  empty?: string | null;
  kind: "table";
  /**
   * @maxItems 12
   */
  lists?:
    | []
    | [SavedList]
    | [SavedList, SavedList]
    | [SavedList, SavedList, SavedList]
    | [SavedList, SavedList, SavedList, SavedList]
    | [SavedList, SavedList, SavedList, SavedList, SavedList]
    | [SavedList, SavedList, SavedList, SavedList, SavedList, SavedList]
    | [SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList]
    | [SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList]
    | [SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList]
    | [SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList, SavedList]
    | [
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList
      ]
    | [
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList,
        SavedList
      ];
  page_size?: number;
  /**
   * @maxItems 6
   */
  row_actions?:
    | []
    | [ActionBinding]
    | [ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding];
  title?: string | null;
  /**
   * @maxItems 8
   */
  totals?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
  view: string;
}
export interface Column {
  editable?: boolean;
  field: string;
  format?: ColumnFormat | null;
  title?: string | null;
  unit?: string | null;
  width?: ("narrow" | "normal" | "wide") | null;
}
/**
 * Run `action` with the record id as `id_param`, plus `input` and what the block adds.
 */
export interface ActionBinding {
  action: string;
  confirm?: string | null;
  id_param?: string | null;
  input?: {
    [k: string]: unknown;
  };
  title?: string | null;
}
/**
 * The record's own page, opened from a table row: every field of the view (or the ones
 * listed), long text as readable paragraphs, and the actions that apply to one record.
 */
export interface DetailSpec {
  /**
   * @maxItems 8
   */
  actions?:
    | []
    | [ActionBinding]
    | [ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding, ActionBinding]
    | [
        ActionBinding,
        ActionBinding,
        ActionBinding,
        ActionBinding,
        ActionBinding,
        ActionBinding,
        ActionBinding,
        ActionBinding
      ];
  /**
   * @maxItems 48
   */
  fields?: string[];
  /**
   * @maxItems 12
   */
  long_fields?:
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
  title_field?: string | null;
}
export interface SavedList {
  id: string;
  title: string;
  where?: Clause | AllOf | AnyOf | Not | null;
}
export interface Clause {
  field: string;
  op: FilterOp;
  value?: {
    [k: string]: unknown;
  };
}
export interface AllOf {
  /**
   * @minItems 1
   * @maxItems 256
   */
  all: [Clause | AllOf | AnyOf | Not, ...(Clause | AllOf | AnyOf | Not)[]];
}
export interface AnyOf {
  /**
   * @minItems 1
   * @maxItems 256
   */
  any: [Clause | AllOf | AnyOf | Not, ...(Clause | AllOf | AnyOf | Not)[]];
}
export interface Not {
  not: Clause | AllOf | AnyOf | Not;
}
export interface MetricsBlock {
  /**
   * @minItems 1
   * @maxItems 6
   */
  cards:
    | [MetricCard]
    | [MetricCard, MetricCard]
    | [MetricCard, MetricCard, MetricCard]
    | [MetricCard, MetricCard, MetricCard, MetricCard]
    | [MetricCard, MetricCard, MetricCard, MetricCard, MetricCard]
    | [MetricCard, MetricCard, MetricCard, MetricCard, MetricCard, MetricCard];
  kind: "metrics";
  title?: string | null;
}
export interface MetricCard {
  goal?: number | null;
  goal_from?: GoalFrom | null;
  goal_label?: string | null;
  hint?: string | null;
  metric: string;
  title: string;
  unit?: string | null;
  view: string;
}
/**
 * A goal read from the first record of a records view (for goals the person sets).
 */
export interface GoalFrom {
  field: string;
  view: string;
}
export interface TrendBlock {
  days?: number;
  goal?: number | null;
  goal_from?: GoalFrom | null;
  kind: "trend";
  title: string;
  unit?: string | null;
  view: string;
  x: string;
  y: string;
}
export interface BoardBlock {
  badge_field?: string | null;
  /**
   * @maxItems 4
   */
  card_actions?:
    | []
    | [ActionBinding]
    | [ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding];
  /**
   * @minItems 2
   * @maxItems 8
   */
  columns:
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
  field_param?: string | null;
  group_field: string;
  kind: "board";
  move?: ActionBinding | null;
  /**
   * @maxItems 4
   */
  subtitle_fields?: [] | [string] | [string, string] | [string, string, string] | [string, string, string, string];
  title?: string | null;
  title_field: string;
  view: string;
}
export interface ListBlock {
  badge_field?: string | null;
  empty?: string | null;
  /**
   * @maxItems 4
   */
  item_actions?:
    | []
    | [ActionBinding]
    | [ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding]
    | [ActionBinding, ActionBinding, ActionBinding, ActionBinding];
  kind: "list";
  link_field?: string | null;
  /**
   * @maxItems 4
   */
  subtitle_fields?: [] | [string] | [string, string] | [string, string, string] | [string, string, string, string];
  title?: string | null;
  title_field: string;
  view: string;
}
export interface FormBlock {
  action: string;
  description?: string | null;
  kind: "form";
  prefill_view?: string | null;
  submit_label?: string | null;
  title?: string | null;
}
export interface TextBlock {
  body: string;
  kind: "text";
  title?: string | null;
}
/**
 * One wide bar: a metric against a goal (calories eaten today out of the day's limit,
 * applications sent out of a weekly target), with what is left or over in words.
 */
export interface ProgressBlock {
  goal?: number | null;
  goal_from?: GoalFrom | null;
  goal_label?: string | null;
  hint?: string | null;
  kind: "progress";
  metric: string;
  title: string;
  unit?: string | null;
  view: string;
}
/**
 * What an App's custom UI may read and do. It carries no native privileges; the shell derives
 * the bridge grant from it and Core enforces the views.
 */
export interface UiDeclaration {
  /**
   * @maxItems 50
   */
  actions?: string[];
  bridge_version?: string | null;
  build_profile?: string | null;
  entry?: string | null;
  kit_version?: string | null;
  /**
   * @maxItems 32
   */
  views?: ViewSpec[];
}
/**
 * A bounded read view the App's UI may query (App UI Bridge, records.query). The view fixes
 * the collection, an optional base filter, the projection and limits; the UI can only narrow it
 * with filters on `filterable` fields and sort on `sortable` fields.
 */
export interface ViewSpec {
  collection: string;
  /**
   * @maxItems 3
   */
  default_order?: [] | [SortKey] | [SortKey, SortKey] | [SortKey, SortKey, SortKey];
  description?: string;
  fields?: string[] | null;
  /**
   * @maxItems 32
   */
  filterable?: string[];
  /**
   * @maxItems 3
   */
  group_by?: [] | [GroupKey] | [GroupKey, GroupKey] | [GroupKey, GroupKey, GroupKey];
  id: string;
  kind?: ViewKind;
  max_limit?: number;
  /**
   * @maxItems 8
   */
  metrics?:
    | []
    | [Metric]
    | [Metric, Metric]
    | [Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric, Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric, Metric, Metric, Metric, Metric];
  /**
   * @maxItems 32
   */
  sortable?: string[];
  where?: Clause | AllOf | AnyOf | Not | null;
}
export interface GroupKey {
  bucket?: Bucket | null;
  field: string;
  timezone?: string | null;
}
export interface Metric {
  field?: string | null;
  fn: MetricFn;
  name: string;
}
