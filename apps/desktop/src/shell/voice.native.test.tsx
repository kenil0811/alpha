/** Inside Tauri, `useSpeech` drives the native host (`stt_start`/`stt_stop`) instead of the
 *  browser's absent `SpeechRecognition` — WKWebView offers neither. */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../core/session", () => ({ hasTauri: () => true }));
const invoke = vi.fn().mockResolvedValue(undefined);
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...args: unknown[]) => invoke(...args) }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn().mockResolvedValue(() => undefined) }));

import { useSpeech } from "./voice";

describe("native speech under Tauri", () => {
  it("reports supported without a browser SpeechRecognition, and starts the host listener", async () => {
    const onText = vi.fn();
    const { result } = renderHook(() => useSpeech(onText));
    expect(result.current.supported).toBe(true);
    await act(async () => {
      result.current.start();
    });
    expect(invoke).toHaveBeenCalledWith("stt_start");
    await act(async () => {
      result.current.stop();
    });
    expect(invoke).toHaveBeenCalledWith("stt_stop");
  });
});
