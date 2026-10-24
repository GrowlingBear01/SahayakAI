import ApprovalCard from "./components/ApprovalCard.jsx";
import Composer from "./components/Composer.jsx";
import Header from "./components/Header.jsx";
import LanguageSelector from "./components/LanguageSelector.jsx";
import LiveBrowserView from "./components/LiveBrowserView.jsx";
import ResultCard from "./components/ResultCard.jsx";
import TaskProgress from "./components/TaskProgress.jsx";
import Toast from "./components/Toast.jsx";
import Transcript from "./components/Transcript.jsx";
import VoiceControls from "./components/VoiceControls.jsx";
import VoiceOrb from "./components/VoiceOrb.jsx";
import WebsiteChoiceCard from "./components/WebsiteChoiceCard.jsx";
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
  const {
    language,
    flow,
    voice,
    taskState,
    connection,
  } = assistant;
  const taskActive = isActiveTask(taskState);
  const autoHint = browserPrefersHindi() ? "autoLangHi" : "autoLangEn";
  const webEventData =
    assistant.lastEvent?.task_id === assistant.taskId
      ? assistant.lastEvent.data || {}
      : {};
  const webCandidates =
    webEventData.candidates ||
    (assistant.task?.web_candidates || []).map((candidate, index) => ({
      id: String(index + 1),
      ...candidate,
    }));
  const selectedWebsite =
    webEventData.selected_site ||
    webCandidates.find(
      (candidate) => candidate.url === assistant.task?.selected_site_url,
    );
  const webPhase = webEventData.web_phase || assistant.task?.web_phase;

  return (
    <div className="app-shell">
      <div className="live-region" aria-live="polite">
        {statusLabel(assistant)} {assistant.assistantText}
      </div>
      <Header
        language={language}
        onLanguage={assistant.setLanguage}
        flow={flow}
        onFlow={assistant.setFlow}
      />

      {connection === "unavailable" ? (
        <p className="notice" style={{ marginBottom: 16 }}>
          {t("backendDown", language)}
        </p>
      ) : null}

      <div className="app-grid">
        <section className="panel stage">
          <p className="status-chip">{statusLabel(assistant)}</p>
          {voice.listening || voice.speaking ? (
            <div className="wave" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          ) : null}
          <VoiceOrb state={assistant.orbState} />
          <p className="muted" style={{ maxWidth: 540 }}>
            {t("welcome", language)}
          </p>
          <LanguageSelector language={language} onChange={assistant.setLanguage} />
          {language === "auto" ? <p className="muted">{t(autoHint, language)}</p> : null}
          <p className="muted">{t("supportedLangs", language)}</p>
          {assistant.voiceError ? (
            <p className="notice">{t(assistant.voiceError, language)}</p>
          ) : null}
          {!voice.support.speech ? (
            <p className="muted">{t("speechUnsupported", language)}</p>
          ) : null}

          <Transcript
            language={language}
            userText={assistant.userUtterance || assistant.transcript}
            assistantText={assistant.assistantText}
            listening={voice.listening}
          />
          {assistant.voiceDraftPending ? (
            <p className="notice" role="status">
              {t("voiceReviewRequest", language)}
            </p>
          ) : null}

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

          <Composer
            language={language}
            value={assistant.typed}
            onChange={assistant.setTyped}
            onSubmit={assistant.startTask}
            disabled={assistant.busy && taskState !== "needs_info" && !assistant.approval}
            onSuggestion={(item) => {
              assistant.setFlow(item.flow);
              assistant.setTyped(item.text[language === "hi" ? "hi" : "en"]);
            }}
            flow={flow}
            webPhase={webPhase}
          />
          {flow === "web" ? (
            <p className="muted">{t("webModeNotice", language)}</p>
          ) : null}

          <button type="button" className="ghost" onClick={assistant.newConversation}>
            {t("newConversation", language)}
          </button>
        </section>

        <aside className="side">
          <TaskProgress
            language={language}
            request={assistant.userUtterance}
            taskState={taskState}
            progress={assistant.progress}
            onStop={assistant.stopTask}
          />
          <WebsiteChoiceCard
            language={language}
            phase={webPhase}
            candidates={webCandidates}
            selectedSite={selectedWebsite}
            onSelect={assistant.startTask}
          />
          <LiveBrowserView
            language={language}
            url={assistant.streamingUrl}
            action={assistant.liveBrowserAction}
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
          />
          <ResultCard
            language={language}
            result={assistant.result}
            onSwitchDemo={() => {
              assistant.newConversation();
              assistant.setFlow("demo");
              assistant.setTyped(t("demoFallbackRequest", language));
            }}
          />
        </aside>
      </div>

      <Toast
        toast={assistant.toast}
        language={language}
        onDismiss={() => assistant.setToast(null)}
      />
    </div>
  );
}
