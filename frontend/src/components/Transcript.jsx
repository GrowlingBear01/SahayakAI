export default function Transcript({ userText, assistantText, listening }) {
  if (!userText && !assistantText && !listening) return null;
  return (
    <div className="transcript" aria-live="polite">
      {userText ? <p className="user">{userText}</p> : null}
      {assistantText ? <p>{assistantText}</p> : null}
    </div>
  );
}
