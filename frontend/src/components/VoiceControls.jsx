import { t } from "../utils/messages.js";

export default function VoiceControls({
  language,
  listening,
  speaking,
  recognitionSupported,
  taskActive,
  onMic,
  onStopListen,
  onInterrupt,
  onReplay,
  onStopTask,
}) {
  return (
    <div className="voice-bar">
      <button
        type="button"
        className="primary"
        onClick={listening ? onStopListen : onMic}
        disabled={!recognitionSupported}
        aria-pressed={listening}
      >
        {listening ? t("stopListening", language) : t("startListening", language)}
      </button>
      <button type="button" className="ghost" onClick={onInterrupt} disabled={!speaking}>
        {t("interrupt", language)}
      </button>
      <button type="button" className="ghost" onClick={onReplay}>
        {t("replay", language)}
      </button>
      {taskActive ? (
        <button type="button" className="danger" onClick={onStopTask}>
          {t("stopTask", language)}
        </button>
      ) : null}
    </div>
  );
}
