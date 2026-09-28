import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "./Popover";
import { Input } from "./Input";
import "./StandardDropdown.css";

export interface StandardDropdownOption {
  value: string;
  label: string;
}

/** Ports Bridge's StandardDropdown behavior: search past 6 options, a pinned "+ Add…" row
 * that can be disabled with a reason (shown as a tooltip-less inline note, kept simple here). */
export function StandardDropdown({
  options,
  value,
  onChange,
  placeholder = "Select…",
  onAdd,
  addLabel = "Add…",
  addDisabledReason,
}: {
  options: StandardDropdownOption[];
  value: string | null;
  onChange: (value: string) => void;
  placeholder?: string;
  onAdd?: () => void;
  addLabel?: string;
  addDisabledReason?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const showSearch = options.length > 6;
  const filtered = useMemo(
    () => (query.trim() ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase())) : options),
    [options, query],
  );
  const current = options.find((o) => o.value === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="ui-select-trigger ui-std-dropdown__trigger">
          <span>{current ? current.label : placeholder}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start">
        <div className="ui-std-dropdown">
          {showSearch ? (
            <Input autoFocus placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} className="ui-std-dropdown__search" />
          ) : null}
          <div className="ui-std-dropdown__list" role="listbox">
            {filtered.map((option) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                className={`ui-std-dropdown__item${option.value === value ? " ui-std-dropdown__item--current" : ""}`}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                {option.label}
              </button>
            ))}
            {filtered.length === 0 ? <p className="ui-std-dropdown__empty">No matches</p> : null}
          </div>
          {onAdd ? (
            <button
              type="button"
              className="ui-std-dropdown__add"
              disabled={Boolean(addDisabledReason)}
              title={addDisabledReason}
              onClick={() => {
                onAdd();
                setOpen(false);
              }}
            >
              <Plus size={14} /> {addLabel}
              {addDisabledReason ? <span className="ui-std-dropdown__reason">{addDisabledReason}</span> : null}
            </button>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
