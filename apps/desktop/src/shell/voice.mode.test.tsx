/** The "Transcription" setting (Settings -> Desktop): which way `useSpeech` listens. Saved in
 *  localStorage like the other per-window voice settings (push-to-talk, speak replies). */
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../core/session", () => ({
  hasTauri: () => false,
  resolveSession: vi.fn().mockResolvedValue({ kind: "unavailable", reason: "test" }),
}));

import { readTranscriptionMode, useSpeech, writeTranscriptionMode } from "./voice";

afterEach(() => {
  window.localStorage.removeItem("alpha.transcription.mode");
});

describe("transcription mode", () => {
  it("defaults to automatic and round-trips through localStorage", () => {
    expect(readTranscriptionMode()).toBe("automatic");
    writeTranscriptionMode("groq");
    expect(readTranscriptionMode()).toBe("groq");
    writeTranscriptionMode("openai");
    expect(readTranscriptionMode()).toBe("openai");
  });

  it("ignores a corrupted stored value and falls back to automatic", () => {
    window.localStorage.setItem("alpha.transcription.mode", "not-a-real-mode");
    expect(readTranscriptionMode()).toBe("automatic");
  });

  it("an explicit Groq or OpenAI choice returns the cloud hook's shape without throwing", () => {
    writeTranscriptionMode("groq");
    const { result } = renderHook(() => useSpeech(vi.fn()));
    expect(result.current).toMatchObject({ listening: false, error: null });
    expect(typeof result.current.toggle).toBe("function");
  });
});
