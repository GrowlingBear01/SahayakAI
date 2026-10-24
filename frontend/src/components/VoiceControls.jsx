import { useRef } from "react";
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
  const keyboardActivationRef = useRef(false);

  function startPointerListening(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    onMic();
  }

  function stopPointerListening() {
    onStopListen();
  }

  function startKeyboardListening(event) {
    if ((event.key !== " " && event.key !== "Enter") || event.repeat) return;
    event.preventDefault();
    keyboardActivationRef.current = true;
    onMic();
  }

  function stopKeyboardListening(event) {
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    onStopListen();
  }

  return (
    <div className="voice-bar">
      <button
        type="button"
        className="primary"
        onPointerDown={startPointerListening}
        onPointerUp={stopPointerListening}
        onPointerCancel={stopPointerListening}
        onLostPointerCapture={stopPointerListening}
        onKeyDown={startKeyboardListening}
        onKeyUp={stopKeyboardListening}
        onBlur={() => {
          if (listening) onStopListen();
        }}
        onClick={(event) => {
          if (event.detail === 0 && !keyboardActivationRef.current) {
            listening ? onStopListen() : onMic();
          }
          keyboardActivationRef.current = false;
        }}
        disabled={!recognitionSupported}
        aria-pressed={listening}
        aria-label={`${t(listening ? "stopListening" : "startListening", language)}. ${t("pushToTalk", language)}`}
      >
        {listening ? t("stopListening", language) : t("pushToTalk", language)}
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
