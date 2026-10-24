import { isHttpUrl } from "../utils/approval.js";
import { t } from "../utils/messages.js";

export default function LiveBrowserView({ language, url, action, active }) {
  if (!active) return null;
  const live = isHttpUrl(url);
  return (
    <section className="panel card" aria-label={t("livePreview", language)}>
      <h2>{t("livePreview", language)}</h2>
      {action ? (
        <p className="live-browser-action" aria-live="polite">
          <strong>{t("liveBrowserAction", language)}:</strong> {action}
        </p>
      ) : null}
      {live ? (
        <div className="browser-frame">
          <iframe title={t("livePreview", language)} src={url} />
        </div>
      ) : (
        <div className="browser-frame">
          <p className="unavailable">
            {active
              ? t("livePreviewStarting", language)
              : t("previewUnavailable", language)}
          </p>
        </div>
      )}
    </section>
  );
}
