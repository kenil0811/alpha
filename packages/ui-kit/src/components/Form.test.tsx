import { render, screen } from "@testing-library/react";
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
