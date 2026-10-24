import { t } from "../utils/messages.js";

export default function Header({
  language,
  onLanguage,
  flow,
  onFlow,
  connection,
  onExpandVoice,
  voiceToggleRef,
}) {
  const connected = connection === "ok" || connection === "live";
  const connectionLabel = connected
    ? "connected"
    : connection === "checking"
      ? "backendStatus"
      : "notConnected";

  return (
    <header className="topbar">
      <div className="topbar-title">
        <h2>{t("studioTitle", language)}</h2>
        <p>{t("studioSubtitle", language)}</p>
      </div>
      <div className="topbar-controls">
        <span className={`connection-badge ${connected ? "connected" : "disconnected"}`}>
          <span className="connection-dot" />
          {t(connectionLabel, language)}
        </span>
        <label className="control">
          {t("flow", language)}
          <select
            value={flow}
            onChange={(event) => onFlow(event.target.value)}
            aria-label={t("flow", language)}
          >
            <option value="demo">{t("demo", language)}</option>
            <option value="discovery">{t("discovery", language)}</option>
          </select>
        </label>
        <label className="control">
          {t("language", language)}
          <select
            value={language}
            onChange={(event) => onLanguage(event.target.value)}
            aria-label={t("language", language)}
          >
            <option value="en">English</option>
            <option value="hi">हिंदी</option>
            <option value="auto">Auto</option>
          </select>
        </label>
        <button
          ref={voiceToggleRef}
          type="button"
          className="fullscreen-button"
          onClick={onExpandVoice}
        >
          <span aria-hidden="true">⛶</span>
          {t("fullScreenVoice", language)}
        </button>
      </div>
    </header>
  );
}
