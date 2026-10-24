import { useState } from "react";
import Composer from "./Composer.jsx";
import { eventMessage, isActiveTask, t } from "../utils/messages.js";

const TABS = ["conversation", "transcript", "activity"];

function ActivityItem({ event, language }) {
  const timestamp = event.ts ? new Date(event.ts) : null;
  const time =
    timestamp && !Number.isNaN(timestamp.getTime())
      ? timestamp.toLocaleTimeString()
      : null;

  return (
    <li>
      <span className="activity-marker" />
      <div>
        <p>{eventMessage(event, language) || event.state}</p>
        {time ? <time>{time}</time> : null}
      </div>
    </li>
  );
}

export default function ConversationPanel({
  language,
  flow,
  request,
  transcript,
  answer,
  progress,
  taskState,
  composerRef,
  onSubmit,
  typed,
  onTypedChange,
  disabled,
  onSuggestion,
  onToast,
  onStopTask,
}) {
  const [activeTab, setActiveTab] = useState("conversation");
  const userText = request || transcript;

  async function copyResponse() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(answer);
      onToast({ kind: "success", text: t("responseCopied", language) });
    } catch {
      onToast({ kind: "error", text: t("copyFailed", language) });
    }
  }

  function askFollowUp() {
    setActiveTab("conversation");
    window.requestAnimationFrame(() => composerRef.current?.focus());
  }

  return (
    <section className="conversation-panel">
      <div className="conversation-heading">
        <div>
          <p className="eyebrow">{t("conversationLabel", language)}</p>
          <h2>{t("conversation", language)}</h2>
        </div>
        <span className="conversation-flow">
          {t("selectedFlow", language)} · {t(flow === "demo" ? "demo" : "discovery", language)}
        </span>
      </div>
      <div className="conversation-tabs" role="tablist" aria-label={t("conversationViews", language)}>
        {TABS.map((tab) => (
          <button
            key={tab}
            id={`tab-${tab}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            aria-controls="conversation-tab-panel"
            tabIndex={activeTab === tab ? 0 : -1}
            onClick={() => setActiveTab(tab)}
            onKeyDown={(event) => {
              if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
              event.preventDefault();
              const direction = event.key === "ArrowRight" ? 1 : -1;
              const nextIndex = (TABS.indexOf(tab) + direction + TABS.length) % TABS.length;
              setActiveTab(TABS[nextIndex]);
              document.getElementById(`tab-${TABS[nextIndex]}`)?.focus();
            }}
          >
            {t(tab, language)}
          </button>
        ))}
      </div>
      <div
        id="conversation-tab-panel"
        className="conversation-content"
        role="tabpanel"
        aria-labelledby={`tab-${activeTab}`}
      >
        {activeTab === "conversation" ? (
          <div className="message-thread" aria-live="polite">
            {userText ? (
              <article className="message user-message">
                <p className="message-meta">{t("you", language)} · {t("yourRequest", language)}</p>
                <p>{userText}</p>
              </article>
            ) : (
              <p className="empty-conversation">{t("conversationEmpty", language)}</p>
            )}
            {answer ? (
              <article className="message assistant-message">
                <p className="message-meta">{t("sahayak", language)} · {t("assistantReply", language)}</p>
                <p>{answer}</p>
                <div className="message-actions">
                  <button type="button" className="text-action accent" onClick={copyResponse}>
                    {t("copyResponse", language)}
                  </button>
                  <button type="button" className="text-action" onClick={askFollowUp}>
                    {t("askFollowUp", language)}
                  </button>
                  {isActiveTask(taskState) ? (
                    <button type="button" className="text-action danger-text" onClick={onStopTask}>
                      {t("stopTask", language)}
                    </button>
                  ) : null}
                </div>
              </article>
            ) : null}
          </div>
        ) : null}
        {activeTab === "transcript" ? (
          <div className="transcript-view" aria-live="polite">
            {userText || answer ? (
              <>
                {userText ? (
                  <article className="transcript-entry">
                    <span className="transcript-speaker">{t("you", language)}</span>
                    <p>{userText}</p>
                  </article>
                ) : null}
                {answer ? (
                  <article className="transcript-entry">
                    <span className="transcript-speaker">{t("sahayak", language)}</span>
                    <p>{answer}</p>
                  </article>
                ) : null}
              </>
            ) : (
              <p className="empty-conversation">{t("transcriptEmpty", language)}</p>
            )}
          </div>
        ) : null}
        {activeTab === "activity" ? (
          <div className="activity-view">
            {taskState ? <p className="activity-state">{taskState}</p> : null}
            {progress.length ? (
              <ol className="activity-list">
                {progress.map((event, index) => (
                  <ActivityItem
                    key={`${event.ts}-${index}`}
                    event={event}
                    language={language}
                  />
                ))}
              </ol>
            ) : (
              <p className="empty-conversation">{t("activityEmpty", language)}</p>
            )}
          </div>
        ) : null}
      </div>
      <div className="follow-up">
        <p className="eyebrow">{t("followUpLabel", language)}</p>
        <Composer
          inputRef={composerRef}
          language={language}
          value={typed}
          onChange={onTypedChange}
          onSubmit={onSubmit}
          disabled={disabled}
          onSuggestion={onSuggestion}
        />
      </div>
    </section>
  );
}
