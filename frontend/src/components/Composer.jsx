import { copy, t } from "../utils/messages.js";

export default function Composer({
  language,
  value,
  onChange,
  onSubmit,
  disabled,
  onSuggestion,
  inputRef,
}) {
  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(value);
      }}
    >
      <div className="composer-row">
        <input
          ref={inputRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={t("typedPlaceholder", language)}
          aria-label={t("typedPlaceholder", language)}
          disabled={disabled}
        />
        <button className="primary" type="submit" disabled={disabled || !value.trim()}>
          {t("send", language)}
        </button>
      </div>
      <div className="suggestions">
        {copy.suggestions.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onSuggestion(item)}
            disabled={disabled}
          >
            {item.text[language === "hi" ? "hi" : "en"]}
          </button>
        ))}
      </div>
    </form>
  );
}
