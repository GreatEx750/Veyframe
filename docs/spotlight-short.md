# Spotlight and Short

Studio now offers Product Demo, Presentation Demo, Spotlight, and Short.

- Spotlight: 30 seconds; hook (4s), one feature recording (22s), CTA (4s).
- Short: 45 seconds; hook (4s), three connected recordings (12s each), CTA (5s).
- Both support landscape 2560 x 1440 and vertical 1080 x 1920.
- Gemini through Google ADK creates project copy and narration scripts from saved inspection,
  the supplied brief, observed action descriptions, and available Parallel research.
- Durations are fixed for these two modes. The brief specifies the desired feature/story.

## Templates

Run `npm run templates:promo`. The four independent packs are under
`services/worker/src/demodirector_worker/templates/{spotlight,short}-{landscape,vertical}-v1`.
`promo-templates.html` is a local specimen gallery; placeholders are not production copy.
Each pack includes integrity-checked background, foreground and product masks, copy-slot limits,
a schedule, and licensed font assets. Existing Presentation packs are not regenerated.

Portrait Shorts use the editorial layout in both template selections: a themed 1080 × 1920
canvas, a rounded 1004 × 1210 product recording at the top, captions inside its lower edge,
and a chapter row above a large headline and continuation. The default palette uses a green
canvas with ivory text and mint accents; Google uses a blue canvas, white and ink text, and
light coral accents (`#FF6666`). A matching arrow completes the lower panel.
The headline and body (CTA on the closing slide) form one short sentence;
the project name fills the brand slot. Landscape layouts retain their existing arrangement.
Revision `short-vertical-{default,google}-editorial-5` invalidates old composition checkpoints.
New recordings use the new aperture dimensions. Previously exported videos retain their layout.

## Runtime

The authenticated generate endpoint routes the two modes to the existing authored job executor.
Project IDs isolate checkpoints and artifacts. Cloud continuation uses three or five section tasks
plus assembly, with the same admission, authentication, lease and retry protections as Presentation.
The existing presentation status/retry transport is reused; Jobs displays the selected format.
Python and TypeScript contracts preserve Product Demo and landscape defaults for older projects.
The new orientation column is additive. Vertical orientation persists into timeline re-exports.

Promo narration uses continuous paragraphs, bounded timing corrections and a final gap/clipping
check. A visual rebuild reuses accepted speech. The existing Presentation narration policy remains
unchanged. Editing controls treat the composed promo sections as authored footage, avoiding double
captions or framing. Replacing edited timelines requires a new project.

## Verification

Live local Wikipedia.com tests completed with real Google ADK/Gemini, Google TTS, and browser
recordings; navigation follows Wikipedia's canonical .org pages. Parallel Search ran but returned
no results for these .com requests, so these examples used inspected page evidence. No research
results were fabricated. Vertical recording opens Wikipedia's responsive contents menu when needed.

Verified outputs and measured audio are in `artifacts/promo-verification/verification.json`.
Spotlight is 30 seconds (landscape), Short 45 seconds (vertical), and the full Presentation regression
120 seconds. Presentation was rebuilt from previously approved recordings/copy/narration with new
AI calls blocked; its decoded narration is compared byte-for-byte with the approved export.

Cloud job continuation is covered by integration tests and live Cloud Run verification in
`demodirector-507722`. Hosted Studio generated and published a 30-second landscape Spotlight and
a 45-second landscape Short using real providers and browser recordings. Both passed authenticated
editor playback, byte-range delivery, audio checks and full MP4 decoding. Cloud vertical output
has not been live-verified by this run; the vertical evidence above remains local-only.
See `qa-cloud-deployment-2026-09-05.md` for failures, corrections, project IDs and test scope.
