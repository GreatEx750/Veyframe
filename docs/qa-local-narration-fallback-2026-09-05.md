# Local narration budget and fallback verification

## Scope

Presentation scripts now enforce their duration-derived word budget before requesting speech.
The default is approximately 144 words per minute with a two-word tolerance. The conflicting
instruction to use very short action summaries as the entire paragraph was removed. Grounded
ADK text correction preserves recorded actions; speech permits at most one corrective
regeneration. Raw successful audio is cached before timing validation.

Product slides may shorten by up to two seconds using time earned by earlier extended slides,
or extend by up to five seconds within the overall 120–140-second window. Bookends stay fixed.
Captures, interaction timestamps, captions and exports use the resolved durations.

The default Gemini 3.1 Flash TTS adapter falls back once on HTTP 429 to Gemini 2.5 Flash TTS
using the same project, voice and text. The adapter keeps the fallback for subsequent slides.
No fallback is attempted for other error statuses. Both models limited means stop, not a loop.

## Actual local UI retry

- Project: `2be6072e-2098-426c-af13-ce0ebdfbc8ef`, Wikipedia — Flexible narration local test.
- Job: `4c4c1dfc-8866-4c9c-8cb3-77172f8390b1`, third and final allowed attempt.
- Target: `https://www.wikipedia.org/`; requested full nine-slide presentation.
- Triggered through the existing local Jobs page's Approve retry button.
- Slides one through four reused saved successful work.
- Slide five's script was corrected to its 38-word budget before speech.
- At 15:48:58 Arizona time, Gemini 3.1 returned HTTP 429 and the adapter switched to Gemini
  2.5. Its first speech response passed timing validation. The receipt records
  `gemini-2.5-flash-preview-tts`, 14.84 seconds of source speech and a fitted 16-second slide.
- Slide five captured three real Wikipedia interactions and completed rendering at 15:49:57.
  Its 2560x1440, 16.000-second MP4 has both audio and video; full decoding passed.
- At 15:50:06, slide six stopped during Gemini/ADK direction with ValueError, before any TTS
  request for that slide. No candidate was saved by the older failure path, so its precise
  underlying validation cause is not established. It must not be reported as another TTS
  quota failure or as a successful full-video generation.
- Five completed slides remain. No final export was published. The application retry cap was
  not reset, and no replacement project was created to bypass it.

Future word-budget failures have a specific safe Jobs explanation. Typed candidates are now
saved before budget validation, and bounded direction failures save their error category and
budget. Speech model messages retain the narration stage label. These diagnostic follow-ups
were tested after the live retry; no additional paid attempt was made.

## Verification

- Focused narration, script and pipeline checks: 48 passed.
- Final raw-audio reuse and mixed-duration pipeline checks: 24 passed.
- Final director and Jobs diagnostics checks: 19 passed.
- Repository lint, strict typecheck and production compliance passed.
- Saved real Gemini speech in a controlled 15-second slot was rejected by strict timing but
  accepted at 17 seconds with speed 1.0 by flexible timing, without provider calls. This is
  an audio timing check, not another generated video.
- Full package regression: 508 passed (386 Python, 88 web, 27 contracts, seven runner),
  four opt-in provider tests skipped. Final diagnostic and cache-reuse changes also passed
  the focused checks listed above.

No cloud services, resources, credentials, existing projects or exports were deleted or deployed.
