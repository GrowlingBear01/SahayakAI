const DEFAULT_BASE = "http://localhost:8000";
const APPROVAL_TIMEOUT_MS = 150000;

export class ApiError extends Error {
  constructor(code, status, detail) {
    super(code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

export function getApiBase() {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (raw === "") return "";
  if (raw) return String(raw).replace(/\/$/, "");
  if (import.meta.env.DEV) return "";
  return DEFAULT_BASE;
}

export function eventsUrl(taskId) {
  return `${getApiBase()}/tasks/${encodeURIComponent(taskId)}/events`;
}

async function request(path, { method = "GET", body, timeoutMs = 15000 } = {}) {
  const url = `${getApiBase()}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        throw new ApiError("malformed_response", response.status, text.slice(0, 200));
      }
    }

    if (!response.ok) {
      throw new ApiError("http_error", response.status, data);
    }

    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error?.name === "AbortError") throw new ApiError("timeout", 0, null);
    throw new ApiError("network", 0, error?.message || "network");
  } finally {
    clearTimeout(timer);
  }
}

export function isHealthy(payload) {
  if (!payload || typeof payload !== "object") return false;
  return payload.ok === true || payload.status === "ok";
}

export const api = {
  health() {
    return request("/health");
  },

  flows() {
    return request("/flows");
  },

  createTask(text, lang) {
    return request("/tasks", { method: "POST", body: { text, lang } });
  },

  getTask(taskId) {
    return request(`/tasks/${encodeURIComponent(taskId)}`);
  },

  answer(taskId, text) {
    return request(`/tasks/${encodeURIComponent(taskId)}/answer`, {
      method: "POST",
      body: { text },
    });
  },

  approve(taskId, approvalId, edits = null) {
    return request(`/tasks/${encodeURIComponent(taskId)}/approve`, {
      method: "POST",
      body: { approval_id: approvalId, edits },
      timeoutMs: APPROVAL_TIMEOUT_MS,
    });
  },

  cancel(taskId) {
    return request(`/tasks/${encodeURIComponent(taskId)}/cancel`, {
      method: "POST",
    });
  },

  stop(taskId) {
    return request(`/tasks/${encodeURIComponent(taskId)}/stop`, {
      method: "POST",
    });
  },
};
