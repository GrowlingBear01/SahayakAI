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
    />
  );
}
