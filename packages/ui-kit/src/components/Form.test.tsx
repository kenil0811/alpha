import { render, screen } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Button, TextAreaField, TextField } from "./controls";
import { Form } from "./Form";
import { QuickEntry } from "./QuickEntry";

// A frame sandboxed without allow-forms never delivers `submit` events. Reproduce that by
// swallowing every submit event before React sees it; the kit must still save.
const swallow = (event: Event) => {
  event.preventDefault();
  event.stopImmediatePropagation();
};
beforeEach(() => document.addEventListener("submit", swallow, true));
afterEach(() => document.removeEventListener("submit", swallow, true));

describe("Form works without native form submission (sandboxed frames)", () => {
  it("submits on Enter in a text field and on its submit button, but not on Enter in a textarea", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <Form onSubmit={onSubmit}>
        <TextField label="Title" />
        <TextAreaField label="Note" />
        <Button type="submit">Save</Button>
      </Form>,
    );
    await user.type(screen.getByLabelText("Title"), "hello{Enter}");
    expect(onSubmit).toHaveBeenCalledTimes(1);
    await user.type(screen.getByLabelText("Note"), "line one{Enter}line two");
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Note")).toHaveValue("line one\nline two");
    screen.getByRole("button", { name: "Save" }).focus();
    await user.keyboard(" ");
    expect(onSubmit).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("type", "button");
  });

  it("QuickEntry saves with Enter when submit events are blocked", async () => {
    const onSubmit = vi.fn(async () => undefined);
    const user = userEvent.setup();
    render(<QuickEntry label="Add" parse={(t) => (t ? { status: "ok", value: t, summary: t } : { status: "empty" })} onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Add"), "paper{Enter}");
    expect(onSubmit).toHaveBeenCalledWith("paper", "paper");
    expect(await screen.findByText(/Added paper/)).toBeInTheDocument();
  });
});

describe("required fields, focus and drafts (M1 review, shared Form issues)", () => {
  function Entry({ onSave }: { onSave: (company: string, role: string) => Promise<void> }) {
    const [company, setCompany] = useState("");
    const [role, setRole] = useState("");
    return (
      <Form
        onSubmit={async () => {
          await onSave(company, role);
          setCompany("");
          setRole("");
        }}
      >
        <TextField label="Company" required value={company} onChange={(e) => setCompany(e.target.value)} />
        <TextField label="Role" required value={role} onChange={(e) => setRole(e.target.value)} />
        <TextField label="Notes" />
        <Button type="submit">Add opening</Button>
      </Form>
    );
  }

  it("does not submit with required fields empty, says which, and focuses the first", async () => {
    const onSave = vi.fn(async () => undefined);
    const user = userEvent.setup();
    render(<Entry onSave={onSave} />);
    await user.type(screen.getByLabelText("Role", { exact: false }), "Analyst");
    await user.click(screen.getByRole("button", { name: "Add opening" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Fill in Company first.");
    expect(screen.getByLabelText("Company", { exact: false })).toHaveFocus();
    expect(screen.getByLabelText("Company", { exact: false })).toHaveAttribute("aria-invalid", "true");

    await user.type(screen.getByLabelText("Company", { exact: false }), "Zenith Foods");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add opening" }));
    expect(onSave).toHaveBeenCalledWith("Zenith Foods", "Analyst");
  });

  it("returns focus to the first field after a save that clears the form, for the next entry", async () => {
    const user = userEvent.setup();
    render(<Entry onSave={async () => undefined} />);
    await user.type(screen.getByLabelText("Company", { exact: false }), "A");
    await user.type(screen.getByLabelText("Role", { exact: false }), "B{Enter}");
    await vi.waitFor(() => expect(screen.getByLabelText("Company", { exact: false })).toHaveFocus());
    expect(screen.getByLabelText("Company", { exact: false })).toHaveValue("");
  });

  it("keeps what was typed when the save fails", async () => {
    const user = userEvent.setup();
    render(
      <Entry
        onSave={async () => {
          throw new Error("offline");
        }}
      />,
    );
    await user.type(screen.getByLabelText("Company", { exact: false }), "Harbor Health");
    await user.type(screen.getByLabelText("Role", { exact: false }), "Ops{Enter}");
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByLabelText("Company", { exact: false })).toHaveValue("Harbor Health");
    expect(screen.getByLabelText("Role", { exact: false })).toHaveValue("Ops");
  });
});
