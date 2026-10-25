import { useEffect, useMemo, useState } from "react";
import { coerceEdits, fieldsWithKeys } from "../utils/approval.js";
import { t } from "../utils/messages.js";

export default function ApprovalCard({
  language,
  approval,
  taskValues,
  busy,
  flowMismatch,
  onApprove,
  onEdit,
  onCancel,
}) {
  const [editing, setEditing] = useState(false);
  const fields = useMemo(
    () => fieldsWithKeys(approval, taskValues),
    [approval, taskValues],
  );
  const [draft, setDraft] = useState({});

  useEffect(() => {
    setEditing(false);
    const next = {};
    for (const field of fields) next[field.key] = field.value ?? "";
    setDraft(next);
  }, [approval?.approval_id, fields]);

  if (!approval) return null;
  const submit = approval.approval_type === "submit";
  const action =
    language === "hi"
      ? approval.action_hi || approval.action_en
      : approval.action_en || approval.action_hi;
  const notice =
    language === "hi"
      ? approval.data_notice_hi || t("dataNoticeFallback", language)
      : approval.data_notice_en || t("dataNoticeFallback", language);
  const hasMismatch = submit && fields.some((field) => field.mismatch);

  return (
    <section className="panel card approval" aria-label={t(submit ? "submitApprovalTitle" : "startApprovalTitle", language)}>
      <h2>{t(submit ? "submitApprovalTitle" : "startApprovalTitle", language)}</h2>
      <p>{action}</p>
      <p className="muted">{approval.site_kind === "demo" ? t("demoForm", language) : t("realWebsite", language)}</p>
      {flowMismatch ? (
        <p className="notice">
          {t(
            approval.site_kind === "real" ? "flowMismatchDiscovery" : "flowMismatch",
            language,
          )}
        </p>
      ) : null}
      <p className="notice">{notice}</p>
      {fields.map((field) => (
        <label className="field" key={field.key}>
          {language === "hi" ? field.label_hi || field.label_en : field.label_en || field.label_hi}
          {field.mismatch ? <span className="notice">{t("fieldMismatch", language)}</span> : null}
          {editing ? (
            <input
              value={draft[field.key] ?? ""}
              onChange={(event) =>
                setDraft((current) => ({ ...current, [field.key]: event.target.value }))
              }
            />
          ) : (
            <strong>{String(field.value ?? "")}</strong>
          )}
        </label>
      ))}
      <div className="actions">
        {editing ? (
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => onEdit(coerceEdits(fields, draft))}
          >
            {t("saveEdits", language)}
          </button>
        ) : (
          <button
            type="button"
            className="primary"
            disabled={busy || hasMismatch}
            onClick={() => onApprove(null)}
          >
            {t("approve", language)}
          </button>
        )}
        {fields.length ? (
          <button
            type="button"
            className="ghost"
            disabled={busy}
            onClick={() => setEditing(true)}
          >
            {t("edit", language)}
          </button>
        ) : null}
        <button type="button" className="ghost" disabled={busy} onClick={onCancel}>
          {t("cancelApproval", language)}
        </button>
      </div>
    </section>
  );
}
