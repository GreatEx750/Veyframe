# README and example media attribution

## Application code and original artwork

The application code uses the root [MIT license](../LICENSE), an
[OSI-approved license](https://opensource.org/license/mit). Keep its copyright and permission
notice with redistributed copies. The original contributor notice is retained through the
DemoDirector-to-Veyframe product rename.

Veyframe interface screenshots and original architecture drawings illustrate this application.
The architecture directory contains editable SVG sources and PNG exports. Company and product
names identify integrations; they do not imply endorsement or transfer trademark rights.

## README walkthrough media

Captured on 2026-09-07 from the running local application:

- `images/landing.png`: public landing page, excluding the synthetic testimonial section.
- `images/studio.png`: a filled Wikipedia brief, not a submitted job or fabricated output.
- `images/projects.png`: the actual local library filtered to published Wikipedia-related projects.
- `images/editor.png`: the completed blue/coral Wikipedia Short in the real editor.
- `images/benchmark.png`: the real comparison table, including its estimate disclosure.
- `images/product-demo.gif`: five-second silent excerpt from the bundled Northstar Product Demo.
- `images/short-demo.gif`: five-second silent excerpt from the locally generated Wikipedia Short.

The GIFs are trimmed, resized, and frame-rate-reduced for documentation. They do not represent
full-duration playback or real-time generation speed. The linked MP4s retain narration.
`scripts/capture-readme-media.py` captures the UI without submitting a generation job; it requires
the local example project. Documentation screenshots are checked in, so running this script is
not required to build the application.

Northstar Analytics is the project's fictional example application. It is not a customer testimonial.
The independent, manually edited Veyframe showcase is not presented here as an unedited generated export.

## Wikipedia content

Wikipedia is independently operated and is used as a public test website, not a sponsor.
Recorded pages include:

- [Wikipedia portal](https://www.wikipedia.org/).
- [Solar System](https://en.wikipedia.org/wiki/Solar_System), by Wikipedia contributors;
  [article history and author credits](https://en.wikipedia.org/w/index.php?title=Solar_System&action=history).
- [Earth](https://en.wikipedia.org/wiki/Earth), by Wikipedia contributors;
  [article history and author credits](https://en.wikipedia.org/w/index.php?title=Earth&action=history).

Wikipedia article text is available under
[Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/),
subject to the [Wikimedia terms](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content).
Wikipedia-derived text in screenshots and recordings is not relicensed as MIT. Recordings resize,
crop, and annotate the page with cursor feedback, narration, and captions. Those presentation changes
are not changes to Wikipedia itself. Individual images and logos can have separate terms; consult
their linked file-description and credit pages before reusing them. The code license does not grant
rights over third-party content or trademarks.

## Fonts

Bundled Inter font files retain their accompanying SIL Open Font License notices inside each
template pack's `shared` directory. Preserve those notices when redistributing the templates.

## Benchmark and testimonial boundaries

The benchmark combines selected recorded jobs, a user-provided Product Demo timing estimate,
and explicitly labeled manual-workflow assumptions. It is not a controlled labor-saving study.
The landing page's synthetic testimonial cards are labeled as layout examples and are not used
as evidence of customer adoption or satisfaction in this README.
