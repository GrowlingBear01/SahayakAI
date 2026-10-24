import { describe, expect, it } from "vitest";
import { isActiveTask } from "../utils/messages.js";

describe("frontend state guards", () => {
  it("does not treat terminal states as active tasks", () => {
    expect(isActiveTask("waiting_for_approval")).toBe(true);
    expect(isActiveTask("working")).toBe(true);
    expect(isActiveTask("done")).toBe(false);
    expect(isActiveTask("stopped")).toBe(false);
    expect(isActiveTask("could_not_finish")).toBe(false);
    expect(isActiveTask("outcome_unknown")).toBe(false);
  });
});
