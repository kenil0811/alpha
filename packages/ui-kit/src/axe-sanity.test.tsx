import { render } from "@testing-library/react";
import axe from "axe-core";
import { expect, it } from "vitest";

it("axe detects an unlabeled input in this environment", async () => {
  const { container } = render(<div><input type="text" /><button type="button"></button></div>);
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  const ids = result.violations.map((v) => v.id);
  expect(ids).toContain("label");
  expect(ids).toContain("button-name");
});
