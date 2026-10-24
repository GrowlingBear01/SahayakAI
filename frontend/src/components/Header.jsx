import { t } from "../utils/messages.js";

export default function Header({ language, onLanguage, flow, onFlow }) {
  const badge = flow === "demo" ? "demoForm" : "realWebsite";
  const badgeLabel = t(badge, language);

  return (
    <header className="header">
      <div className="brand">
        <h1>SahayakAI</h1>
        <span className="muted">{t("tagline", language)}</span>
      </div>
      <div className="header-controls">
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
        <span
          className={`badge ${flow === "demo" ? "demo" : "discovery"}`}
          aria-label={badgeLabel}
        >
          {badgeLabel}
        </span>
      </div>
    </header>
  );
}
