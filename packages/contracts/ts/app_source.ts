/* Generated from app_source.schema.json (contract 0.2). Do not edit. */

export type EffectClass = "none" | "local_write" | "external_read" | "external_write";
export type Invocable = "assistant" | "ui" | "manual" | "trigger";
export type RetryClass = "pure" | "idempotent" | "requires_reconciliation";
export type FieldKind =
  "text" | "number" | "integer" | "boolean" | "date" | "datetime" | "choice" | "reference" | "json";
export type Bucket = "day" | "week" | "month";
export type ViewKind = "records" | "aggregate";
export type MetricFn = "count" | "sum" | "avg" | "min" | "max";
export type FilterOp = "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "contains" | "starts_with" | "is_null";

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
  runtime_profile: string;
  sdk_version: string;
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
export interface SortKey {
  direction?: "asc" | "desc";
  field: string;
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
