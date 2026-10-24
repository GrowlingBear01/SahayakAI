import { t } from "../utils/messages.js";

export default function Toast({ toast, language, onDismiss }) {
  if (!toast) return null;
  const text = toast.text || t(toast.messageKey, language);
  return (
    <div className={`toast ${toast.kind || ""}`} role="status">
      <p style={{ margin: 0 }}>{text}</p>
      <button type="button" className="ghost" onClick={onDismiss} style={{ marginTop: 8 }}>
        OK
      </button>
    </div>
  );
}
