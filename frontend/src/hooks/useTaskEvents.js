import { useEffect, useRef } from "react";
import { eventsUrl } from "../services/api.js";
import { TERMINAL_STATES } from "../utils/messages.js";

export function parseTaskEvent(raw) {
  if (raw == null || raw === "") return { ok: false, reason: "empty" };
  try {
    const data = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!data || typeof data !== "object") return { ok: false, reason: "malformed_event" };
    if (!data.state || !data.task_id) return { ok: false, reason: "malformed_event" };
    return { ok: true, event: data };
  } catch {
    return { ok: false, reason: "malformed_event" };
  }
}

export function useTaskEvents(taskId, { onEvent, onError, enabled = true } = {}) {
  const onEventRef = useRef(onEvent);
  const onErrorRef = useRef(onError);
  onEventRef.current = onEvent;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!enabled || !taskId || typeof EventSource === "undefined") return undefined;

    let closed = false;
    let source;
    try {
      source = new EventSource(eventsUrl(taskId));
    } catch (error) {
      onErrorRef.current?.("sse_unavailable", error);
      return undefined;
    }

    source.onmessage = (message) => {
      if (closed) return;
      const parsed = parseTaskEvent(message.data);
      if (!parsed.ok) {
        onErrorRef.current?.(parsed.reason);
        return;
      }
      onEventRef.current?.(parsed.event);
      if (TERMINAL_STATES.has(parsed.event.state)) {
        closed = true;
        source.close();
      }
    };

    source.onerror = () => {
      if (closed) return;
      onErrorRef.current?.("sse_disconnected");
    };

    return () => {
      closed = true;
      source.close();
    };
  }, [taskId, enabled]);
}
