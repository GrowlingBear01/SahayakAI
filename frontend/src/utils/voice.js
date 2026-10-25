export function isVoiceSendCommand(text) {
  const value = String(text || "")
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[.!?。！？।,،]+$/u, "")
    .replace(/\s+/g, " ");
  return [
    "send",
    "send it",
    "send request",
    "send the request",
    "submit",
    "submit it",
    "submit request",
    "bhejo",
    "bhej do",
    "bhej dijiye",
    "jama karo",
    "भेजो",
    "भेज दो",
    "भेज दीजिए",
    "भेजें",
    "जमा करो",
    "जमा करें",
  ].includes(value);
}

export function recognitionErrorKey(error) {
  switch (String(error || "").toLowerCase()) {
    case "not-allowed":
    case "service-not-allowed":
      return "micDenied";
    case "no-speech":
      return "micNoSpeech";
    case "network":
      return "micNetworkError";
    case "audio-capture":
      return "micCaptureError";
    default:
      return "micRecognitionError";
  }
}
