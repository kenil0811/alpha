import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { StandardDropdown } from "./StandardDropdown";

const MANY = Array.from({ length: 8 }, (_, i) => ({ value: `v${i}`, label: `Option ${i}` }));

function Harness({ options = MANY, onAdd }: { options?: typeof MANY; onAdd?: () => void }) {
  const [value, setValue] = useState<string | null>(null);
  return <StandardDropdown options={options} value={value} onChange={setValue} onAdd={onAdd} addDisabledReason={onAdd ? undefined : "Not available here"} />;
}

describe("StandardDropdown", () => {
  it("shows a search box only past 6 options, and filters by it", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button"));
    const search = screen.getByPlaceholderText("Search…");
    expect(search).toBeInTheDocument();
    await user.type(search, "Option 3");
    expect(screen.getByRole("option", { name: "Option 3" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Option 0" })).not.toBeInTheDocument();
  });

  it("hides the search below the 6-option threshold, and picking closes the menu", async () => {
    const user = userEvent.setup();
    render(<Harness options={MANY.slice(0, 3)} />);
    await user.click(screen.getByRole("button"));
    expect(screen.queryByPlaceholderText("Search…")).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "Option 1" }));
    expect(screen.queryByRole("option", { name: "Option 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveTextContent("Option 1");
  });

  it("disables the pinned add row with its reason when refused", async () => {
    const user = userEvent.setup();
    const onAdd = vi.fn();
    render(<StandardDropdown options={MANY.slice(0, 3)} value={null} onChange={() => undefined} onAdd={onAdd} addDisabledReason="Not available here" />);
    await user.click(screen.getByRole("button"));
    const addRow = screen.getByRole("button", { name: /Not available here/ });
    expect(addRow).toBeDisabled();
    expect(onAdd).not.toHaveBeenCalled();
  });
});
