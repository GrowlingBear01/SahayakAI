import { describe, expect, it } from "vitest";
import { parseTaskEvent } from "../hooks/useTaskEvents.js";
import { coerceEdits, eventKey, fieldsWithKeys, isHttpUrl } from "./approval.js";
import { TERMINAL_STATES, isStopCommand } from "./messages.js";

describe("safety helpers", () => {
  it("recognizes stop commands without treating silence as approval", () => {
    expect(isStopCommand("stop")).toBe(true);
    expect(isStopCommand("ruko")).toBe(true);
    expect(isStopCommand("रुको")).toBe(true);
    expect(isStopCommand("")).toBe(false);
    expect(isStopCommand("yes")).toBe(false);
  });

  it("never treats a fake URL as a live browser preview", () => {
    expect(isHttpUrl("javascript:alert(1)")).toBe(false);
    expect(isHttpUrl("not-a-url")).toBe(false);
    expect(isHttpUrl("https://example.test/stream")).toBe(true);
  });

  it("maps approval fields without inventing extra values", () => {
    const fields = fieldsWithKeys(
      {
        fields: [{ label_en: "Full name", label_hi: "पूरा नाम", value: "Savitri Devi" }],
      },
      { full_name: "Savitri Devi" },
    );
    expect(fields[0].key).toBe("full_name");
    expect(coerceEdits(fields, { full_name: "Asha" })).toEqual({ full_name: "Asha" });
  });

  it("keeps the four terminal states distinct", () => {
    expect([...TERMINAL_STATES]).toEqual([
      "done",
      "could_not_finish",
      "stopped",
      "outcome_unknown",
    ]);
  });

  it("rejects malformed SSE payloads", () => {
    expect(parseTaskEvent("{")).toEqual({ ok: false, reason: "malformed_event" });
    expect(parseTaskEvent(JSON.stringify({ task_id: "t", state: "working" })).ok).toBe(true);
  });

  it("dedupes spoken events by identity, not by guessing success", () => {
    const event = { task_id: "t", ts: "1", state: "working", message_en: "Filling", step: 3 };
    expect(eventKey(event)).toBe("t:1:working:Filling:3");
  });
});
