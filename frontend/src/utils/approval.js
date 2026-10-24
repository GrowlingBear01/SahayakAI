const LABEL_KEYS = {
  "full name": "full_name",
  "पूरा नाम": "full_name",
  age: "age",
  उम्र: "age",
  state: "state",
  राज्य: "state",
  "mobile number": "phone",
  phone: "phone",
  मोबाइल: "phone",
  "मोबाइल नंबर": "phone",
};

export function isHttpUrl(value) {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function fieldKey(field, index, taskValues) {
  if (field?.key) return field.key;
  const fromValues = Object.keys(taskValues || {});
  if (fromValues[index]) return fromValues[index];
  const label = String(field?.label_en || field?.label_hi || "")
    .trim()
    .toLowerCase();
  return LABEL_KEYS[label] || `field_${index}`;
}

export function fieldsWithKeys(approval, taskValues) {
  return (approval?.fields || []).map((field, index) => ({
    ...field,
    key: fieldKey(field, index, taskValues),
  }));
}

export function coerceEdits(fields, draft) {
  const edits = {};
  for (const field of fields) {
    const raw = draft[field.key];
    if (raw === undefined) continue;
    const asNumber = Number(raw);
    if (
      field.type === "number" ||
      field.key === "age" ||
      (String(raw).trim() !== "" && Number.isFinite(asNumber) && String(raw).trim() === String(asNumber))
    ) {
      if (field.key === "age" || field.type === "number") {
        edits[field.key] = asNumber;
        continue;
      }
    }
    edits[field.key] = String(raw);
  }
  return edits;
}

export function spokenFieldReadback(fields, lang) {
  const hi = lang === "hi";
  return fields
    .map((field) => {
      const label = hi ? field.label_hi || field.label_en : field.label_en || field.label_hi;
      return `${label}: ${field.value ?? ""}`;
    })
    .join(". ");
}

export function eventKey(event) {
  if (!event) return "";
  return [event.task_id, event.ts, event.state, event.message_en, event.step].join(":");
}
