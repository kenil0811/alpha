/* Generated from validation_plan.schema.json (contract 0.2). Do not edit. */

export type FilterOp = "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "contains" | "starts_with" | "is_null";

export interface ValidationPlan {
  contract_version?: "0.2";
  /**
   * @minItems 1
   * @maxItems 20
   */
  scenarios:
    | [Scenario]
    | [Scenario, Scenario]
    | [Scenario, Scenario, Scenario]
    | [Scenario, Scenario, Scenario, Scenario]
    | [Scenario, Scenario, Scenario, Scenario, Scenario]
    | [Scenario, Scenario, Scenario, Scenario, Scenario, Scenario]
    | [Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario]
    | [Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario]
    | [Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario]
    | [Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario]
    | [Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario, Scenario]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ]
    | [
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario,
        Scenario
      ];
  ui?: UiPlan | null;
}
export interface Scenario {
  description: string;
  id: string;
  /**
   * @minItems 1
   * @maxItems 20
   */
  steps:
    | [InvokeStep | RecordsStep]
    | [InvokeStep | RecordsStep, InvokeStep | RecordsStep]
    | [InvokeStep | RecordsStep, InvokeStep | RecordsStep, InvokeStep | RecordsStep]
    | [InvokeStep | RecordsStep, InvokeStep | RecordsStep, InvokeStep | RecordsStep, InvokeStep | RecordsStep]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ]
    | [
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep,
        InvokeStep | RecordsStep
      ];
}
/**
 * Run one declared action through the platform and check its outcome.
 */
export interface InvokeStep {
  action: string;
  exact?: boolean;
  expect?: "succeeded" | "failed";
  id: string;
  input?: {
    [k: string]: unknown;
  };
  kind?: "invoke";
  output?: {
    [k: string]: unknown;
  } | null;
}
/**
 * Read the preview store directly (never through the candidate) and check what persisted.
 */
export interface RecordsStep {
  collection: string;
  count?: number | null;
  id: string;
  /**
   * @maxItems 20
   */
  includes?:
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
  kind?: "records";
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
/**
 * The screen's primary interaction and what it must visibly and durably do.
 */
export interface UiPlan {
  /**
   * @minItems 1
   * @maxItems 12
   */
  primary:
    | [UiStep]
    | [UiStep, UiStep]
    | [UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep]
    | [UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep, UiStep];
  saved?: RecordsStep | null;
  /**
   * @maxItems 20
   */
  seed?:
    | []
    | [InvokeStep]
    | [InvokeStep, InvokeStep]
    | [InvokeStep, InvokeStep, InvokeStep]
    | [InvokeStep, InvokeStep, InvokeStep, InvokeStep]
    | [InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep]
    | [InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep]
    | [InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep]
    | [InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep]
    | [InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep, InvokeStep]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ]
    | [
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep,
        InvokeStep
      ];
  /**
   * @maxItems 10
   */
  seed_shows?:
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
    | [string, string, string, string, string, string, string, string, string, string];
  /**
   * @maxItems 10
   */
  shows?:
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
    | [string, string, string, string, string, string, string, string, string, string];
}
/**
 * One user action on the rendered screen, addressed the way a person would: by the visible
 * label of a field or the name of a button.
 */
export interface UiStep {
  key?: string | null;
  kind: "fill" | "press" | "click" | "select" | "check";
  label?: string | null;
  text?: string | null;
}
