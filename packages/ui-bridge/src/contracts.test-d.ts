/**
 * Type-level sync check: the bridge's hand-written query payload must accept exactly the sort
 * keys the contract defines. `pnpm --filter @alpha/ui-bridge typecheck` fails on drift.
 */
import type { RecordQuery } from "@alpha/contracts";
import type { RecordsQueryPayload } from "./host";

type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
type Expect<T extends true> = T;

type ContractSortKey = NonNullable<RecordQuery["order_by"]>[number];
type BridgeSortKey = NonNullable<RecordsQueryPayload["order_by"]>[number];

export type BridgeMatchesContracts = [
  Expect<Equal<BridgeSortKey["direction"], NonNullable<ContractSortKey["direction"]>>>,
  Expect<Equal<Exclude<keyof BridgeSortKey, keyof ContractSortKey>, never>>,
];
