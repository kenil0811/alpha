import { useEffect, useId, useRef, useState } from "react";
import { Button, type SelectOption } from "./controls";

export interface FilterDefinition {
  id: string;
  label: string;
  options: readonly SelectOption[];
  /** Label of the "no filter" choice. */
  anyLabel?: string;
}

export interface FilterValues {
  search: string;
  [filterId: string]: string;
}

export interface FilterBarProps {
  /** Omit to hide the search box. */
  searchLabel?: string;
  searchPlaceholder?: string;
  filters?: readonly FilterDefinition[];
  values: FilterValues;
  onChange: (values: FilterValues) => void;
  /** Number of matching items to announce, when known ("12 shown", "more than 100"). */
  resultLabel?: string;
  /** Milliseconds to wait after typing before applying the search. */
  debounceMs?: number;
}

/** Search plus choice filters over a list. Changes apply as the person types or chooses;
 *  "Clear filters" resets everything. The result count is announced politely. */
export function FilterBar({
  searchLabel = "Search",
  searchPlaceholder,
  filters = [],
  values,
  onChange,
  resultLabel,
  debounceMs = 250,
}: FilterBarProps) {
  const id = useId();
  const [search, setSearch] = useState(values.search);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef(values);
  latest.current = values;

  useEffect(() => setSearch(values.search), [values.search]);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  function setSearchDebounced(text: string) {
    setSearch(text);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onChange({ ...latest.current, search: text }), debounceMs);
  }

  const active = Boolean(values.search) || filters.some((f) => Boolean(values[f.id]));
  return (
    <div className="a-filter-bar" role="search" aria-label="Filter the list">
      {searchLabel ? (
        <div className="a-field a-filter-bar__search">
          <label className="a-field__label" htmlFor={`${id}-search`}>
            {searchLabel}
          </label>
          <input
            id={`${id}-search`}
            className="a-input"
            type="search"
            value={search}
            placeholder={searchPlaceholder}
            onChange={(event) => setSearchDebounced(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                if (timer.current) clearTimeout(timer.current);
                onChange({ ...latest.current, search });
              }
            }}
          />
        </div>
      ) : null}
      {filters.map((filter) => (
        <div className="a-field a-filter-bar__filter" key={filter.id}>
          <label className="a-field__label" htmlFor={`${id}-${filter.id}`}>
            {filter.label}
          </label>
          <select
            id={`${id}-${filter.id}`}
            className="a-input"
            value={values[filter.id] ?? ""}
            onChange={(event) => onChange({ ...latest.current, [filter.id]: event.target.value })}
          >
            <option value="">{filter.anyLabel ?? "Any"}</option>
            {filter.options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      ))}
      <Button
        disabled={!active}
        onClick={() => {
          if (timer.current) clearTimeout(timer.current);
          setSearch("");
          const cleared: FilterValues = { search: "" };
          for (const f of filters) cleared[f.id] = "";
          onChange(cleared);
        }}
      >
        Clear filters
      </Button>
      <div className="a-filter-bar__count" role="status" aria-live="polite">
        {resultLabel ?? ""}
      </div>
    </div>
  );
}
