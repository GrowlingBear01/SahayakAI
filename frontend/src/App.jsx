import { useEffect, useRef, useState } from "react";
import ApprovalCard from "./components/ApprovalCard.jsx";
import Composer from "./components/Composer.jsx";
import ConversationPanel from "./components/ConversationPanel.jsx";
import Header from "./components/Header.jsx";
import LanguageSelector from "./components/LanguageSelector.jsx";
import LiveBrowserView from "./components/LiveBrowserView.jsx";
import ResultCard from "./components/ResultCard.jsx";
import TaskProgress from "./components/TaskProgress.jsx";
import Toast from "./components/Toast.jsx";
import VoiceControls from "./components/VoiceControls.jsx";
import VoiceOrb from "./components/VoiceOrb.jsx";
import { useAssistant } from "./hooks/useAssistant.js";
import { browserPrefersHindi, isActiveTask, t } from "./utils/messages.js";

function statusLabel(assistant) {
  if (assistant.voice.listening) return t("listening", assistant.language);
  if (assistant.orbState === "working") return t("working", assistant.language);
  if (assistant.voice.speaking) return t("speaking", assistant.language);
  if (assistant.orbState === "processing") return t("processing", assistant.language);
  return t("idle", assistant.language);
}

export default function App() {
  const assistant = useAssistant();
  const [voiceExpanded, setVoiceExpanded] = useState(false);
  const composerRef = useRef(null);
  const voiceToggleRef = useRef(null);
  const exitVoiceRef = useRef(null);
  const voiceExpandedBefore = useRef(false);
  const {
    language,
    flow,
    voice,
    taskState,
    connection,
  } = assistant;
  const taskActive = isActiveTask(taskState);
  const autoHint = browserPrefersHindi() ? "autoLangHi" : "autoLangEn";
  const connected = connection === "ok" || connection === "live";
  const connectionLabel = connected
    ? "connected"
    : connection === "checking"
      ? "backendStatus"
      : "notConnected";

  useEffect(() => {
    if (!voiceExpanded) return undefined;
    const frame = window.requestAnimationFrame(() => exitVoiceRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [voiceExpanded]);

  useEffect(() => {
    if (voiceExpanded) {
      voiceExpandedBefore.current = true;
      return undefined;
    }
    if (voiceExpandedBefore.current) {
      voiceToggleRef.current?.focus();
      voiceExpandedBefore.current = false;
    }
    return undefined;
  }, [voiceExpanded]);

  useEffect(() => {
    if (!voiceExpanded) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") setVoiceExpanded(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [voiceExpanded]);

  const stage = (
    <section
      className={`panel stage${voiceExpanded ? " stage-expanded" : ""}`}
      role={voiceExpanded ? "dialog" : undefined}
      aria-modal={voiceExpanded ? "true" : undefined}
      aria-label={voiceExpanded ? t("fullScreenVoice", language) : undefined}
      onKeyDown={(event) => {
        if (!voiceExpanded || event.key !== "Tab") return;
        const focusable = Array.from(
          event.currentTarget.querySelectorAll("button:not(:disabled), select, input:not(:disabled)"),
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
    >
      <div className="stage-topline">
        <span className="stage-mode">{t("voiceWorkspace", language)}</span>
        <span className={`flow-tag ${flow}`}>{t(flow === "demo" ? "demo" : "discovery", language)}</span>
      </div>
      <div className="stage-heading">
        <p className="eyebrow">{t("heroEyebrow", language)}</p>
        <h2>{t("heroTitle", language)}</h2>
        <p className="stage-copy">{t("welcome", language)}</p>
      </div>
      <p className="status-chip">
        <span className={`status-dot ${assistant.orbState}`} />
        {statusLabel(assistant)}
      </p>
      <VoiceOrb state={assistant.orbState} />
      <div className="language-control">
        <p className="eyebrow language-label">{t("language", language)}</p>
        <LanguageSelector language={language} onChange={assistant.setLanguage} />
      </div>
      {language === "auto" ? <p className="muted">{t(autoHint, language)}</p> : null}
      {assistant.voiceError ? (
        <p className="notice">{t(assistant.voiceError, language)}</p>
      ) : null}
      {!voice.support.speech ? (
        <p className="muted">{t("speechUnsupported", language)}</p>
      ) : null}
      <div className="voice-disclaimer">{t("micPrivacy", language)}</div>
      <VoiceControls
        language={language}
        listening={voice.listening}
        speaking={voice.speaking}
        recognitionSupported={voice.support.recognition}
        taskActive={taskActive}
        onMic={voice.startListening}
        onStopListen={voice.stopListening}
        onInterrupt={voice.stopSpeech}
        onReplay={assistant.replay}
        onStopTask={assistant.stopTask}
      />
      {voiceExpanded ? (
        <button
          type="button"
          className="ghost close-fullscreen"
          ref={exitVoiceRef}
          onClick={() => setVoiceExpanded(false)}
        >
          {t("exitFullScreen", language)}
        </button>
      ) : null}
    </section>
  );

  return (
    <div className={`app-shell${voiceExpanded ? " has-expanded-voice" : ""}`}>
      <div className="live-region" aria-live="polite">
        {statusLabel(assistant)} {assistant.assistantText}
      </div>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">स</span>
          <div className="brand-copy">
            <h1>SahayakAI</h1>
            <span>{t("voiceWorkspace", language)}</span>
          </div>
        </div>
        <button
          type="button"
          className="new-conversation"
          onClick={assistant.newConversation}
        >
          <span aria-hidden="true">＋</span>
          {t("newConversation", language)}
        </button>
        <div className="sidebar-section-label">{t("workspace", language)}</div>
        <div className="sidebar-current" aria-current="page">
          <span aria-hidden="true">◖</span>
          {t("voiceStudio", language)}
        </div>
        <div className="sidebar-foot">
          <span className={`connection-dot ${connection}`} />
          <span>{t(connectionLabel, language)}</span>
        </div>
      </aside>

      <main className="main-area">
        <Header
          language={language}
          onLanguage={assistant.setLanguage}
          flow={flow}
          onFlow={assistant.setFlow}
          connection={connection}
          onExpandVoice={() => setVoiceExpanded(true)}
          voiceToggleRef={voiceToggleRef}
        />
        {connection === "unavailable" ? (
          <p className="notice backend-notice">{t("backendDown", language)}</p>
        ) : null}
        <div className="studio-grid">
          {stage}
          <ConversationPanel
            language={language}
            flow={flow}
            request={assistant.userUtterance}
            transcript={assistant.transcript}
            answer={assistant.assistantText}
            progress={assistant.progress}
            taskState={taskState}
            composerRef={composerRef}
            onSubmit={assistant.startTask}
            typed={assistant.typed}
            onTypedChange={assistant.setTyped}
            disabled={assistant.busy && taskState !== "needs_info" && !assistant.approval}
            onSuggestion={(item) => {
              assistant.setFlow(item.flow);
              assistant.setTyped(item.text[language === "hi" ? "hi" : "en"]);
            }}
            onToast={assistant.setToast}
            onStopTask={assistant.stopTask}
          />
        </div>
        <div className="supplemental-grid">
          <LiveBrowserView
            language={language}
            url={assistant.streamingUrl}
            active={taskActive || Boolean(assistant.streamingUrl)}
          />
          <ApprovalCard
            language={language}
            approval={assistant.approval}
            taskValues={assistant.task?.values}
            busy={assistant.approvalBusy}
            flowMismatch={assistant.flowMismatch}
            onApprove={() => assistant.approve(null)}
            onEdit={(edits) => assistant.approve(edits)}
            onCancel={assistant.cancelApproval}
            onSwitchToFlow={assistant.setFlow}
          />
          <ResultCard
            language={language}
            result={assistant.result}
            flow={flow}
            onSwitchToDemo={() => assistant.setFlow("demo")}
          />
        </div>
        <TaskProgress
          language={language}
          request={assistant.userUtterance}
          taskState={taskState}
          progress={assistant.progress}
          onStop={assistant.stopTask}
        />
      </main>
      {voiceExpanded ? <div className="fullscreen-backdrop" aria-hidden="true" /> : null}
      <Toast
        toast={assistant.toast}
        language={language}
        onDismiss={() => assistant.setToast(null)}
      />
    </div>
  );
}
