import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, eventsUrl, getApiBase, isHealthy } from "./api.js";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.unstubAllEnvs();
});

describe("api contract", () => {
  it("builds the SSE path from the configured base", () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000");
    expect(eventsUrl("abc")).toBe("http://localhost:8000/tasks/abc/events");
  });

  it("treats both health payload shapes as healthy", () => {
    expect(isHealthy({ ok: true })).toBe(true);
    expect(isHealthy({ status: "ok" })).toBe(true);
    expect(isHealthy({ ok: false })).toBe(false);
  });

  it("POSTs { text, lang, flow } to /tasks", async () => {
    globalThis.fetch = vi.fn(async (url, options) => {
      expect(String(url)).toMatch(/\/tasks$/);
      expect(options.method).toBe("POST");
      expect(JSON.parse(options.body)).toEqual({
        text: "Fill the demo form",
        lang: "en",
        flow: "auto",
      });
      return new Response(JSON.stringify({ task_id: "t1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    const result = await api.createTask("Fill the demo form", "en");
    expect(result).toEqual({ task_id: "t1" });
  });

  it("sends the selected public website mode", async () => {
    globalThis.fetch = vi.fn(async (_url, options) => {
      expect(JSON.parse(options.body)).toEqual({
        text: "National Scholarship Portal",
        lang: "en",
        flow: "web",
      });
      return new Response(JSON.stringify({ task_id: "t2" }), { status: 200 });
    });
    await api.createTask("National Scholarship Portal", "en", "web");
  });

  it("sends approval_id and edits exactly", async () => {
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout");
    globalThis.fetch = vi.fn(async (url, options) => {
      expect(String(url)).toMatch(/\/tasks\/t1\/approve$/);
      expect(JSON.parse(options.body)).toEqual({
        approval_id: "appr-1",
        edits: { age: 73 },
      });
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    try {
      await api.approve("t1", "appr-1", { age: 73 });
      expect(timeoutSpy).toHaveBeenCalledWith(expect.any(Function), 150000);
    } finally {
      timeoutSpy.mockRestore();
    }
  });

  it("does not invent a successful task payload on HTTP errors", async () => {
    globalThis.fetch = vi.fn(async () => new Response("nope", { status: 500 }));
    await expect(api.getTask("t1")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getApiBase", () => {
  it("uses an empty base when the env is an empty string", () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    expect(getApiBase()).toBe("");
  });
});
