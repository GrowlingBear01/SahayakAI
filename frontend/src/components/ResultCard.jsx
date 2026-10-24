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

export default function ResultCard({ language, result, flow }) {
  if (!result) return null;
  const titleKey = TITLES[result.state] || "couldNotFinish";
  const evidence = result.evidence;
  const kind = evidence?.kind;
  const summary =
    language === "hi" ? result.summary_hi || result.summary_en : result.summary_en || result.summary_hi;

  return (
    <section className="panel card result" data-state={result.state} aria-live="polite">
      <h2>{t(titleKey, language)}</h2>
      <p>{summary}</p>
      {flow === "discovery" ? <p className="muted">{t("possibleMatches", language)}</p> : null}
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
        <p className="notice">{result.needs_human_kind}</p>
      ) : null}
    </section>
  );
}
