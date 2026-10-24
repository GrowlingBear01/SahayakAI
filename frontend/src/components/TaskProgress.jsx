import { eventMessage, isActiveTask, t } from "../utils/messages.js";

export default function TaskProgress({
  language,
  request,
  taskState,
  progress,
  onStop,
}) {
  const current = progress[progress.length - 1];
  return (
    <section className="task-progress" aria-label={t("liveActivity", language)}>
      <div className="task-progress-heading">
        <h2>{t("liveActivity", language)}</h2>
        {taskState ? <span className="task-progress-state">{taskState}</span> : null}
      </div>
      {request ? <p className="task-progress-request">{request}</p> : null}
      {current?.total_steps ? (
        <p className="task-progress-request">
          {current.step}/{current.total_steps}
        </p>
      ) : null}
      {progress.length ? (
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
      ) : (
        <p className="task-progress-request">{t("activityEmpty", language)}</p>
      )}
      {isActiveTask(taskState) ? (
        <button type="button" className="danger" onClick={onStop}>
          {t("stopTask", language)}
        </button>
      ) : null}
    </section>
  );
}
