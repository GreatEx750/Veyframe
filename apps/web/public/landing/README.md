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
  The blue top brief, central footage and coral caption strip are editable template
  layers; the reference photograph and placeholder words are not part of the video.
  The latest revision rounds the colored panels and footage window in the exported
  video, while retaining the same recordings, narration and 45-second duration.

`scripts/build-landing-assets.mjs` recreates these files from the retained local export
artifacts. Rebuilding samples is a maintainer operation; production builds use the
checked-in public files and do not require the local artifacts or video encoder.

The landing page is `/`; the authenticated creation workspace is `/studio`.
