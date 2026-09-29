import { useEffect, useState } from "react";
import type { UserList } from "./types";

// ponytail: local-only Lists; move to Core views table (backend plan step 3)
export function useLists(moduleId: string, blockId: string) {
  const key = `alpha.lists.${moduleId}.${blockId}`;
  const [lists, setLists] = useState<UserList[]>(() => {
    try {
      return JSON.parse(window.localStorage.getItem(key) ?? "[]") as UserList[];
    } catch {
      return [];
    }
  });
  useEffect(() => {
    window.localStorage.setItem(key, JSON.stringify(lists));
  }, [key, lists]);

  function upsert(list: UserList) {
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
