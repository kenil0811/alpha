/** "Speak replies" defaults on and persists the person's choice. */
import { beforeEach, describe, expect, it } from "vitest";
import { setSpeakEnabled, speakEnabled } from "./tts";

beforeEach(() => {
  window.localStorage.clear();
});

describe("speak replies toggle", () => {
  it("defaults to on", () => {
    expect(speakEnabled()).toBe(true);
  });

  it("persists off, then on again", () => {
    setSpeakEnabled(false);
    expect(speakEnabled()).toBe(false);
    setSpeakEnabled(true);
    expect(speakEnabled()).toBe(true);
  });
});
