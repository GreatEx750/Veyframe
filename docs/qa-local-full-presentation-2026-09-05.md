# Local full Presentation Demo verification — 2026-09-05

## Result

DemoDirector generated a real nine-slide, 120.000-second Wikipedia presentation through the
local Studio, Jobs, and editor flow. This verifies the authored full-length pipeline, not the
earlier requested nested DemoDirector self-demonstration and not cloud deployment.

- Project: **Wikipedia — 2-minute Presentation Test**, `131916a2-e019-4bcf-958d-95ffff140e41`.
- Job: `8f41be2b-fe6a-495c-8e7d-d608e2e0f9cf`.
- Latest export: `62e65dc7-27d4-4844-beed-1fd8a36f4cd1`.
- Output: `artifacts/exports/presentation-9-slides-131916a2-e019-4bcf-958d-95ffff140e41-38867315.mp4`.
- Final media: 2560 × 1440, 30 fps, H.264 video, AAC narration, exactly 120 seconds.
- Evidence: `artifacts/presentations/131916a2-e019-4bcf-958d-95ffff140e41/full/` contains
  scripts, ADK receipts, capture events, per-slide compositions, result metadata,
  `media-verification.json`, and `verified-contact-sheet.png`.

## Application flow and recovery

Created the named project through Studio with Presentation Demo selected and the first-five
preview unchecked. Creation selected the returned job in Jobs. The first attempt stopped at
slide 3 because a valid short narration instruction was rejected by an arbitrary minimum word
count. The rule now accepts nonempty instructions while retaining the upper bound, typed
schema, exact recipe, source, and copy geometry checks.

An explicit UI retry reused the saved first two slides and completed all nine slides. Visual
review then found low-contrast slide 8 card text and slide 6 narration copied from the preceding
Earth workflow. Corrected the card ink, removed previous narration from the direction context,
and added a deterministic narration guard for the built-in Solar System section recipe.

The UI's explicit **Rebuild from saved slides** action used the third bounded attempt on the
same job. It reused all seven recordings, regenerated the invalid slide 6 script/narration,
rerendered affected slides, and published a new export. The previous successful MP4 and all
other projects remain. Rebuild completed from 09:48:09 to 09:50:04 Arizona time; this is a
cached correction run, not a cold generation benchmark.

## Media and provider checks

- All nine slide durations match the authored schedule: 3, 10, 15, 17, 16, 17, 20, 17, and 5 seconds.
- Seven real browser recordings fill their template-native apertures. Product footage is
  present from second 3 through second 115; only the opening and closing omit it.
- Capture receipts contain 19 coordinate-bearing clicks and support 21 bounded smooth zooms.
  Visible cursor movement and click rings are part of the real recordings. Zoom begins after
  the initial full view and is applied inside the product window, not to the slide frame.
- Nine real Google ADK evidence-reading receipts and schema-validated slide scripts were saved.
  Gemini generated narration; direct Parallel Search saved three sources, with one separately
  inspected website source. The rebuild reused this research rather than searching again.
- Word highlighting uses the existing stable phrase layout; its timing remains approximate,
  not audio-forced alignment.
- Every frame of the final MP4 decoded without errors. A contact sheet of all nine finished
  slides confirmed visible product footage, fitted copy, and readable corrected card text.
- Jobs reports success and links to the same project's editor. The editor exposes the latest
  export ID, 120-second duration, nine scenes, and a playable QHD video. The project is visible
  in the local demo account's library.
- Actual editor playback advanced from 0 to 120 seconds and reached the browser's ended state
  without a media error. Temporary buffering occurred during local playback, but it resumed
  and completed without seeking. The editor is left open on the verified project.

## Automated verification

Full package regression passed: 335 Python, 88 web, 27 TypeScript contract, and seven runner
tests (457 total); four opt-in provider tests skipped. Repository lint, strict typecheck over
143 Python files, production web build, 308-file compliance scan, and whitespace checks passed.

## Remaining limitations

- This does not prove the nested self-demo workflow. The earlier failed self-demo remains
  documented separately and is not relabeled as successful.
- The authored local pipeline is not yet deployed to Cloud Tasks; keep the local API running.
- Current recordings use bounded navigation recipes. A more varied, project-specific workflow
  and tighter semantic matching between every slide heading and action remain quality work;
  a full-length render is not proof of those capabilities.
- Authored captions and camera moves are baked into slide clips; existing editor controls do
  not provide independent post-generation layers for them.
- Previously reported Studio setting propagation and preview-library duration issues remain
  outside this correction. Account admission still permits only one active generation.
