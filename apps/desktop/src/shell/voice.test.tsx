/** Speaking into the assistant: one click listens and shows it, words land in the field, the
 *  next click stops. */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";

class FakeRecognition {
  static live: FakeRecognition | null = null;
  continuous = false;
  interimResults = false;
  lang = "";
  onresult: ((e: { resultIndex: number; results: { isFinal: boolean; 0: { transcript: string } }[] }) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((e: { error?: string }) => void) | null = null;
  started = false;
  stopped = false;
  start() {
    this.started = true;
    FakeRecognition.live = this;
  }
  stop() {
    this.stopped = true;
    this.onend?.();
  }
}

afterEach(() => {
  delete (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;
  FakeRecognition.live = null;
});

describe("speaking instead of typing", () => {
  it("listens on one click, shows it, fills the field as words arrive and stops on the next click", async () => {
    (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition = FakeRecognition;
    const user = userEvent.setup();
    render(<App client={new FakeWorkflowsClient()} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    const mic = screen.getByRole("button", { name: "Speak" });
    await user.click(mic);
    const live = screen.getByRole("button", { name: "Stop listening" });
    expect(live).toHaveAttribute("aria-pressed", "true");
    expect(live).toHaveTextContent("Listening");
    expect(FakeRecognition.live?.started).toBe(true);
    expect(FakeRecognition.live?.continuous).toBe(true);
    act(() => {
      FakeRecognition.live?.onresult?.({ resultIndex: 0, results: [{ isFinal: false, 0: { transcript: "track my" } }] });
    });
    expect(screen.getByLabelText("What do you want done?")).toHaveValue("track my");
    act(() => {
      FakeRecognition.live?.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: "track my reading" } }] });
    });
    expect(screen.getByLabelText("What do you want done?")).toHaveValue("track my reading");
    await user.click(live);
    expect(FakeRecognition.live?.stopped).toBe(true);
    expect(screen.getByRole("button", { name: "Speak" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText("What do you want done?")).toHaveValue("track my reading");
  });

  it("is greyed out with a hint when the window cannot listen", async () => {
    render(<App client={new FakeWorkflowsClient()} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    const mic = screen.getByRole("button", { name: "Speak" });
    expect(mic).toBeDisabled();
    expect(mic).toHaveAttribute("title", expect.stringContaining("dictation"));
  });
});
