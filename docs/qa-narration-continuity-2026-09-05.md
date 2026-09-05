# Continuous narration verification â€” 2026-09-05

The local Wikipedia two-minute presentation was rebuilt with continuous narration per slide.
The previous export remains available. The new export is the latest for the same project.

- Project: `131916a2-e019-4bcf-958d-95ffff140e41`
- Export: `31063bb9-b6bb-41f4-b5c2-b54ac875a191`
- File: `artifacts/exports/presentation-9-slides-131916a2-e019-4bcf-958d-95ffff140e41-9a8348d6.mp4`
- SHA-256: `fcf73eb59f3db89409726c561c2efadc1e9dd0c259dcc5dd306e9874f951b50e`

## Changes

The pipeline synthesizes the full paragraph once per slide, preserving narrative context.
It no longer replaces full narration with short action summaries or pads each of three
phrases independently. A focused Google ADK narration rewriter uses saved evidence and
measured duration feedback when speech does not fit. Retries remain bounded.

Audio preparation preserves short edge margins, uses a constant gain per paragraph,
applies short edge fades, limits tempo changes to 0.9â€“1.1x, and emits 48 kHz mono PCM.
Speech that needs excessive padding, compression, or has a long internal pause is rejected.
The final soundtrack is assembled from the original prepared WAVs, bypassing intermediate
AAC slide tracks. The final encoded export is decoded and checked before publication.

Cache keys include narration version, voice configuration, model, and slide duration;
composition keys also include the actual audio hash. Existing recordings are reused.
Captions now span the measured continuous speech duration. Word highlighting remains
approximate; this change does not implement forced alignment or retime the saved actions.

## Measured exported audio

Both exports were decoded to mono floating-point PCM at 24 kHz for the same comparison.
Quiet intervals use a -45 dBFS RMS threshold in 10 ms windows; quiet time includes natural
pauses and quiet speech frames, so it is not a measure of missing content.

| Check | Before | After |
| --- | --- | --- |
| Duration | 120.000 s | 120.000 s |
| Longest quiet interval | 5.71 s | 1.43 s |
| Total quiet frames | 64.77 s | 32.93 s |
| Samples at or above 0.999 full scale | 0 | 0 |

Every video and audio frame decoded without an FFmpeg error. The nine slides retain their
original 120-second schedule at 2560 Ã— 1440. A rebuilt slide screenshot confirmed the new
caption text fits the frame. This is signal and artifact verification, not a claim of
subjective listening review or a guarantee against every possible TTS pronunciation artifact.

Evidence is in `artifacts/presentations/131916a2-e019-4bcf-958d-95ffff140e41/continuous-narration/`:
`audio-comparison.json`, `audio-verification.json`, per-slide narration receipts, rewrite
receipts, scripts, compositions, and `result.json`.

## Regression checks

The final full Python suite passed 341 tests, with four optional provider tests skipped.
All 18 focused narration, director, pipeline, and composition tests also passed.
Lint and strict typechecking passed for all seven changed Python source/test files.
The final full Python regression result is recorded in `artifacts/narration-regression-tests-final.log`.
