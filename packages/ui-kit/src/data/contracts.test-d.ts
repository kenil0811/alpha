/**
 * Type-level sync check: the kit's own copies of contract shapes (kept so the packed kit needs
 * nothing but the bridge) must stay equal to the types generated from the Python contracts.
 * `pnpm --filter @alpha/ui-kit typecheck` fails when either side changes alone.
 */
import type { AppRecord, RecordQuery } from "@alpha/contracts";
import type { FieldProvenanceData, RecordRow } from "./hooks";
import type { FilterOp, SortKey } from "./query";

type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
type Expect<T extends true> = T;

type ContractClause = Extract<NonNullable<RecordQuery["where"]>, { op: unknown }>;
type ContractSortKey = NonNullable<RecordQuery["order_by"]>[number];
type ContractProvenance = NonNullable<AppRecord["provenance"]>[string];

export type KitMatchesContracts = [
  Expect<Equal<FilterOp, ContractClause["op"]>>,
  Expect<Equal<SortKey["direction"], NonNullable<ContractSortKey["direction"]>>>,
  Expect<Equal<FieldProvenanceData["source"], ContractProvenance["source"]>>,
  // Every field the kit reads from a record exists on the contract's record.
  Expect<Equal<Exclude<keyof RecordRow, keyof AppRecord>, never>>,
  Expect<Equal<Exclude<keyof FieldProvenanceData, keyof ContractProvenance>, never>>,
];
