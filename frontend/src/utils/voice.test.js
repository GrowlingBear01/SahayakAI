import { afterEach, describe, expect, it, vi } from "vitest";
import {
  isVoiceSendCommand,
  recognitionErrorKey,
  resetVoiceSilenceTimer,
  VOICE_SILENCE_TIMEOUT_MS,
} from "./voice.js";

afterEach(() => {
  vi.useRealTimers();
});

describe("speech silence timeout", () => {
  it("waits three seconds and restarts the timeout after new speech", () => {
    vi.useFakeTimers();
    const timerRef = { current: null };
    const onSilence = vi.fn();

    resetVoiceSilenceTimer(timerRef, onSilence);
    vi.advanceTimersByTime(VOICE_SILENCE_TIMEOUT_MS - 1);
    expect(onSilence).not.toHaveBeenCalled();

    resetVoiceSilenceTimer(timerRef, onSilence);
    vi.advanceTimersByTime(VOICE_SILENCE_TIMEOUT_MS - 1);
    expect(onSilence).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onSilence).toHaveBeenCalledOnce();
  });
});

describe("voice confirmation commands", () => {
  it.each(["send", "Send it.", "submit request", "bhej do", "भेजो।", "जमा करें"])(
    "recognizes %s as an explicit send command",
    (text) => {
      expect(isVoiceSendCommand(text)).toBe(true);
    },
  );

  it.each(["send me information", "please submit details", "भेजो जानकारी"])(
    "does not treat %s as a send command",
    (text) => {
      expect(isVoiceSendCommand(text)).toBe(false);
    },
  );
});

describe("speech recognition errors", () => {
  it.each([
    ["no-speech", "micNoSpeech"],
    ["network", "micNetworkError"],
    ["audio-capture", "micCaptureError"],
    ["not-allowed", "micDenied"],
    ["unknown", "micRecognitionError"],
  ])("maps %s to %s", (error, messageKey) => {
    expect(recognitionErrorKey(error)).toBe(messageKey);
  });
});
