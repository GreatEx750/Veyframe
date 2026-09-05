# Editorial presentation template pack

`presentation-story@2` is a pre-authored, product-first visual system for a two-minute Presentation Demo. It borrows the supplied reference's editorial rhythm—flat forest and mint fields, thin metadata rails, oversized concise typography, asymmetric product apertures, restrained callouts, and narration straps—without copying its branding, language, screenshots, or product identity.

Every master is 2560 × 1440 in sRGB. The 1280 × 720 `preview.png` files are review thumbnails only. `contact-sheet.png` shows the complete pack at a glance.

## Asset layers

Each slide folder contains:

- `source.svg`: editable QHD master with clearly named copy and product groups.
- `background.png`: opaque QHD base layer with no project-specific copy.
- `foreground.png`: transparent QHD framing layer with no project-specific copy.
- `product-mask.png`: grayscale QHD aperture mask for product-present slides.
- `preview.png`: flattened specimen used only for visual review.

The bundled Inter variable font and its license live in `shared/`. `tokens.json` fixes visual tokens. `motion.json` contains only enumerated motion presets. `manifest.json` defines the exact two-minute schedule, typed copy slots, product geometry, and SHA-256 integrity hashes.

## Composition order

1. Draw `background.png`.
2. Place real product footage through `product-mask.png`. The authored renderer records at the aperture's native resolution and places the footage without rescaling.
3. Draw `foreground.png`.
4. Render validated project copy, captions, cursor, and click feedback into declared slots.

Only the opening 0–3 seconds and closing 115–120 seconds omit a product aperture. Slide 2 shows a ten-second product example from 3–13 seconds; every layout from 3–115 seconds requires product footage. The local application uses all nine slides for the full 120-second Presentation Demo and the first five for the optional 61-second preview. The separate `presentation-story@1` renderer remains for legacy exports, not new presentation generation.

Regenerate committed assets with `npm run templates:presentation` and review the contact sheet before accepting changes.
