# Cloud narration credential retest — 2026-09-06

## Scope

Retry Spotlight and Presentation on Wikipedia through the hosted Studio with the
new Gemini credential supplied in the local `.env`. Preserve earlier projects and
exports. This isolates a credential change; no narration-processing changes are
included, and successful generation alone does not establish audible smoothness.

## Deployment

- Google Cloud project: `demodirector-507722` only.
- Secret: `demodirector-gemini-api-key`, version `3`; uploaded without printing the value.
- API revision: `demodirector-api-00011-fsd`, serving all traffic and explicitly using version `3`.
- Primary speech model remains `gemini-3.1-flash-tts-preview`, with the existing
  HTTP 429 fallback to `gemini-2.5-flash-preview-tts` unchanged.
- `.env` remains ignored by Git. No HabiWatch resources were modified.

## Results

Both generations completed. Fresh projects are used so cached narration cannot mask whether
the new key works. Evidence is kept separately in `artifacts/cloud-new-key-smoke/`.

- Spotlight project: `208f7496-2c97-4f69-956a-0e00989a7c59`.
- Spotlight job: `e4de65be-7a3f-41ee-91a1-4b3663e3ddd4`.
- Initial Spotlight speech request succeeded on Gemini 3.1 and reached section rendering.
- Spotlight attempt 1 stopped on slide 3: 4.41 seconds of speech did not fit its
  four-second slot, and the automatic rewrite returned the same text, reusing the
  same cached speech. This was a timing failure, not a rate-limit failure.
- One normal UI-approved retry completed all three slides without changing code.
  All three accepted narration receipts report `gemini-3.1-flash-tts-preview`.
- Spotlight export: `b8e6de4f-9575-48b6-8914-9c2f4f1beaa8`, 30 seconds,
  completed at 04:42:41 UTC. Total elapsed including the retry pause: 6m35s.
- Presentation project: `3f2f0ae4-d63e-44a2-ad0c-4edeb69fa9e9`.
- Presentation job: `b3ec9c6e-4c48-4493-a823-058d286dce74`, started at 04:43:27 UTC.
- Presentation completed on its first attempt at 05:11:03 UTC (27m35s), nine slides,
  120 seconds, export `16059bce-4568-49e6-848d-dfc1c7ca936b`. All nine accepted
  narration receipts report Gemini 3.1. Seven recordings preserve 21 interactions.
- Spotlight passed hosted playback-presence, dimensions, duration, project-library,
  range-delivery and full-file decoding checks. See the separate player diagnosis
  below: these original checks did not detect continuous playback interruption.
- After the player fix, Presentation also passed the full hosted export checks:
  2560x1440, 120 seconds, nine saved sections, playback and seeking, library presence,
  private range delivery and full MP4 decoding. Both new-key projects passed the
  separate real-time playback regression with zero unwanted seeks or waiting events.

The QA helpers now accept a separate artifact root, and the UI helper accepts a
title suffix, to preserve evidence and videos from prior tests. Python compilation
and `git diff --check` passed for these changes; no production source was changed.

## Preview stutter diagnosis following user recording

The supplied `laggy.mp4` shows the fresh Spotlight in the editor. A read-only
Playwright observation (`scripts/diagnose-preview-playback.py`) reproduced 28
unsolicited seeking events and 28 waiting events during 10.09 seconds of normal
playback. Media advanced only 6.37 seconds despite playbackRate being 1.

The editor's `onTimeUpdate` updates `playheadMs`; a `useEffect` watching that state
then assigns `video.currentTime`. This creates feedback between normal playback
and seeking. Caption highlighting is baked into the rendered frames and does not
control speech playback. Fix the feedback loop by separating observed playback
position from explicit user seek actions. Production code has not been changed
during that diagnosis. The subsequent fix is tracked in
`qa-preview-playback-2026-09-06.md`. Earlier decode/playback-presence checks did not test this
real-time continuity invariant and therefore missed the defect.
