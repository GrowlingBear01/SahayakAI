# SahayakAI demo script

Use this run-through only after verifying the backend and browser flows on the demo machine. Use invented demo values only.

## 90-second version

| Time | Action and narration |
|---|---|
| 0:00-0:10 | Introduce Savitri, 72, who can describe a task but finds websites hard to navigate. State the promise: SahayakAI asks before it acts and reports only what it can verify. |
| 0:10-0:35 | Select Hindi and use push-to-talk for a request that needs one missing detail. Let the assistant ask; answer in Hindi. Use typed input if speech recognition or the venue network is unreliable. |
| 0:35-0:55 | If the myScheme flow passed the smoke test and rehearsal, show the read-only discovery results and official links. Describe them only as possible matches and direct the audience to confirm eligibility on the official pages. Otherwise, say the real-site flow is not being demonstrated and continue with the demo form. |
| 0:55-1:20 | Explicitly select Demo Form. Review the start approval and read-back, approve the fill-only phase, then review the separate submit approval and approve once. Show the backend-provided verified result. Do not narrate a successful submission unless the result contains verified confirmation evidence. |
| 1:20-1:30 | Press STOP during a run if a safe rehearsal permits it. State that actions already taken in the cloud browser may remain. Close with: “It asks before it acts, stops when you say stop, and never claims what it can't verify.” |

## Before presenting

- Start the backend and frontend; verify `/health` and the intended flow.
- Confirm the dummy site's HTTPS URL and the live browser preview on the demo machine.
- Confirm Hindi microphone permission and available speech voices; keep typed input ready.
- Use fake demo data only. Never use Aadhaar, bank details, or real identifiers.
- Do not bypass CAPTCHA, OTP, login, or human verification.
- Keep STOP visible and use it only in a rehearsed, safe state.
- If TinyFish is unavailable, play a real recorded run and explicitly disclose that it is recorded. Do not use a fabricated recording.
