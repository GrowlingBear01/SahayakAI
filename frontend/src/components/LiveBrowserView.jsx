import { isHttpUrl } from "../utils/approval.js";
import { t } from "../utils/messages.js";

export default function LiveBrowserView({ language, url, active }) {
  if (!active) return null;
  const live = isHttpUrl(url);
  return (
    <section className="panel card" aria-label={t("livePreview", language)}>
      <h2>{t("livePreview", language)}</h2>
      {live ? (
        <div className="browser-frame">
          <iframe title={t("livePreview", language)} src={url} />
        </div>
      ) : (
        <div className="browser-frame">
          <p className="unavailable">{t("previewUnavailable", language)}</p>
        </div>
      )}
    </section>
  );
}
