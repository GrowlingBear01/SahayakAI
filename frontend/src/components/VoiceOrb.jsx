export default function VoiceOrb({ state }) {
  const label = {
    idle: "idle",
    listening: "listening",
    processing: "processing",
    speaking: "speaking",
    working: "working",
  }[state] || "idle";

  return (
    <div
      className={`orb ${state}`}
      role="img"
      aria-label={`Assistant ${label}`}
    >
      {state === "listening" || state === "speaking" ? (
        <span className="orb-wave" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
        </span>
      ) : null}
    </div>
  );
}
