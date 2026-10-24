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
