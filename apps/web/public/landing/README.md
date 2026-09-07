# Landing video examples

The eight-second, silent preview clips are extracts from existing application exports.
Landscape previews are encoded at 1280x720; the portrait Short is 720x1280.
Playback metadata is at the front for quick loading.
Full samples retain their narration and open only when requested.

- Product and Presentation: bundled Northstar Analytics examples, a fictional example app.
- Spotlight: a saved Wikipedia cloud generation verification export showing
  https://www.wikipedia.org/ and English Wikipedia articles, with the application's
  recorded pointer, narration and captions. These are public reference-site recordings;
  they do not contain account sessions or private customer content.
- Short: a new 45-second Wikipedia recording generated locally through the application
  pipeline with the approved blue/coral portrait template, Google ADK/Gemini direction,
  Parallel research, Gemini narration, visible pointer interactions and captions.
  The current editorial layout has a rounded recording at the top, in-frame highlighted
  captions, a chapter row, and a large two-line takeaway below it. Blue is the background
  and light coral is the accent. The reference photograph and placeholder words are not
  part of the video. The latest local rebuild uses new native-aperture browser recordings
  and narration at the same 45-second duration.

See [media attribution](../../../../docs/media-attribution.md) for website source pages,
font licenses, and the distinction between code licensing and third-party recorded content.

`scripts/build-landing-assets.mjs` recreates these files from the retained local export
artifacts. Rebuilding samples is a maintainer operation; production builds use the
checked-in public files and do not require the local artifacts or video encoder.

The landing page is `/`; the authenticated creation workspace is `/studio`.
