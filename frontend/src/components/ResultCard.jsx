import { t } from "../utils/messages.js";

const TITLES = {
  done: "done",
  could_not_finish: "couldNotFinish",
  stopped: "stopped",
  outcome_unknown: "outcomeUnknown",
};

const EVIDENCE_LABEL = {
  extracted_text: "evidenceExtracted",
  agent_reported: "evidenceReported",
  verified_confirmation: "evidenceVerified",
};

const HUMAN_ACTION_LABEL = {
  captcha: "needsHumanCaptcha",
  otp: "needsHumanOtp",
  login: "needsHumanLogin",
  blocked: "needsHumanBlocked",
};

export default function ResultCard({ language, result, onSwitchDemo }) {
  if (!result) return null;
  const titleKey = TITLES[result.state] || "couldNotFinish";
  const evidence = result.evidence;
  const kind = evidence?.kind;
  const summary =
    language === "hi" ? result.summary_hi || result.summary_en : result.summary_en || result.summary_hi;
  const note =
    result.note === "stop_too_late" ? t("stopTooLate", language) : result.note;
  const isDiscovery = result.flow_id === "myscheme_discovery";
  const schemes = Array.isArray(result.schemes) ? result.schemes : [];

  return (
    <section className="panel card result" data-state={result.state} aria-live="polite">
      <h2>{t(titleKey, language)}</h2>
      <p>{summary}</p>
      {note ? <p className="muted">{note}</p> : null}
      {isDiscovery ? <p className="muted">{t("discoveryDisclaimer", language)}</p> : null}
      {schemes.length ? (
        <div className="scheme-results">
          <h3>{t("schemeListings", language)}</h3>
          {schemes.map((scheme, index) => (
            <article className="scheme-result" key={`${scheme.name}-${index}`}>
              <h4>{scheme.name}</h4>
              <p>
                {language === "hi"
                  ? scheme.description_hi || scheme.description
                  : scheme.description || scheme.description_hi}
              </p>
              {language === "hi" && !scheme.description_hi ? (
                <p className="muted">{t("schemeHindiUnavailable", language)}</p>
              ) : null}
              {scheme.scheme_page_url ? (
                <p>
                  <a href={scheme.scheme_page_url} target="_blank" rel="noreferrer">
                    {t("schemePage", language)}
                  </a>
                </p>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
      <p className="muted">{t("notProof", language)}</p>
      {kind ? (
        <div className="evidence">
          <strong>{t(EVIDENCE_LABEL[kind] || "evidenceReported", language)}</strong>
          {evidence.text ? <p>{evidence.text}</p> : <p className="muted">—</p>}
          {evidence.screenshot_url ? (
            <p className="muted">{evidence.screenshot_url}</p>
          ) : null}
        </div>
      ) : null}
      {Array.isArray(result.links) && result.links.length
        ? result.links.map((link) => (
            <p key={link}>
              <a href={link} target="_blank" rel="noreferrer">
                {link}
              </a>
            </p>
          ))
        : null}
      {result.needs_human_kind ? (
        <p className="notice">
          {t(HUMAN_ACTION_LABEL[result.needs_human_kind] || "couldNotFinish", language)}
        </p>
      ) : null}
      {result.offer_demo && onSwitchDemo ? (
        <button type="button" className="primary" onClick={onSwitchDemo}>
          {t("switchToDemo", language)}
        </button>
      ) : null}
    </section>
  );
}
