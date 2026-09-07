# Veyframe self-demo verification

Status: COMPLETE WITH REVIEW CAVEATS. Cloud Roamstead generation and delivery
verified; local Google-color presentation rebuilt, saved and fully decoded.
The notes below are chronological; later results supersede earlier pending states.

## Verified

- Cloud landing, judge entry, Studio and three existing published exports passed
  browser checks. Existing projects were preserved.
- The cloud recorder reached the owner-authorized Roamstead profile. The test
  client timed out shortly before the worker returned HTTP 200; its saved video
  was recovered and inspected instead of submitting a duplicate.
- Three local authored-recorder checks against live Roamstead passed, with loaded
  map markers/property photos and 3, 3 and 2 interactions. Preparation is bounded
  and excluded from the visible recording clock.
- A 20-second format walkthrough through the authored recorder opens saved
  Spotlight and vertical Short examples. The revised timing shows actual Short
  website footage, not just its opening card. This is diagnostic footage without
  the new presentation narration, not the final self-demo.
- Full tests: 7 runner, 27 contract, 105 web and 426 Python tests passed; 4 opt-in
  live tests skipped. Lint and typecheck passed (158 Python files).
- The local outer project is saved as `Veyframe — marketing workflow presentation`
  (`3a0ab083-5be1-442e-a4c6-b0e594d5d4d0`), without starting generation yet. Its
  operator-reviewed, typed profile is scoped to that project and the exact cloud
  Veyframe URL. A real Studio-input recording passed after correcting the profile's
  missing locator strategies and waiting for sign-in completion before navigation.
  These were preparation failures, not failures of the running Roamstead cloud job.

## Failures found and corrections

| Finding | Correction / limitation |
| --- | --- |
| Google blocked automated cloud recording with CAPTCHA | Switched to the owner's authorized Roamstead site; no bypass attempted. |
| Early clicks before hydration and incorrect map-marker selectors | Wait for readiness and actual custom map-marker elements before recording. |
| A workflow variable shadowed activity-card data | Renamed the recording profile variable; focused and package tests pass. |
| Authored videos had no storyboard/trace for Sources | Publish actual captured scenes and record component-call timings. Authored trace routing retains ownership checks; no approval or historical timings are fabricated. |
| Empty Parallel results were searched again at every resumed slide | Preserve the completed research receipt, including a zero-result outcome. Distinguish provider failure from successful searches with no usable results. |
| Short showcase stopped during its title card | Revised capture timing to reach the recorded website section. |

## Deployments

- Landing: `8ed6e8bf-cd29-43b0-8b55-f3325860b1d1` succeeded.
- Roamstead capture support: `338749cf-b007-4b76-81f5-a49a4cd9afef` succeeded.
- Sources publication/reporting: `84b918af-217b-4ecb-bf18-bc493ef34c3f` succeeded.

Two command-based attempts were rejected before process creation. After explicit
user approval to use the browser instead, Studio successfully created the full
Roamstead presentation on 2026-09-06 at 09:07:48 UTC. Job:
`17d4d01d-6fc8-4507-93b5-6d4905457a2a`; project:
`982cff9c-5684-4149-9a92-4324b17824f7`. The observed job is running; its first slide
reached rendering, with one saved Parallel source and Gemini 3.1 Flash TTS activity.
Do not create a duplicate; verify this saved job.

These are manually submitted Cloud Builds, not evidence of a GitHub push trigger.
Only the new Veyframe services in `demodirector-507722` are deployment targets.

## Execution history

### Local recording update — 2026-09-06

- The outer project explicitly selects the saved Google-color presentation pack
  (`presentation-story-google@1`, 2560 × 1440), per the owner's request. The inner
  Roamstead cloud generation retains its original theme. Theme selection is typed
  and project-scoped in the reviewed local recording profile; defaults are unchanged.
- All nine cloud slides reached completion and final assembly. The sampled product
  frames contain loaded map markers, home photos, visible pointers and highlighted
  captions. Slide 5 has a headline/badge overlap; record this as a layout defect,
  not a clean visual pass. The final MP4 has not yet been verified.
- Repeated Studio preflight captures found `/api/auth/session` returning 401 on
  a failed upstream connection. The web proxy previously converted exceptions into
  authentication failures and cleared cookies. It now reports 503 for temporary
  failures, preserves the cookie and retries the session check. Genuine expired,
  absent and revoked sessions still redirect; backend authorization is unchanged.
- Tests: 429 Python passed, 4 opt-in live tests skipped; 7 runner, 27 contract and
  111 web tests passed. Lint and typecheck (159 Python files) passed.
- Web-only build `b490f0cc-2c02-45d1-9cbb-32479a3ceed8` was submitted for the session
  correction and deployed successfully as `veyframe-web-00005-bgb`. Studio capture
  now passes after fresh sign-in. Saved Spotlight/Short capture also passes.
- Cloud Roamstead job succeeded in 32m59s on attempt 1: nine slides, exactly 120s,
  2560 × 1440, 41,602,707 bytes. Its Sources UI shows the real single Parallel
  search and saved source, nine ADK copy stages and TTS stages, seven recorder
  stages, and final assembly. Storyboard approval was not fabricated.
- Full/open-ended video requests returned 500 while a 1KB range returned 206.
  The 41.6MB export exceeds Cloud Run's fixed-length HTTP/1 response limit.
  A streaming file response retains byte ranges, ownership checks and small
  response lengths while omitting fixed length on large responses. Focused range,
  export and invalid-range tests pass. API build
  `9bc0cf3c-4acf-44ea-88c9-09996aa01744` is pending deployment verification.
- The exported audio receipt reports 120s duration, 0.701 peak and a longest
  internal quiet interval of 5.51s. Quiet holds are allowed; this is an automated
  measurement, not a claim that the entire narration was listened to.
- API streaming fix deployed successfully as `veyframe-api-00006-5fv`. The full
  authenticated download now succeeds and matches saved SHA-256
  `dda6417f3c24e26dee8be3c8ed61635d6066a0a49f98b89505e962eaf1898238`.
  Open-ended range returns 206, and browser playback advances through actual
  product footage. Full H.264/AAC decoding reports no errors.
- All seven local recording segments (2–8) passed. The Sources segment was
  refined to hold a product shot beside the real runtime evidence. Its initial
  strict-selector failure was corrected to select the first trace summary.
- The local full presentation was started through the normal authenticated app
  generation endpoint. Job `cca5a332-3c48-4bc4-a9b7-057d04029a2b`, project
  `3a0ab083-5be1-442e-a4c6-b0e594d5d4d0`; title
  `Veyframe — marketing workflow presentation`. Google-color profile selected.
  Final local output remains pending. No duplicate cloud job was created.
- The first local export succeeded: nine slides, 120s, 8m54s generation time.
  Reviewer corrections changed "verified evidence" to retrieved project sources
  and removed wording implying cross-format conversion without manual rework.
  Original scripts were preserved in the QA artifacts. Corrected scripts passed
  the typed schema, and the normal Jobs-page rebuild was started to regenerate
  affected narration/composition. This is a reviewed demo, not a claim of zero
  human preparation or review. Rebuild attempt 2 is pending verification.
- Rebuild 2 completed at 120s with corrected copy. Frame review then found that
  timeline scene buttons selected the editing target without seeking the media;
  the purported property shot was still showing the opening/map segment. Added
  deliberate scene-click seeking (no seeking from playback time updates), with a
  regression test. 112 web tests, lint and typecheck pass. Web build
  `9d740a70-c907-4cf6-9e1d-cafa94f7e50d` is pending; replace affected captures only
  after browser verification. Final recording profile now asserts the expected
  playback time before starting those shots.

## Final recording verification

- Scene-selection fix deployed as `veyframe-web-00006-xrq`. Recorder preflights
  for slides 2, 4 and 5 passed explicit playback-time assertions and visual review:
  loaded Roamstead map at 0:09, Sources beside the property scene at 0:29, and the
  property photo/details at 0:41. These are actual saved video segments.
- The three original capture folders and receipts were preserved. Jobs-page
  rebuild attempt 3 replaces only those recordings and dependent compositions;
  existing exports, reviewed scripts and unaffected narration remain intact.
- Latest regression: 432 Python passed, four opt-in live skips; 112 web,
  27 contract and seven runner tests passed. Lint and typecheck passed
  (161 Python files). Production compliance passed for 379 files, and
  `git diff --check` reported no whitespace errors.
- Review caveats: the wide editor viewport makes the inner preview relatively
  small in slides 2 and 5. Slide 8 includes a brief real page-loading transition
  between the populated library and the loaded editor; it is not a failed clip.
  Narration retains quiet holds rather than being slowed to fill every slide.
  Cloud Roamstead slide 5 still has a headline/status overlap.

## Final result — 2026-09-06

- Local Jobs rebuild attempt 3 succeeded at 10:23:23 UTC, without changing the
  three-attempt limit. First generation took 8m54s; the final cached correction
  took approximately 3m24s. The job's 27m7s elapsed value includes review gaps
  and both rebuilds, not continuous initial generation time.
- Export `33b5fc31-8446-4168-a5bb-e75e80af825e`: exactly 120.000 seconds,
  2560 × 1440 H.264 with 48kHz AAC audio, 10,174,723 bytes. Full decode passed
  with no reported errors. Authenticated app download matches saved SHA-256
  `e667d274b1a253b64849a25cff4459cddf9559a60d22e23c635e158aebb22964`.
- Handoff: `artifacts/veyframe-self-demo/veyframe-google-presentation-120s.mp4`.
  The local Projects entry is published as `Veyframe — marketing workflow
  presentation`, project `3a0ab083-5be1-442e-a4c6-b0e594d5d4d0`. The editor's
  Download MP4 action resolves to this final export, not an earlier revision.
- Browser playback advanced from 0:00 to 0:51 and paused on the corrected
  property-details scene. Sources mode loaded the final project's saved direct
  Parallel, Google ADK/Gemini, TTS and recorder stage history successfully.
- Reviewed all nine composed slide samples and additional library-transition
  samples. Corrected slides 2/4/5 show the intended Roamstead map, Sources with
  real Parallel/ADK/TTS activity, and property details. The saved Google-color
  template pack supplies the outer blue/coral/neutral layouts. The embedded
  Roamstead example keeps its original green palette.
- All seven product-bearing capture receipts succeeded, with 14 coordinate-bearing
  clicks total and visible pointers/click indicators. Spotlight and Short are
  separately generated Wikipedia examples, explicitly labeled as saved examples.
- Automated audio measurement: 120s, active RMS 0.1015, peak 0.7155, longest
  internal quiet interval 6.36s. Quiet holds are intentional. Full subjective
  listening and exact word-to-audio alignment are not claimed by these checks.
- This is a reviewed, application-generated presentation using a typed local
  recording profile and two reviewed copy corrections. It is not a claim of an
  unprepared zero-touch nested generation or instantaneous batch conversion.
- The user-owned final minute (landing measurements and real provider/deployment
  evidence) remains outside this generated section. No savings metrics,
  testimonials or endorsements were invented.
