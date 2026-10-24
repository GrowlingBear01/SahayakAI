# TinyFish M0 Smoke-Test Notes

Date: 2026-10-24

These notes contain smoke-test observations only. No API keys or personal data
are recorded. The demo values used in the runs were invented.

## Environment

- TinyFish base URL: `https://agent.tinyfish.ai`
- Dummy-site exposure: temporary Cloudflare Quick Tunnel to port `8001`
- Dummy form URL: `MOCK_SITE_BASE_URL/mock/form`
- Wallet before smoke runs: `$38.520`
- Wallet after initial smoke runs: `$37.976`
- Wallet after follow-up checks: `$37.896`
- Observed spend across all M0 checks: approximately `$0.624`
- Initial wallet rate: `$0.016` per agent step and `$0.002` per browser minute

## Required observations

1. **Phase 1 does not submit:** PASS. The dummy-form run completed in 6 steps
   with all four fields matching the intended fake values. The result was
   `submitted: false`, `problems: []`, and the demo database remained empty.
   The approval-code field was left empty.
2. **Field filling:** PASS for `text`, `number`, and the demo form fields. The
   returned values matched `Savitri Devi`, `72`, `Delhi`, and the fake
   ten-digit phone number. A native `select` field was not separately tested.
3. **Public reachability:** PASS. TinyFish reached the dummy form through the
   temporary HTTPS tunnel and returned live browser steps.
4. **Typical runtime and watchdog:** The dummy fill took 67.6 seconds. The
   phase-two fill-and-submit took 9 steps; its exact elapsed time was not
   captured by the first smoke script. Use a 120-second watchdog initially.
5. **Evidence and live view:** PASS. `steps[].screenshot` URLs were populated
   without `capture_config`, and `streaming_url` was present on the
   `run-async` result.
6. **Result shape:** PASS. Both successful goals returned a JSON object directly
   under `result`.
7. **myScheme:** Anonymous access worked in the tested English flow. The run
   returned 10 scheme records and no problems after 19 steps. No CAPTCHA, OTP,
   or login appeared in this run. A second English run and a Hindi-language
   attempt both exceeded the 120-second watchdog and were authoritatively
   cancelled with zero completed steps. Go/no-go: **GO for a guarded,
   read-only demo only**, with the first run as the evidence; do not depend on
   repeated or Hindi myScheme success on stage.
8. **Cost:** The observed wallet delta was approximately `$0.544` for the
   smoke and cancellation runs. Recheck the wallet before rehearsals and M10.
9. **Missing/slow page behavior:** The missing-phone run completed in 32.5
   seconds, left the phone field empty, returned a clear problem, and did not
   submit. A slow-page watchdog run was cancelled after 60 seconds and the
   authoritative final status was `CANCELLED`. The adapter must re-fetch after
   cancellation because the previous poll can be stale.

## Cancellation checks

- Dummy form: cancel response `CANCELLED`; final run status `CANCELLED`.
- myScheme: cancel response `CANCELLED`; final run status `CANCELLED`.
- A separate myScheme watchdog race returned `COMPLETED` from the cancel
  endpoint, demonstrating that cancellation is a request, not a guarantee.
- The two follow-up myScheme runs returned `CANCELLED` after authoritative
  re-fetches; both initially appeared as stale `RUNNING` responses.

## Phase-two demo submission

- TinyFish completed the fill-and-submit run in 9 steps.
- The result was `submitted: true` with confirmation message `Application
  received`.
- The demo server recorded exactly one submission with reference
  `DEMO-D2D652C6`.
- No retry was performed.

## Follow-up results

- The native `select` control remains untested; the demo form currently uses a
  text input for state.
- Hindi myScheme reliability is not demonstrated. Keep myScheme optional and
  lead with the demo form if it is unstable.

## Follow-up before relying on myScheme

- Keep the first successful myScheme run as the only evidence for the guarded
  discovery path.
- Treat Hindi myScheme as unsupported until a stable run is observed.

## M9 guarded implementation check

- One English, read-only M9 check was attempted with no personal details and no
  application action.
- The backend returned `outcome_unknown` with zero safely parsed scheme results;
  it did not claim success.
- The wallet endpoint returned HTTP 200. No balance value was recorded.
- A read-only run-history lookup did not find a matching M9 goal, so a remote
  TinyFish run start could not be independently confirmed. The exact failure
  cause was not captured; do not infer that the site itself failed.
- No second run was performed. M9 remains locally tested but not live-validated.
