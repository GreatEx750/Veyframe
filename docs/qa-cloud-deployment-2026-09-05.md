# Cloud deployment verification report

Project: `demodirector-507722`  
Region: `us-central1`  
Hosted URL: `https://demodirector-web-5zo4cenn3q-uc.a.run.app`

## Outcome

**PASS: Spotlight, Short and full Presentation generated through the hosted Studio, with real
Wikipedia recordings, Google ADK/Gemini, Google TTS and direct Parallel research.** All three
projects remain in the cloud Judge Demo library. These are cloud-generated outputs, not uploaded
local examples. The API fixes are deployed as `demodirector-api-00010-lhc`.

## Automated checks

- Final package run after all runtime corrections: **529 passed** (405 Python, 90 web,
  27 TypeScript contracts, 7 runner); four opt-in provider tests skipped. Real provider calls are
  exercised separately by the hosted mode tests below.
- Final repository lint and strict typecheck passed; production readiness passed (331 files).

- Initial local test run: 402 Python tests passed, 4 live-provider checks skipped;
  also 7 runner, 27 TypeScript contract and 90 web tests passed.
- Initial type check: failed on one test fixture that passed a plain `str` where the typed
  contract requires `HttpUrl`. Fixed with a static `HttpUrl` cast. The resumed full type check
  passed on September 6 UTC (151 Python source files plus both TypeScript packages).
- Resumed lint found two import-order errors introduced during the earlier fixes. Both corrected;
  final repository lint passed.
- Storyboard schema regression test: 13 passed after removing provider-unsupported collection
  constraints from the Gemini response schema.
- Capture deadline regression test: passed. It verifies that a single browser action is capped at
  15 seconds while the total capture deadline remains authoritative.

## Hosted smoke findings

### New-project Gemini rate limit — existing-key workaround

The newly-created Gemini key was rate limited at the Product Demo understanding stage (HTTP 429).
Inspection completed and Parallel saved four research sources before that point. The deployment now
uses the already validated Google Gemini runtime credential from the local successful generation;
the credential is stored only in Secret Manager. Hosting resources are in `demodirector-507722`,
but Gemini quota and billing follow the existing key's originating project. Successful generation
with this key does not verify Gemini access against the new project's promotional credits.

### Gemini storyboard schema rejection — fixed

Gemini rejected the `GeneratedStoryboard` schema with HTTP 400 because it contained `minItems` and
`maxItems` collection constraints. The product already validates the five-to-ten-scene policy after
typed schema parsing. Those unsupported provider hints were removed and a regression test added.
The hosted retry then generated and saved a valid six-scene storyboard.

### Gemini 2.5 Flash reasoning-model trial — not used

`gemini-2.5-flash` returned HTTP 404 for this credential because the model is no longer available
to new users. The deployment was returned to `gemini-3.5-flash-lite`, which is available and passed
the corrected storyboard request. This was a reasoning-model trial, not the TTS fallback;
`gemini-2.5-flash-preview-tts` did successfully generate speech in the authored tests.

### Product Demo capture timeout — unresolved, outside resumed three-mode scope

The first hosted 90-second Product Demo reached capture but exceeded its overall recording deadline.
The second attempt identified action 16: the plan expected a Wikipedia homepage control after a
previous action had navigated to an article. This is a plan/state mismatch, not evidence that the
page simply needed more time. The capture runtime
now caps individual browser locator actions at 15 seconds, so an unavailable or slow page control
cannot hold the job for the entire capture budget. Updated API and capture-worker images were
deployed, but this bound does not repair the invalid plan. Both attempts failed. A proposed
unconditional page reset between beats was withdrawn: it would disrupt continuous recordings.
Its built image (`continuous-reset-20260906`) was not deployed. Existing failed project and job
are retained.

## Authored mode verification

### Authored final assembly rejected cloud media — fixed and cloud-verified

Spotlight attempt 1 completed and cloud-saved all three sections, then failed immediately during
assembly with `RendererError`. The pipeline constructed the final renderer with `/app/artifacts`
as its allowed media root, although the configured cloud artifacts live under `/tmp/demodirector`.
The renderer correctly rejected paths outside that root. It now receives the exact per-project
output directory, preserving path-containment validation rather than weakening it.

The strengthened pipeline test uses an artifact root outside the checkout and calls the real media
path validator. It reproduced the failure before the fix; 39 presentation/promo/cloud tests passed
afterward. A further 18 job-monitor/cloud tests passed, including a safe diagnostic for media-root
errors. Cloud job failures now retain that safe explanation instead of only an exception class.
Build: `78a5f08a-6aa3-4fbf-9629-c52c660852b2` (`authored-media-root-20260906`).
Deployed revision `demodirector-api-00009-m4r`. Spotlight retry succeeded from saved sections:
30.000-second 2560×1440 output, H.264/AAC, playable in the hosted editor, range requests HTTP 206,
Projects membership and complete decode all passed. The exported audio peak was 0.582 and longest
internal silence 0.69 seconds. Real receipts show four Parallel sources, ADK evidence reads,
three coordinate-bearing capture interactions, and successful Gemini 2.5 TTS fallback on section 3.

### Escaped punctuation displayed in slide copy — fixed and cloud-verified

Visual QA caught a literal `\u2014` in Spotlight's opening body copy. Typed slide text now normalizes
only a small allowlist of printable punctuation escapes; arbitrary/control escapes remain literal.
The regression failed before the correction; 43 slide-direction/pipeline/promo tests then passed,
and affected lint plus strict typecheck passed. Build `0e816878-e1fd-42c5-ba17-fda8c60b2262`
(`slide-copy-20260906`), deployed as `demodirector-api-00010-lhc`. Spotlight's saved-slide rebuild
completed and the opening frame was visually rechecked: the dash renders correctly. Final export
`2426c86c-b686-44c6-b289-e1613b615eb8` passes the same playback/decode checks. Previous export is kept.

### Login unavailable during Spotlight rendering — configuration corrected

The hosted smoke's status check failed with HTTP 503 at login. Cloud Run logged
"The request was aborted because there was no available instance" while slide 2 was rendering.
The API had a maximum of one instance with concurrency two. Increased its maximum to two;
kept minimum zero, concurrency two, the existing image and the one-active-job-per-user admission
guard. Revision `demodirector-api-00008-d8n` is ready. Login and status retrieval succeeded after
the change. This follows Google's [no available instances guidance](https://docs.cloud.google.com/run/docs/troubleshooting#abort-request).

The resumed request focused on Spotlight, Short and Presentation, not Product Demo.
Generation ran sequentially through the hosted Studio. Each completed output passed saved job
progress, export metadata, editor Play/Pause and seeking, resolution, Projects membership,
authenticated byte-range retrieval and full-file decode checks.

The reusable check is `scripts/smoke-cloud-modes.py`; non-secret evidence and screenshots are saved
under `artifacts/cloud-mode-smoke`. It uses the hosted application pipeline, not local rendering.

| Mode | Project | Result |
| --- | --- | --- |
| Spotlight (30s, landscape) | `7b7021ba-1b00-444b-992f-50fd9988bf59` | PASS; corrected opening visually verified after saved-slide rebuild |
| Short (45s, landscape) | `3d42a559-1577-4ab1-aaf0-c27d270412fb` | PASS on attempt 1; 45.000s, 2560×1440, nine recorded interactions |
| Presentation (120–140s, all 9 slides) | `caf1cae8-91ca-4c15-b26a-71e84079f597` | PASS on attempt 1; exactly 120.000s, 2560×1440, 21 recorded interactions |

Short export: `fc0e862c-76df-491f-b507-f1ce650019f0`. Hosted Studio creation and Jobs redirect,
saved checkpoints, publication, library membership, actual editor Play/Pause, seeking, byte-range
delivery and full MP4 decode passed. Sampled opening, article navigation and closing frames are
saved with the test evidence. Audio peak 0.629; longest internal silence 0.87 seconds. Generation
took 8m50s including three real browser recordings, five narrated sections and assembly.

Presentation export: `390c396e-ba25-43e6-9aa2-cc93c4014442`; 28,431,007 bytes, H.264/AAC,
30 fps. All nine section midpoints were inspected in the hosted editor. Product footage appears
in sections 2–8; sections 1 and 9 are opening/closing layouts. Captured pointer and click rings,
template framing and highlighted captions are visible. Cloud receipts contain seven successful
recordings with three interactions each, nine ADK direction receipts, four retrieved Parallel
sources and a partner source cited in the finished scripts. All nine accepted narration files
used `gemini-2.5-flash-preview-tts` after the configured primary rate limit. Per-slide receipts,
not the result summary's configured-primary label, identify the actual speech model.

The presentation's audio peak was 0.699, with longest internal silence 6.78 seconds. Quiet holds
are intentional under the approved narration policy, not dropped audio; the video continues while
captions clear after speech. Full generation took **24m26s** on the current two-CPU API configuration.
This verifies completion, not fast generation. No presentation retry was necessary.

## Test limits and retained state

- These live tests cover 2560×1440 landscape. Cloud vertical orientations, arbitrary websites and
  the complete post-generation editing surface were not exhaustively tested.
- Word highlighting uses estimated timing; it is not word-level forced alignment with the audio.
- The failed Product Demo from the earlier four-mode attempt remains unresolved and preserved;
  it was excluded by the resumed three-mode request. Do not interpret this report as a Product Demo pass.
- No projects, exports, HabiWatch resources or retry counters were deleted/reset. Spotlight's first
  successful export remains available alongside its corrected export.
- An added QA status helper initially requested a web detail route that is not exposed. The helper
  was corrected to read the existing Jobs overview; this was a test-harness error, not a generation
  failure. The final playback verification passed afterward.
- Runtime changes are deployed from local source; this work did not commit/push to GitHub or create
  a new-project continuous-deployment trigger. The Gemini credential/quota caveat above still applies.

## Open the generated projects

Sign in using Judge Demo, then open:

- [Wikipedia — Cloud Spotlight verification](https://demodirector-web-5zo4cenn3q-uc.a.run.app/projects/7b7021ba-1b00-444b-992f-50fd9988bf59/editor)
- [Wikipedia — Cloud Short verification](https://demodirector-web-5zo4cenn3q-uc.a.run.app/projects/3d42a559-1577-4ab1-aaf0-c27d270412fb/editor)
- [Wikipedia — Cloud Presentation verification](https://demodirector-web-5zo4cenn3q-uc.a.run.app/projects/caf1cae8-91ca-4c15-b26a-71e84079f597/editor)
