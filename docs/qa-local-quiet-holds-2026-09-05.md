# Local presentation: non-blocking quiet holds

## Result

The replacement Wikipedia presentation completed through the local Studio/Jobs workflow.
Project `fbb062e9-c421-467b-ac87-4cb783bbd495` is named **Wikipedia — Smooth narration retry**.
Job `021a0304-d580-461e-90d2-0677ada490dd` succeeded on its first attempt in 9 minutes 3 seconds.
The preceding failed project and its saved slides were retained without resetting its retry cap.

Export `ee57134d-a6ad-418d-82f4-c346d07903c5` is 120.000 seconds, 2560x1440 at 30 fps,
with H.264 video and AAC narration. Nine authored slides contain seven real website recordings,
19 recorded clicks, 21 coordinate-bearing interactions and 21 derived smooth zooms. Three
Parallel research sources and nine real Gemini/Google ADK slide receipts were verified.

Gemini 3.1 Flash TTS produced the opening speech, then returned HTTP 429 on slide two.
The configured adapter switched to Gemini 2.5 Flash TTS, which produced slides two through nine.
All nine usable audio recordings passed on their first timing attempt; there were no corrective
audio regenerations. Narration model identity is saved in each new speech receipt.

## Changed behavior

- Duration-based word budgets remain planning guidance and an upper-bound preflight check.
  Short, otherwise valid narration no longer fails merely for having too few words.
- Speech plays as one paragraph with constant gain and a single bounded playback speed.
  Short speech is not slowed, repeated, or cut into fragments to fill its slide.
- Unused time becomes a measured quiet hold while the recording continues. The longest quiet
  gap in this export is 13.04 seconds, intentionally accepted under the requested policy.
- Captions use the actual speech duration and disappear when it ends, preventing a final
  highlighted word from staying on screen throughout a hold. Existing fixed-layout Inter
  captions and 30 fps highlight timing remain in place. Word timing is still estimated.
- Dynamic product-slide durations exercised both extension (10 to 10.5 seconds, 16 to 16.9)
  and shortening (15 to 14.5 seconds, 17 to 16.1). The final total remained 120 seconds.
- Quiet holds no longer fail final audio verification. Missing/invalid audio, clipping risk,
  typed-schema failures and unsafe or ungrounded execution plans still block publication.

## Error reporting

Direction-check receipts now record slide/attempt, error category, validation field/type pairs
and check locations without raw provider payloads or credentials. Known checks have safe,
customer-readable explanations in Jobs.

This run caught slide-six copy exceeding a template field's character limit. The bounded
text-only retry corrected it before TTS; the slide subsequently completed. This establishes
the cause of that validation failure in this run, not the exact cause of the earlier run whose
generic error did not retain these details.

## Verification

- 510 repository checks passed: 388 Python, 88 web, 27 contracts and seven runner; four
  opt-in provider tests skipped. The live application run above was separate from these tests.
- Focused quiet-hold, pipeline, script and composition checks: 44 passed. Caption end-time
  assertions and the final error-explanation checks passed after their last adjustments.
- Repository lint, strict typecheck and production compliance passed.
- Authenticated project-library membership, latest-export identity and HTTP 206 delivery passed.
- FFprobe metadata, complete video/audio decoding and contiguous nine-slide timing passed.
- Audio duration is 120 seconds, normalized active RMS approximately 0.102, peak 0.637.
- Browser playback confirmed readyState 4, advancing playback, no media error, and 2560x1440
  dimensions. A rendered frame during slide three's quiet hold showed the product with no
  lingering caption highlight. Existing encoded caption timing/layout tests remain green.

The export is saved in `artifacts/exports/presentation-9-slides-fbb062e9-c421-467b-ac87-4cb783bbd495-7543a3e5.mp4`.
Detailed machine-readable results are in this project's ignored `full/local-verification.json`.
No cloud deployment, resource deletion, credential changes or previous-project deletion occurred.
