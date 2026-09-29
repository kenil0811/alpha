import { useEffect, useState } from "react";

// ponytail: local-only Lists; move to Core views table (backend plan step 3)
/** Bridge Lists for one block/collection: declared lists live in its own contract, the person's
 * own lists live here, keyed `alpha.lists.<moduleId>.<blockId>` (a "page:<collection>" blockId
 * for a derived collection page). Generic so any table's saved-list shape can reuse it. */
export function useLists<T extends { id: string; title: string }>(moduleId: string, blockId: string) {
  const key = `alpha.lists.${moduleId}.${blockId}`;
  const [lists, setLists] = useState<T[]>(() => {
    try {
      return JSON.parse(window.localStorage.getItem(key) ?? "[]") as T[];
    } catch {
      return [];
    }
  });
  useEffect(() => {
    window.localStorage.setItem(key, JSON.stringify(lists));
  }, [key, lists]);

  function upsert(list: T) {
    setLists((ls) => {
      const i = ls.findIndex((l) => l.id === list.id);
      if (i === -1) return [...ls, list];
      const next = ls.slice();
      next[i] = list;
      return next;
    });
  }
  function remove(id: string) {
    setLists((ls) => ls.filter((l) => l.id !== id));
  }
  return { lists, upsert, remove };
}
