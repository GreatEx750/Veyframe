# Local self-demo smoke test — 2026-09-05

## Result: blocked before recording

This is not a successful video-generation test. No new MP4 was produced.

- Project: `presentation demo test` (`45853248-1491-487d-b4c8-b1ec6858f5ae`).
- Job: `37864881-8013-453c-b3d1-28ed497a5fec`.
- Target: `http://localhost:3000/`.
- Format: full Presentation Demo, 120 seconds, first-five preview unchecked.
- Account: local judge demo. Project and job are preserved.
- Intended story: demonstrate DemoDirector setup using Wikipedia.org, show Jobs, then the existing Wikipedia Exploration Test and Sources. Do not submit a nested generation, delete anything, or portray existing results as newly generated during recording.

## Actual UI exercise

1. Entered the judge demo, opened Jobs, and confirmed zero active jobs.
2. Filled the Studio title, website, brief, audience, CTA, and full Presentation selection. Left smooth zoom and captions enabled.
3. Clicked Create demo. The title persisted and the browser redirected to Jobs with the exact new job selected.
4. Observed saved progress, stage transitions, heartbeat, attempt count, and failure logs. Inspection saved three authenticated pages; research and understanding saved checkpoints.
5. Approved two retries through Jobs. Neither restarted inspection/research/understanding. The job stopped after its three-attempt limit and released the account slot.
6. Opened Projects and verified the named test project remains visible as Failed.
7. Opened the existing Wikipedia Exploration Test. Its video loaded at 2560×1440 with a duration of 61 seconds and playback advanced beyond 31 seconds. This was only a partial playback check of an existing output, not the requested new two-minute video.

## Failure evidence

Times below are local Arizona time.

| Time | Attempt | Result |
| --- | --- | --- |
| 08:43:46–08:44:00 | Initial run | Inspected three pages, saved research and understanding, then storyboard business validation failed. The old generic error did not retain its exact rule or candidate. |
| 08:52:54–08:52:59 | Storyboard retry 1 | Retained typed diagnostic candidate proves Gemini produced four 30-second scenes. Required scene count is five to ten. Rejected before execution. |
| 08:55:24–08:55:25 | Storyboard retry 2 | StructuredGenerationError; no valid storyboard returned. Existing error wrapping did not expose enough safe detail to establish the underlying provider/schema/output cause. Terminal failure after three attempts. |

The initial failure cannot be conclusively attributed to the scene-count rule. The final failure cannot be conclusively attributed to the new schema constraints. No further paid retry or replacement project was submitted.

## Changes made during this test

- Enabled authenticated self-capture for the exact local origin using the ignored local environment setting `DEMO_CAPTURE_AUTH_ORIGINS=http://localhost:3000`. Sessions remain encrypted and scoped; authentication was not disabled.
- Fixed a reproducible business-validation edge case: negated submission instructions such as “do not submit” and “without submitting” no longer incorrectly require a submit click. This was not proven to be the cause of the first live failure.
- Added safe, specific storyboard failure categories and retained rejected typed candidates in private diagnostic records. These records are not storyboard repositories, approvals, or execution checkpoints.
- Made the generation schema require the scenes array and advertise its five-to-ten scene budget; strengthened the presentation prompt. Local tests pass, but live generation is not validated after this change because the final attempt failed earlier in structured generation.

## Other issues found — not implemented in this smoke test

1. **Full Presentation and first-five preview use different template pipelines.** The 120-second path still requests `presentation-story@1`; the first-five path uses the newer authored v2 assets. A preview should not imply that the full output has already been verified to use those same slides.
2. **Library durations describe the requested length, not the actual export.** Wikipedia Exploration Test displays 2:00 in Projects but its editor/video reports 61 seconds. The summary runtime is consequently misleading.
3. **Some Studio settings are not sent to generation.** Voice, language, pace, caption toggle/style, and zoom intensity have visible controls but are absent from the project/generation request. The zoom-enabled setting is sent.
4. **No independent Parallel evidence for a localhost target.** The research stage saved zero Parallel sources. Localhost cannot be publicly indexed; inspected app pages supported understanding. Do not claim that this run found external articles or repositories.
5. **Nested generation conflicts with the one-active-job rule.** Self-recording cannot start a second generation on the same account. A truthful demonstration needs setup plus a clearly identified existing result, or a separately designed staged workflow.
6. **Provider failure diagnostics remain insufficient.** StructuredGenerationError currently hides whether the last attempt failed because of a rejected request, provider response, or typed-output validation. Safe structured error categories are needed before another paid attempt.

## Verification

- Full package run: 7 runner checks, 27 TypeScript contract tests, 86 web tests, and 323 Python tests passed; four opt-in provider tests skipped.
- After adding the schema-budget and diagnostic-checkpoint regressions: all 34 focused storyboard/job/monitor tests passed.
- Repository lint, strict typecheck, and production compliance passed.
- No cloud deployment, new rendered video, end-to-end audio/cursor/zoom verification, or successful two-minute playback is claimed.
