export default function Transcript({
  history = [],
  userText,
  assistantText,
  listening,
}) {
  const lastTurn = history.at(-1);
  const currentTurnIsRecorded =
    lastTurn?.role === "assistant" &&
    lastTurn.text === assistantText &&
    history.some((turn) => turn.role === "user" && turn.text === userText);
  const showCurrentUser = userText && !currentTurnIsRecorded;
  const showCurrentAssistant = assistantText && !currentTurnIsRecorded;
  if (!history.length && !showCurrentUser && !showCurrentAssistant && !listening) {
    return null;
  }
  return (
    <div className="transcript" aria-live="polite">
      {history.map((turn, index) => (
        <p className={turn.role === "user" ? "user" : ""} key={`${index}-${turn.role}`}>
          {turn.text}
        </p>
      ))}
      {showCurrentUser ? <p className="user">{userText}</p> : null}
      {showCurrentAssistant ? <p>{assistantText}</p> : null}
    </div>
  );
}
