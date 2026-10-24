# SahayakAI pitch outline

Three-minute outline aligned with the build spec. Replace every bracketed measurement with a measured value before presenting; do not estimate or invent results.

| Time | Slide | Content |
|---|---|---|
| 0:00-0:30 | The person and the problem | Introduce Savitri, 72, a Hindi-first user who knows what she needs but struggles to navigate portals. Explain the accessibility gap without claiming the product serves every website. |
| 0:30-2:00 | Live demo | Follow `DEMO_SCRIPT.md`. Lead with myScheme only if its smoke test and rehearsal passed; otherwise lead with the labelled demo form. Show consent, read-back, STOP, and the backend's actual evidence. |
| 2:00-2:30 | Trust model | Show the two approval boundaries, explicit cancellation, the stop behavior, and the distinction between an agent report and verified confirmation. Explain that real-site discovery is read-only. |
| 2:30-2:45 | Evidence | Report `[passes] / [runs]`, `[median latency]`, and test conditions from actual rehearsal results. If metrics are unavailable, say so rather than supplying numbers. |
| 2:45-3:00 | Roadmap | Mention only out-of-scope work from the spec: persistent preferences, hands-free mode, recovery checkpoints, broader site support, and additional languages. |

## Architecture slide

```text
React UI
  - push-to-talk / typed input
  - bilingual transcript, approvals, STOP, results
  - REST requests + SSE progress
        |
        v
FastAPI backend
  - planner -> orchestrator state machine -> verifier
        |
        v
BrowserAgent -> TinyFish cloud browser
  - myScheme discovery (read-only)
  - public HTTPS dummy form (demo submission only)
```

The frontend presents backend state and evidence; it does not decide whether a task succeeded.
