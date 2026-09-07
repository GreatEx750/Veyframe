# Presenter split frame

Standalone 2560 × 1440 layout for a 40-second closing segment. Not registered with Veyframe or connected to generation. The composition follows the supplied Frame.png reference, with the outer purple border removed: edge-to-edge pastel background, a wide rounded screen recording on the left, and a rounded portrait presenter on the right.

## Files

- `preview.png`: layout preview with placeholder labels; do not use as the final overlay.
- `overlay.png`: production frame with genuinely transparent media openings. Place above the two video layers. No labels, presenter, or webpage are baked in.
- `background.png`: opaque background for workflows that composite independently masked media on top.
- `video-mask.png` and `presenter-mask.png`: full-canvas masks; white is visible, black is hidden.
- `overlay.svg`, `background.svg`, `preview.svg`: editable vector versions.
- `layout.json`: exact canvas and slot coordinates in pixels.

## Placement

| Layer | X | Y | Width | Height | Corner radius |
| --- | ---: | ---: | ---: | ---: | ---: |
| Screen recording | 52 | 153 | 2016 | 1134 | 22 |
| Presenter | 2128 | 392 | 369 | 656 | 24 |

Place the recording and presenter at those coordinates beneath `overlay.png`. The larger desktop window is exactly 16:9 (2016 × 1134), so standard landscape footage fits without bars or cropping. Preserve aspect ratio; do not stretch the app. The smaller presenter window is exactly 9:16 and vertically centered alongside the recording. Presenter footage should fill the portrait opening, with the face kept inside the crop. The overlay supplies the rounded corners and shadows.

Keep the same frame throughout the closing segment while changing only the left-side footage. Suggested footage: benchmark, Parallel import/search code and matching request, then Cloud Run. Audio comes from the presenter or narration track; this pack contains no audio or recorded content.

To rebuild and verify from the repository root: `node templates/presenter-split-v1/build.mjs`.
