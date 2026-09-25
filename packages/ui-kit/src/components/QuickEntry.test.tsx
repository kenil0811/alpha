import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AlphaProvider, useAction } from "../data/hooks";
import { createMemoryApp, type MemoryApp } from "../testing/memoryApp";
import { QuickEntry, type ParseResult } from "./QuickEntry";

type Entry = { title: string; amount: number | null };

function parse(text: string): ParseResult<Entry> {
  const trimmed = text.trim();
  if (!trimmed) return { status: "empty" };
  const match = trimmed.match(/^(\d+(?:\.\d+)?)\s+(.+)$/);
  if (match) return { status: "ok", value: { title: match[2], amount: Number(match[1]) }, summary: `${match[1]} × ${match[2]}` };
  if (trimmed.length > 60) return { status: "invalid", message: "Keep it under 60 characters." };
  return { status: "ambiguous", value: { title: trimmed, amount: null }, summary: trimmed, note: "No amount given; it will be saved without one." };
}

function Composition() {
  const add = useAction<{ id: string; revision: number }>("add_entry");
  const remove = useAction("remove_entry");
  return (
    <QuickEntry
      label="Add an entry"
      parse={parse}
      onSubmit={async (value) => {
        const created = await add.run(value);
        return { undo: async () => void (await remove.run({ id: created.id, expected_revision: created.revision })) };
      }}
    />
  );
}

async function app(): Promise<MemoryApp> {
  return createMemoryApp({
    views: [{ id: "entries.list", collection: "entries" }],
    actions: {
      add_entry: (input, store) => {
        const row = store.create("entries", input);
        return { id: row.id, revision: row.revision };
      },
      remove_entry: (input, store) => {
        store.remove("entries", String(input.id), Number(input.expected_revision));
        return {};
      },
    },
  });
}

describe("QuickEntry through the bridge", () => {
  it("adds with Enter, keeps focus, previews and undoes", async () => {
    const memory = await app();
    const user = userEvent.setup();
    render(
      <AlphaProvider client={memory.client}>
        <Composition />
      </AlphaProvider>,
    );
    const input = screen.getByLabelText("Add an entry");
    await user.click(input);
    await user.type(input, "3 paper");
    expect(screen.getByText("Will add: 3 × paper")).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(await screen.findByText(/Added 3 × paper/)).toBeInTheDocument();
    expect(input).toHaveValue("");
    expect(input).toHaveFocus();
    expect(memory.store.records.entries).toHaveLength(1);
    expect(memory.store.records.entries[0].values).toEqual({ title: "paper", amount: 3 });

    await user.type(input, "lamp");
    expect(screen.getByText(/No amount given/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText(/Removed 3 × paper/)).toBeInTheDocument();
    expect(memory.store.records.entries).toHaveLength(0);
  });

  it("keeps the text after a failed save and succeeds on retry", async () => {
    const memory = await app();
    const user = userEvent.setup();
    render(
      <AlphaProvider client={memory.client}>
        <Composition />
      </AlphaProvider>,
    );
    const input = screen.getByLabelText("Add an entry");
    memory.failNext("add_entry", "entries.amount must be at most 1000");
    await user.type(input, "5000 bricks{Enter}");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Not saved. Amount must be at most 1000");
    expect(input).toHaveValue("5000 bricks");
    expect(input).toHaveFocus();
    expect(memory.store.records.entries ?? []).toHaveLength(0);

    await user.clear(input);
    await user.type(input, "500 bricks{Enter}");
    await waitFor(() => expect(screen.getByText(/Added 500 × bricks/)).toBeInTheDocument());
    expect(memory.store.records.entries).toHaveLength(1);
  });

  it("explains invalid or empty input without saving, and Escape clears", async () => {
    const memory = await app();
    const user = userEvent.setup();
    render(
      <AlphaProvider client={memory.client}>
        <Composition />
      </AlphaProvider>,
    );
    const input = screen.getByLabelText("Add an entry");
    await user.type(input, "{Enter}");
    expect(await screen.findByText("Type something to add.")).toBeInTheDocument();
    await user.type(input, "x".repeat(61) + "{Enter}");
    expect(await screen.findByText("Keep it under 60 characters.")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    await user.keyboard("{Escape}");
    expect(input).toHaveValue("");
    expect(memory.store.records.entries ?? []).toHaveLength(0);
  });
});
