import { t } from "../utils/messages.js";

export default function LanguageSelector({ language, onChange }) {
  return (
    <div className="suggestions" role="group" aria-label={t("language", language)}>
      {[
        ["en", "EN"],
        ["hi", "HI"],
        ["auto", "Auto"],
      ].map(([value, label]) => (
        <button
          key={value}
          type="button"
          className={language === value ? "primary" : "ghost"}
          aria-pressed={language === value}
          onClick={() => onChange(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
