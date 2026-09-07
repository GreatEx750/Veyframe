# Landing previews and judge entry

Local update, September 6, 2026. Cloud Run is unchanged.

## Rounded Short revision

The blue/coral portrait Short now has 32-pixel curved corners on its recording
window and colored panels, plus 20-pixel corners on the monogram block (at 1080p).
The product mask rounds the recorded footage itself, including during zooms; this
is part of the exported MP4, not just a browser-player decoration. Layout, palette,
capture viewport and other template packs are unchanged.

All five sections were re-rendered through the application using the saved script,
recordings and narration. No new research or speech generation was needed. Export
`a36359c8-8020-4c0e-bf81-cad2bdf05055` replaces the landing example and is saved under
the same project. The previous export is retained. Duration remains 45.000 seconds.
Decoded narration SHA-256 matches the previous export exactly:
`f5885f3a491d612965f590667824e365b328c32e8519f5702e544da943634d70`.

The visual revision invalidates cached slide compositions, while the landing media
uses a new poster URL and versioned video URLs. Template tests check all four mask
corners and preserve the original default pack. Frame inspection, full video decode,
desktop/mobile browser playback, lint, typecheck and production web build passed.
The rounded master frame is `artifacts/landing-short-google/rounded-frame.png`.
Rounded-revision full suite: 7 runner, 27 contract, 105 web and 419 Python tests
passed; four opt-in tests skipped. Fourteen focused template checks and six focused
landing tests passed as well.

## Changes

- Presentation is the first tab and initial preview, followed by Product, Spotlight
  and Short. Existing playback, keyboard navigation and reduced-motion behavior remain.
- A visible **Judge Demo Mode** button beside Get started creates a session using
  the existing judge authentication endpoint, then opens Projects. Pending requests
  disable the button; failures show a retryable message without navigating away.
- Short now uses a freshly generated 45-second portrait Wikipedia video, made through
  the application's sequential authored-video pipeline. The approved template has a
  blue top description, overlapping monogram, central live recording, coral narration
  strip and empty black footer. No reference photograph or placeholder URL is used.
- The original editorial packs remain unchanged. Alternate promo pack selection is
  available to the local sample-generation tool; this does not add a Studio theme picker.
- The typed slide-script allowlist now recognizes alternate promo template IDs.
  Unknown templates, capture recipes and source references remain rejected.

## Generated example

Project: `dd910b44-0420-43c4-9e75-21f2aaadfb3e`, **Wikipedia — Blue and coral Short**.
Export: `e1aa736a-6a09-418e-8e3b-67d789d09f9f`.
Master: 1080 × 1920, exactly 45 seconds. Landing copy: 720 × 1280, H.264/AAC,
5.6 MB, with fast-start metadata. The eight-second preview is silent; Watch with
sound opens the full narrated example. Both preserve the portrait aspect ratio.

The application used Google ADK/Gemini for validated scripts and Gemini 3.1 Flash TTS
for continuous narration. Parallel returned four sources; slide citations selected
the directly inspected Wikipedia source instead (zero cited partner sources).
Three product sections recorded nine total interactions at a 968 × 902 viewport,
matching the template aperture. Smooth zoom, visible pointer/click indicators and
paint-only word highlighting were rendered by the existing application components.

Reproduce with `scripts/generate-landing-short.py`, followed by
`node scripts/build-landing-assets.mjs --short-only`. These are maintainer operations;
normal web builds use the bundled files without calling AI services.

## Verification

- All five sections completed and passed the application's render/audio checks.
- The optimized landing video decoded end-to-end without errors; its audio stream,
  portrait dimensions and 45.000-second duration were checked independently.
- Desktop/mobile browser checks passed: first preview, four formats, pause persistence,
  automatic rotation, narrated modal, portrait playback, account links, reduced motion,
  judge entry and Studio navigation. No JavaScript errors or horizontal overflow.
- Initial generation was blocked by an alternate-template ID missing from the typed
  allowlist. Added explicit supported IDs and rejection coverage, then reran successfully.
- New template pixels/layout and preserved default theme selection have regression tests.
- A stale optimized poster was found during visual inspection. The new Short poster
  has a distinct URL to avoid serving the old design from the image cache.

Evidence: `artifacts/landing-short-google/result.json`, section capture/script receipts,
`artifacts/landing-short-google/overview.png`, and `artifacts/landing-verification/`.

Final checks: 7 runner tests, 27 contract tests, 105 web tests and 418 Python tests
passed; four opt-in tests were skipped. Lint, strict typecheck (152 Python files),
production web build and whitespace checks passed. The final browser run also confirmed
the new Short is visible in the judge project library.
