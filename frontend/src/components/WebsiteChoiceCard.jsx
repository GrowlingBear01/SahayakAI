import { t } from "../utils/messages.js";

function hostname(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

export default function WebsiteChoiceCard({
  language,
  phase,
  candidates,
  selectedSite,
  onSelect,
}) {
  if (phase === "site_choice" && candidates.length) {
    return (
      <section className="panel card">
        <h2>{t("chooseWebsite", language)}</h2>
        <p>{t("chooseWebsiteHelp", language)}</p>
        <div className="scheme-results">
          {candidates.map((candidate, index) => (
            <article className="scheme-result" key={`${candidate.id || index}-${candidate.url}`}>
              <h3>{candidate.name}</h3>
              <p><strong>{hostname(candidate.url)}</strong></p>
              <p>{candidate.reason}</p>
              <p className="muted">
                {t("siteConfidence", language)}: {candidate.confidence}
              </p>
              <button
                type="button"
                className="primary"
                onClick={() => onSelect(String(candidate.id || index + 1))}
              >
                {t("chooseThisSite", language)}
              </button>
            </article>
          ))}
        </div>
      </section>
    );
  }

  if (phase === "question" && selectedSite) {
    return (
      <section className="panel card">
        <h2>{t("selectedWebsite", language)}</h2>
        <p><strong>{hostname(selectedSite.url)}</strong></p>
        <p>{selectedSite.reason}</p>
        <p className="muted">{t("readOnlyWebsiteNotice", language)}</p>
      </section>
    );
  }
  return null;
}
