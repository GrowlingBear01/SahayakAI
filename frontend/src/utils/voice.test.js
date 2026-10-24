import { describe, expect, it } from "vitest";
import { isVoiceSendCommand } from "./voice.js";

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
