# SahayakAI

Voice-first accessibility assistant concept for hackathon MVPs.

## 1) Honest assessment of the idea
SahayakAI is a strong hackathon direction because it solves a real pain point (navigating complex websites through voice) and can demonstrate meaningful TinyFish usage. The current concept is ambitious; credibility will come from shipping **one reliable read-only workflow** with explicit consent, progress updates, and graceful failure handling.

## 2) Proposed vs currently implemented
> Note: `SahayakAI_ByteCraft.pptx` is not present in this repository, so this assessment uses the problem statement summary.

| Area | Proposed in deck/problem statement | Actually implemented in repo now |
|---|---|---|
| Product concept | Voice-first website task assistant | Concept only |
| Frontend | Voice input + status UI | Not implemented |
| Backend | FastAPI + LLM intent parser | Not implemented |
| TinyFish integration | Search/Fetch/Web Agent workflow | Not implemented |
| Safety | Confirmation before sensitive actions | Not implemented |
| Testing/demo flow | Live end-to-end demo | Not implemented |

Current repository state: only this README (planning stage).

## 3) Single best MVP workflow (24-hour feasible)
**Read-only government scheme explainer** (no form submissions):
1. User speaks/types in Hindi or English (example: “PM-Kisan eligibility batao”).
2. STT (or text fallback) provides command text.
3. Intent classifier maps to `scheme_info_lookup`.
4. TinyFish Search finds likely official page(s).
5. TinyFish Fetch retrieves page content from shortlisted official URL.
6. LLM summarizes key points in simple Hindi/English.
7. App announces progress + final answer; user can cancel anytime.

Why this is best: low legal/safety risk, minimal automation complexity, still demonstrates real web retrieval + accessibility value.

## 4) Realistic architecture using TinyFish (verified assumptions)
Minimal stack:
- **Frontend**: simple HTML/JS page (mic button + text fallback + progress log + stop button)
- **Backend**: FastAPI (single service)
- **LLM layer**: intent classification + safe summarization
- **TinyFish layer**:
  - Search API for discovery
  - Fetch API for grounded page extraction

Public references indicate these integration patterns (must be re-checked in TinyFish dashboard/docs before coding production claims):
- Search: `GET https://api.search.tinyfish.ai?query=...` with header `X-API-Key`
- Fetch: `POST https://api.fetch.tinyfish.ai` with header `X-API-Key` and JSON body like `{"urls":["https://..."],"format":"markdown"}`

Guardrails:
- allowlist trusted domains (e.g., `*.gov.in`, `pmkisan.gov.in`)
- reject suspicious/non-official links
- no write actions in MVP
- explicit “prototype may fail” messaging

## 5) Prioritized 24-hour build checklist
- [ ] **Hour 0-2**: scaffold FastAPI app + single-page UI + env handling
- [ ] **Hour 2-5**: implement intent classification (`scheme_info_lookup` only)
- [ ] **Hour 5-8**: TinyFish Search integration with retries/timeouts
- [ ] **Hour 8-11**: TinyFish Fetch integration + content extraction
- [ ] **Hour 11-14**: Hindi/English response formatting + TTS output
- [ ] **Hour 14-17**: progress events, cancel support, user-facing errors
- [ ] **Hour 17-20**: safety filters (domain allowlist, no-action policy)
- [ ] **Hour 20-22**: demo script + fallback mode (cached sample response)
- [ ] **Hour 22-24**: dry-run testing, README setup/run steps, limitation notes

## 6) Biggest risks (technical, safety, judging)
1. **API uncertainty risk**: endpoint/auth changes can break demo.  
   Mitigation: verify TinyFish docs in real time before coding + keep fallback cached demo path.
2. **Hallucination/incorrect summary risk**: model may misstate scheme facts.  
   Mitigation: show source URL(s), quote extracted lines, and add uncertainty messaging.
3. **Safety/trust risk**: users may assume full automation reliability.  
   Mitigation: explicit prototype disclaimer; no transactional actions.
4. **Accessibility risk**: speech recognition may fail in noisy environments.  
   Mitigation: text fallback always available.
5. **Judging credibility risk**: overclaiming impact/compliance/capabilities.  
   Mitigation: clearly label implemented vs planned; avoid unverifiable claims.

## Next implementation target
Build the MVP as a **read-only, source-grounded scheme information assistant** first; defer booking/forms/OTP workflows to post-hackathon scope.
