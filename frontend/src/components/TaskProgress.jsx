import { eventMessage, isActiveTask, t } from "../utils/messages.js";

export default function TaskProgress({
  language,
  request,
  taskState,
  progress,
  onStop,
}) {
  if (!taskState && !progress.length) return null;
  const current = progress[progress.length - 1];
  return (
    <section className="panel card" aria-label={t("working", language)}>
      <h2>{t("working", language)}</h2>
      {request ? <p>{request}</p> : null}
      <p className="muted">
        {taskState || "—"}
        {current?.total_steps
          ? ` · ${current.step}/${current.total_steps}`
          : ""}
      </p>
      <ol className="steps">
        {progress.map((event, index) => (
          <li
            key={`${event.ts}-${index}`}
            className={index === progress.length - 1 ? "current" : ""}
          >
            <span className="dot" />
            <span>{eventMessage(event, language)}</span>
          </li>
        ))}
      </ol>
      {isActiveTask(taskState) ? (
        <button type="button" className="danger" onClick={onStop} style={{ marginTop: 12 }}>
          {t("stopTask", language)}
        </button>
      ) : null}
    </section>
  );
}
