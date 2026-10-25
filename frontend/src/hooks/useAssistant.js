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
import { isVoiceSendCommand } from "../utils/voice.js";
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
    human_action_url: data.human_action_url || null,
    note: data.note || null,
    links: data.links || data.official_links || [],
    flow_id: data.flow_id || null,
    schemes: Array.isArray(data.schemes) ? data.schemes : [],
    web_answer: data.web_answer || null,
    web_sources: Array.isArray(data.web_sources) ? data.web_sources : [],
    web_media: Array.isArray(data.web_media) ? data.web_media : [],
    selected_site: data.selected_site || null,
    offer_demo: data.offer_demo === true,
  };
}

export function useAssistant() {
  const [language, setLanguage] = useState("en");
  const [flow, setFlow] = useState("auto");
  const [conversationHistory, setConversationHistory] = useState([]);
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
  const [liveBrowserAction, setLiveBrowserAction] = useState(null);
  const [browserStarted, setBrowserStarted] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [connection, setConnection] = useState("checking");
  const [toast, setToast] = useState(null);
  const [health, setHealth] = useState(null);
  const [flows, setFlows] = useState([]);
  const [flowMismatch, setFlowMismatch] = useState(false);
  const [voiceError, setVoiceError] = useState(null);
  const [voiceDraftPending, setVoiceDraftPending] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);

  const spokenKeys = useRef(new Set());
  const inFlight = useRef(false);
  const answering = useRef(false);
  const approvalLock = useRef(null);
  const taskIdRef = useRef(null);
  const taskStateRef = useRef(null);
  const conversationHistoryRef = useRef([]);
  const activeTaskTurnsRef = useRef([]);
  const userUtteranceRef = useRef("");
  const recordedTasksRef = useRef(new Set());
  const typedRef = useRef(typed);
  const voiceDraftPendingRef = useRef(false);
  const voiceDraftTextRef = useRef("");
  const startTaskRef = useRef(async () => {});
  const flowRef = useRef(flow);
  const languageRef = useRef(language);
  const speakRef = useRef(() => {});
  const stopTaskRef = useRef(async () => {});

  taskIdRef.current = taskId;
  taskStateRef.current = taskState;
  typedRef.current = typed;
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
    if (event.state === "needs_info") {
      setBusy(false);
      inFlight.current = false;
    }

    const url = extractStreamingUrl(event.data);
    if (url) {
      setStreamingUrl(url);
      setBrowserStarted(true);
    }
    if (event.data?.browser_started === true) setBrowserStarted(true);
    if (typeof event.data?.action === "string" && event.data.action.trim()) {
      setLiveBrowserAction(event.data.action.trim());
    }

    setProgress((current) => [...current, event].slice(-12));

    if (event.state === "waiting_for_approval") {
      const nextApproval = approvalFromEvent(event);
      setApproval(nextApproval);
      const selectedSite =
        flowRef.current === "demo"
          ? "demo"
          : flowRef.current === "web" || flowRef.current === "discovery"
            ? "real"
            : null;
      setFlowMismatch(
        Boolean(
          selectedSite &&
            nextApproval?.site_kind &&
            nextApproval.site_kind !== selectedSite,
        ),
      );
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
      if (
        !recordedTasksRef.current.has(event.task_id) &&
        userUtteranceRef.current.trim()
      ) {
        recordedTasksRef.current.add(event.task_id);
        const answer =
          nextResult.web_answer ||
          (lang === "hi" ? nextResult.summary_hi : nextResult.summary_en) ||
          text;
        const nextHistory = [
          ...conversationHistoryRef.current,
          ...activeTaskTurnsRef.current,
          { role: "assistant", text: answer.slice(0, 2000) },
        ].slice(-12);
        conversationHistoryRef.current = nextHistory;
        setConversationHistory(nextHistory);
        activeTaskTurnsRef.current = [];
      }
    }
  }, []);

  const updateTyped = useCallback((value) => {
    const text = String(value ?? "");
    typedRef.current = text;
    setTyped(text);
  }, []);

  const voice = useVoice({
    language,
    onInterim: setTranscript,
    onFinal: (text) => {
      if (
        voiceDraftPendingRef.current &&
        isVoiceSendCommand(text) &&
        typedRef.current.trim()
      ) {
        const request = typedRef.current.trim();
        voiceDraftPendingRef.current = false;
        setVoiceDraftPending(false);
        setTranscript(voiceDraftTextRef.current);
        startTaskRef.current(request);
        return;
      }

      setTranscript(text);
      updateTyped(text);
      if (isStopCommand(text) && taskIdRef.current && isActiveTask(taskStateRef.current)) {
        voiceDraftPendingRef.current = false;
        setVoiceDraftPending(false);
        stopTaskRef.current();
        return;
      }
      voiceDraftTextRef.current = text;
      voiceDraftPendingRef.current = true;
      setVoiceDraftPending(true);
      speakRef.current(text, {
        lang: languageRef.current,
        key: `voice-review:${Date.now()}`,
      });
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

  useEffect(() => {
    if (!approval?.site_kind) {
      setFlowMismatch(false);
      return;
    }
    if (flow === "auto") {
      setFlowMismatch(false);
      return;
    }
    const selectedSite = flow === "demo" ? "demo" : "real";
    setFlowMismatch(Boolean(approval.site_kind && approval.site_kind !== selectedSite));
  }, [approval, flow]);

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
            summary_hi: snapshot.error_hi || snapshot.error || snapshot.state,
            reason: snapshot.reason || null,
            needs_human_kind: snapshot.needs_human_kind || null,
            human_action_url: snapshot.human_action_url || null,
            flow_id: snapshot.flow_id || null,
            schemes: Array.isArray(snapshot.schemes) ? snapshot.schemes : [],
            web_answer: snapshot.web_answer || null,
            web_sources: Array.isArray(snapshot.web_sources)
              ? snapshot.web_sources
              : [],
            web_media: Array.isArray(snapshot.web_media)
              ? snapshot.web_media
              : [],
            selected_site: snapshot.selected_site || null,
            offer_demo:
              snapshot.flow_id === "myscheme_discovery" &&
              ["could_not_finish", "outcome_unknown"].includes(snapshot.state),
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
      if (!TERMINAL_STATES.has(state)) {
        setTaskState(state);
        setToast({
          kind: "warning",
          text: response.note_en || response.note || "Stop requested. Waiting for verified status.",
        });
        return;
      }
      setTaskState(state);
      setResult({
        state,
        evidence: response.evidence || null,
        summary_en:
          response.summary_en ||
          response.note_en ||
          response.note ||
          "Stopped. Actions already taken may remain.",
        summary_hi:
          response.summary_hi ||
          response.note_hi ||
          "रोक दिया गया। पहले किए गए काम का असर रह सकता है।",
        reason: response.reason || null,
        needs_human_kind: response.needs_human_kind || null,
        human_action_url: response.human_action_url || null,
        flow_id: response.flow_id || null,
        schemes: Array.isArray(response.schemes) ? response.schemes : [],
        web_answer: response.web_answer || null,
        web_sources: Array.isArray(response.web_sources)
          ? response.web_sources
          : [],
        web_media: Array.isArray(response.web_media) ? response.web_media : [],
        selected_site: response.selected_site || null,
        offer_demo: response.offer_demo === true,
        note: response.note_key || null,
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
      if (!text) return;
      if (isStopCommand(text) && taskIdRef.current && isActiveTask(taskStateRef.current)) {
        await stopTask();
        return;
      }
      voiceDraftPendingRef.current = false;
      setVoiceDraftPending(false);

      if (taskIdRef.current && taskStateRef.current === "needs_info") {
        if (answering.current) return;
        answering.current = true;
        activeTaskTurnsRef.current = [
          ...activeTaskTurnsRef.current,
          { role: "user", text },
        ].slice(-11);
        setTaskState("planning");
        try {
          await api.answer(taskIdRef.current, text);
          setUserUtterance(text);
          updateTyped("");
        } catch {
          setTaskState("needs_info");
          setToast({ kind: "error", messageKey: "backendDown" });
        } finally {
          answering.current = false;
        }
        return;
      }

      if (inFlight.current) return;
      inFlight.current = true;
      setBusy(true);
      setResult(null);
      setApproval(null);
      setProgress([]);
      setStreamingUrl(null);
      setLiveBrowserAction(null);
      setBrowserStarted(false);
      setFlowMismatch(false);
      setUserUtterance(text);
      userUtteranceRef.current = text;
      activeTaskTurnsRef.current = [{ role: "user", text }];
      setAssistantText("");
      setTranscript("");
      spokenKeys.current = new Set();
      voice.stopSpeech();

      const lang = language === "auto" ? "auto" : language;
      try {
        const created = await api.createTask(
          text,
          lang,
          flowRef.current,
          conversationHistoryRef.current,
        );
        if (!created?.task_id) throw new Error("missing_task_id");
        setTaskId(created.task_id);
        setTaskState("planning");
        const snapshot = await api.getTask(created.task_id);
        setTask(snapshot);
        setTaskState(snapshot.state);
        updateTyped("");
      } catch (error) {
        setBusy(false);
        inFlight.current = false;
        setConnection(
          error?.code === "network" || error?.code === "timeout" ? "unavailable" : "error",
        );
        setToast({ kind: "error", messageKey: "backendDown" });
      }
    },
    [language, stopTask, typed, updateTyped, voice],
  );
  startTaskRef.current = startTask;

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
        answering.current = false;
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
    setLiveBrowserAction(null);
    setBrowserStarted(false);
    setResult(null);
    setBusy(false);
    setUserUtterance("");
    userUtteranceRef.current = "";
    setAssistantText("");
    setTranscript("");
    updateTyped("");
    voiceDraftPendingRef.current = false;
    voiceDraftTextRef.current = "";
    setVoiceDraftPending(false);
    setFlowMismatch(false);
    conversationHistoryRef.current = [];
    activeTaskTurnsRef.current = [];
    recordedTasksRef.current = new Set();
    setConversationHistory([]);
    setToast(null);
  }, [updateTyped, voice]);

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
    else if (voice.recognitionError) setVoiceError(voice.recognitionError);
    else setVoiceError(null);
  }, [voice.recognitionError, voice.support]);

  const replay = useCallback(() => {
    if (!assistantText) return;
    voice.speak(assistantText, { lang: language, key: `replay:${assistantText}` });
  }, [assistantText, language, voice]);

  return {
    language,
    setLanguage,
    flow,
    setFlow,
    conversationHistory,
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
    liveBrowserAction,
    browserStarted,
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
    voiceDraftPending,
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
