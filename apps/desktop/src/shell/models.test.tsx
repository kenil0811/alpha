/** Settings -> Models: Claude, ChatGPT, OpenRouter and Grok accounts, keys saved through Core
 *  (the Keychain), never shown back once saved. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";

async function openModels() {
  const client = new FakeWorkflowsClient();
  const user = userEvent.setup();
  render(<App client={client} />);
  expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Settings" }));
  await screen.findByLabelText("Models");
  return { client, user };
}

describe("Settings -> Models provider accounts", () => {
  it("shows every provider's state, with Claude starred as the default", async () => {
    await openModels();
    const providers = await screen.findByLabelText("Model providers");
    expect(within(providers).getByText("Claude")).toBeInTheDocument();
    expect(within(providers).getByText("Claude API")).toBeInTheDocument();
    expect(await within(providers).findByRole("button", { name: "Claude is the default" })).toHaveAttribute("aria-pressed", "true");
    expect(within(providers).getByLabelText("Connected")).toBeInTheDocument();
    expect(within(providers).getByText("ChatGPT")).toBeInTheDocument();
    expect(within(providers).getByLabelText("Not signed in")).toBeInTheDocument();
    expect(within(providers).getAllByLabelText("Not connected").length).toBeGreaterThanOrEqual(2); // OpenRouter, Grok
  });

  it("the star makes another provider the default", async () => {
    const { client, user } = await openModels();
    const providers = await screen.findByLabelText("Model providers");
    await user.click(within(providers).getByRole("button", { name: "Make ChatGPT the default" }));
    await waitFor(() => expect(client.settingsUpdates).toContainEqual({ "models.provider": "chatgpt_codex" }));
    expect(within(providers).getByRole("button", { name: "ChatGPT is the default" })).toHaveAttribute("aria-pressed", "true");
    expect(within(providers).getByRole("button", { name: "Make Claude the default" })).toHaveAttribute("aria-pressed", "false");
  });

  it("saves an OpenRouter key and shows only its last 4 characters afterwards", async () => {
    const { client, user } = await openModels();
    const providers = await screen.findByLabelText("Model providers");
    const openrouterItem = within(providers).getByText("OpenRouter").closest(".item") as HTMLElement;
    const input = within(openrouterItem).getByPlaceholderText("Paste a key");
    await user.type(input, "sk-or-abcd1234");
    await user.click(within(openrouterItem).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(client.providers.find((p) => p.id === "openrouter")?.state).toBe("key_saved"));
    expect(await within(openrouterItem).findByLabelText(/•••• 1234/)).toBeInTheDocument();
  });

  it("removes a saved key", async () => {
    const { client, user } = await openModels();
    const providers = await screen.findByLabelText("Model providers");
    const grokItem = within(providers).getByText("Grok").closest(".item") as HTMLElement;
    await user.type(within(grokItem).getByPlaceholderText("Paste a key"), "xai-test-9999");
    await user.click(within(grokItem).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(client.providers.find((p) => p.id === "grok")?.state).toBe("key_saved"));
    await user.click(await within(grokItem).findByRole("button", { name: "Remove" }));
    await waitFor(() => expect(client.providers.find((p) => p.id === "grok")?.state).toBe("not_configured"));
  });

  it("shows a status dot per provider whose tooltip names the exact state", async () => {
    await openModels();
    const providers = await screen.findByLabelText("Model providers");
    const claudeItem = within(providers).getByText("Claude").closest(".item") as HTMLElement;
    expect(within(claudeItem).getByTitle("Connected.")).toBeInTheDocument();
    const chatgptItem = within(providers).getByText("ChatGPT").closest(".item") as HTMLElement;
    expect(within(chatgptItem).getByTitle("Not signed in", { exact: true })).toBeInTheDocument();
  });

  it("reconnects a provider from its ⋮ menu, clearing cached state and re-probing", async () => {
    const { client, user } = await openModels();
    const providers = await screen.findByLabelText("Model providers");
    const claudeItem = within(providers).getByText("Claude").closest(".item") as HTMLElement;
    await user.click(within(claudeItem).getByRole("button", { name: "Claude options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Reconnect" }));
    await waitFor(() => expect(client.testResults.has("claude")).toBe(false));
  });

  it("reconnecting a key-based provider clears the saved key so it prompts again", async () => {
    const { client, user } = await openModels();
    const providers = await screen.findByLabelText("Model providers");
    const grokItem = within(providers).getByText("Grok").closest(".item") as HTMLElement;
    await user.type(within(grokItem).getByPlaceholderText("Paste a key"), "xai-test-9999");
    await user.click(within(grokItem).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(client.providers.find((p) => p.id === "grok")?.state).toBe("key_saved"));
    await user.click(within(grokItem).getByRole("button", { name: "Grok options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Reconnect" }));
    await waitFor(() => expect(client.providers.find((p) => p.id === "grok")?.state).toBe("not_configured"));
  });
});
