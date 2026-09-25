/* Generated from app_source.schema.json (contract 0.2). Do not edit. */

export type EffectClass = "none" | "local_write" | "external_read" | "external_write";
export type Invocable = "assistant" | "ui" | "manual" | "trigger";
export type RetryClass = "pure" | "idempotent" | "requires_reconciliation";
export type FieldKind =
  "text" | "number" | "integer" | "boolean" | "date" | "datetime" | "choice" | "reference" | "json";

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
  ui?: {
    [k: string]: unknown;
  } | null;
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
