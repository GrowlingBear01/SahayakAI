import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, isHealthy } from "../services/api.js";
import { eventKey, fieldsWithKeys, isHttpUrl } from "../utils/approval.js";
import {
  TERMINAL_STATES,
  eventMessage,
  isActiveTask,
  isStopCommand,
  resolvedLang,
} from "../utils/messages.js";
import { useTaskEvents } from "./useTaskEvents.js";
import { useVoice } from "./useVoice.js";

function extractStreamingUrl(data) {
  const candidate = data?.streaming_url || data?.live_url || data?.browser_url;
  return isHttpUrl(candidate) ? candidate : null;
}

function approvalFromEvent(event) {
  const data = event?.data || {};
  if (!data.approval_id) return null;
  return data;
}

function resultFromEvent(event) {
  if (!TERMINAL_STATES.has(event?.state)) return null;
  const data = event.data || {};
  return {
    state: event.state,
    evidence: data.evidence || null,
    summary_en: data.summary_en || event.message_en,
    summary_hi: data.summary_hi || event.message_hi,
    reason: data.reason || null,
    needs_human_kind: data.needs_human_kind || null,
    note: data.note || null,
    links: data.links || data.official_links || [],
  };
}

export function useAssistant() {
  const [language, setLanguage] = useState("en");
  const [flow, setFlow] = useState("demo");
  const [typed, setTyped] = useState("");
  const [transcript, setTranscript] = useState("");
  const [userUtterance, setUserUtterance] = useState("");
  const [assistantText, setAssistantText] = useState("");
  const [taskId, setTaskId] = useState(null);
  const [task, setTask] = useState(null);
  const [taskState, setTaskState] = useState(null);
  const [progress, setProgress] = useState([]);
  const [approval, setApproval] = useState(null);
  const [streamingUrl, setStreamingUrl] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [connection, setConnection] = useState("checking");
  const [toast, setToast] = useState(null);
  const [health, setHealth] = useState(null);
  const [flows, setFlows] = useState([]);
  const [flowMismatch, setFlowMismatch] = useState(false);
  const [voiceError, setVoiceError] = useState(null);
  const [lastEvent, setLastEvent] = useState(null);

  const spokenKeys = useRef(new Set());
  const inFlight = useRef(false);
  const approvalLock = useRef(null);
  const taskIdRef = useRef(null);
  const taskStateRef = useRef(null);
  const flowRef = useRef(flow);
  const languageRef = useRef(language);
  const speakRef = useRef(() => {});
  const stopTaskRef = useRef(async () => {});

  taskIdRef.current = taskId;
  taskStateRef.current = taskState;
  flowRef.current = flow;
  languageRef.current = language;

  const applyEvent = useCallback((event) => {
    if (!event || (taskIdRef.current && event.task_id && event.task_id !== taskIdRef.current)) {
      return;
    }
    const lang = languageRef.current;
    setLastEvent(event);
    setTaskState(event.state);
    setConnection("live");
    const text = eventMessage(event, lang);
    setAssistantText(text);

    const url = extractStreamingUrl(event.data);
    if (url) setStreamingUrl(url);

    setProgress((current) => [...current, event].slice(-12));

    if (event.state === "waiting_for_approval") {
      const nextApproval = approvalFromEvent(event);
      setApproval(nextApproval);
      if (nextApproval?.site_kind === "demo" && flowRef.current === "discovery") {
        setFlowMismatch(true);
      }
      const fields = fieldsWithKeys(nextApproval, {});
      const readback =
        resolvedLang(lang) === "hi"
          ? nextApproval?.read_back_hi || text
          : nextApproval?.read_back_en || text;
      const values = fields
        .map((field) => `${field.label_en || field.label_hi}: ${field.value}`)
        .join(". ");
      const key = eventKey(event);
      if (key && !spokenKeys.current.has(key)) {
        spokenKeys.current.add(key);
        speakRef.current(`${readback} ${values}`, { lang, key });
      }
    } else {
      setApproval(null);
      const key = eventKey(event);
      if (text && key && !spokenKeys.current.has(key)) {
        spokenKeys.current.add(key);
        speakRef.current(text, { lang, key });
      }
    }

    const nextResult = resultFromEvent(event);
    if (nextResult) {
      setResult(nextResult);
      setBusy(false);
      inFlight.current = false;
    }
  }, []);

  const voice = useVoice({
    language,
    onInterim: setTranscript,
    onFinal: (text) => {
      setTranscript(text);
      setTyped(text);
      if (isStopCommand(text) && taskIdRef.current && isActiveTask(taskStateRef.current)) {
        stopTaskRef.current();
      }
    },
  });

  speakRef.current = voice.speak;

  const refreshHealth = useCallback(async () => {
    try {
      const payload = await api.health();
      const ok = isHealthy(payload);
      setHealth(payload);
      setConnection(ok ? "ok" : "unavailable");
      if (ok) {
        try {
          setFlows(await api.flows());
        } catch {
          setFlows([]);
        }
      }
      return ok;
    } catch {
      setHealth(null);
      setConnection("unavailable");
      return false;
    }
  }, []);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth]);

  useTaskEvents(taskId, {
    enabled: Boolean(taskId) && !TERMINAL_STATES.has(taskState),
    onEvent: applyEvent,
    onError: async (reason) => {
      if (reason === "malformed_event") {
        setToast({ kind: "error", messageKey: "sseLost" });
        return;
      }
      setConnection("disconnected");
      setToast({ kind: "warning", messageKey: "sseLost" });
      if (!taskIdRef.current) return;
      try {
        const snapshot = await api.getTask(taskIdRef.current);
        setTask(snapshot);
        setTaskState(snapshot.state);
        if (TERMINAL_STATES.has(snapshot.state)) {
          setResult({
            state: snapshot.state,
            evidence: snapshot.evidence || null,
            summary_en: snapshot.error || snapshot.state,
            summary_hi: snapshot.error || snapshot.state,
          });
        }
      } catch {
        /* snapshot recovery failed; banner already visible */
      }
    },
  });

  const stopTask = useCallback(async () => {
    if (!taskIdRef.current) return;
    try {
      const response = await api.stop(taskIdRef.current);
      const state = response?.state;
      if (!state) {
        setToast({
          kind: "warning",
          text:
            resolvedLang(languageRef.current) === "hi"
              ? "रोकने का अनुरोध भेजा गया। पुष्टि का इंतज़ार है।"
              : "Stop requested. Waiting for the backend to confirm.",
        });
        return;
      }
      setTaskState(state);
      setResult({
        state,
        evidence: null,
        summary_en: response?.note || "Stopped. Actions already taken may remain.",
        summary_hi: "रोक दिया गया। पहले किए गए काम का असर रह सकता है।",
        note: response?.note || null,
      });
      setApproval(null);
      setBusy(false);
      inFlight.current = false;
    } catch {
      setToast({
        kind: "error",
        text:
          resolvedLang(languageRef.current) === "hi"
            ? "रोकने का अनुरोध भेजा नहीं जा सका।"
            : "The stop request could not be sent.",
      });
    }
  }, []);

  stopTaskRef.current = stopTask;

  const startTask = useCallback(
    async (rawText) => {
      const text = String(rawText || typed || "").trim();
      if (!text || inFlight.current) return;
      if (isStopCommand(text) && taskIdRef.current && isActiveTask(taskStateRef.current)) {
        await stopTask();
        return;
      }

      if (taskIdRef.current && taskStateRef.current === "needs_info") {
        try {
          await api.answer(taskIdRef.current, text);
          setUserUtterance(text);
          setTyped("");
        } catch {
          setToast({ kind: "error", messageKey: "backendDown" });
        }
        return;
      }

      inFlight.current = true;
      setBusy(true);
      setResult(null);
      setApproval(null);
      setProgress([]);
      setStreamingUrl(null);
      setFlowMismatch(false);
      setUserUtterance(text);
      setAssistantText("");
      setTranscript("");
      spokenKeys.current = new Set();
      voice.stopSpeech();

      const lang = language === "auto" ? "auto" : language;
      try {
        const created = await api.createTask(text, lang);
        if (!created?.task_id) throw new Error("missing_task_id");
        setTaskId(created.task_id);
        setTaskState("planning");
        const snapshot = await api.getTask(created.task_id);
        setTask(snapshot);
        setTaskState(snapshot.state);
        setTyped("");
      } catch (error) {
        setBusy(false);
        inFlight.current = false;
        setConnection(
          error?.code === "network" || error?.code === "timeout" ? "unavailable" : "error",
        );
        setToast({ kind: "error", messageKey: "backendDown" });
      }
    },
    [language, stopTask, typed, voice],
  );

  const approve = useCallback(
    async (edits = null) => {
      if (!taskId || !approval?.approval_id) return;
      if (approvalLock.current === approval.approval_id && edits == null) return;
      approvalLock.current = approval.approval_id;
      setApprovalBusy(true);
      const usedId = approval.approval_id;
      try {
        await api.approve(taskId, usedId, edits);
        approvalLock.current = null;
        const snapshot = await api.getTask(taskId);
        setTask(snapshot);
        setTaskState(snapshot.state);
      } catch (error) {
        approvalLock.current = null;
        setToast({
          kind: "error",
          text:
            error?.status === 409
              ? resolvedLang(language) === "hi"
                ? "यह अनुमति अब मान्य नहीं है। नई जाँच का इंतज़ार करें।"
                : "That approval is no longer valid. Wait for a fresh review."
              : resolvedLang(language) === "hi"
                ? "अनुमति भेजना असफल रहा।"
                : "Approval could not be sent.",
        });
      } finally {
        setApprovalBusy(false);
      }
    },
    [approval, language, taskId],
  );

  const cancelApproval = useCallback(async () => {
    if (!taskId) return;
    setApprovalBusy(true);
    try {
      await api.cancel(taskId);
      const snapshot = await api.getTask(taskId);
      setTask(snapshot);
      setTaskState(snapshot.state);
      setApproval(null);
    } catch {
      setToast({ kind: "error", messageKey: "backendDown" });
    } finally {
      setApprovalBusy(false);
      setBusy(false);
      inFlight.current = false;
    }
  }, [taskId]);

  const newConversation = useCallback(() => {
    voice.stopListening();
    voice.stopSpeech();
    inFlight.current = false;
    approvalLock.current = null;
    spokenKeys.current = new Set();
    setTaskId(null);
    setTask(null);
    setTaskState(null);
    setProgress([]);
    setApproval(null);
    setStreamingUrl(null);
    setResult(null);
    setBusy(false);
    setUserUtterance("");
    setAssistantText("");
    setTranscript("");
    setTyped("");
    setFlowMismatch(false);
    setToast(null);
  }, [voice]);

  const orbState = useMemo(() => {
    if (voice.listening) return "listening";
    if (taskState === "working" || taskState === "submitting" || taskState === "planning") {
      return "working";
    }
    if (voice.speaking) return "speaking";
    if (busy && !approval) return "processing";
    return "idle";
  }, [approval, busy, taskState, voice.listening, voice.speaking]);

  useEffect(() => {
    if (!voice.support.recognition) setVoiceError("micUnsupported");
    else if (voice.support.permission === "denied") setVoiceError("micDenied");
    else setVoiceError(null);
  }, [voice.support]);

  const replay = useCallback(() => {
    if (!assistantText) return;
    voice.speak(assistantText, { lang: language, key: `replay:${assistantText}` });
  }, [assistantText, language, voice]);

  return {
    language,
    setLanguage,
    flow,
    setFlow,
    typed,
    setTyped,
    transcript,
    userUtterance,
    assistantText,
    taskId,
    task,
    taskState,
    progress,
    approval,
    streamingUrl,
    result,
    busy,
    approvalBusy,
    connection,
    toast,
    setToast,
    health,
    flows,
    flowMismatch,
    voiceError,
    lastEvent,
    voice,
    orbState,
    startTask,
    approve,
    cancelApproval,
    stopTask,
    newConversation,
    refreshHealth,
    replay,
  };
}
