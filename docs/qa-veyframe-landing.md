# Veyframe landing page

The public `/` page follows the supplied landing-page recording: a compact header,
centered introduction and primary action, format tabs, a large video preview, and a
small narrated-example card below. Inter and the approved Veyframe icon are used.
The page uses the reference's blue/purple background treatment.

## Behavior

- Product, Presentation, Spotlight and Short tabs show actual saved application outputs.
- Previews are silent, with a visible pause control. They advance to the next format
  after eight seconds; pausing persists across manual tab changes.
- Reduced-motion preferences disable automatic playback and rotation. Manual play works.
- The example card opens the selected narrated video in a native modal with playback
  controls. Escape and the close button stop the example and restore focus.
- Get started and Sign up open account creation; Log in opens the existing login flow.
- The homepage is public, including when no API session is available.
- Studio moved to `/studio`. Project-library, Jobs, sidebar and verification-tool links
  were updated. Protected routes still check sessions. Login still opens Projects.
- Navigation and authentication branding now use Veyframe, while backend identifiers,
  package names, existing media and saved project names are preserved.

## Verification

`scripts/verify-landing-page.py` verifies public access, all four playable previews,
pause persistence, narrated-modal playback and dismissal, mobile overflow, account
links, reduced motion, and authenticated navigation to Studio. The run passed with
no browser JavaScript errors. Screenshots and results are in
`artifacts/landing-verification/`.

The optimized production build passed and includes public `/` and `/studio` routes.
Lint and strict typechecking passed. The full package run passed: 7 runner tests,
27 contract tests, 102 web tests, and 415 Python tests, with 4 opt-in live tests skipped.
After retaining the existing expired-session regression alongside the new public-route
coverage, the 7 focused landing/session tests passed again. The final browser run also
verified automatic preview rotation and reported no JavaScript errors.

These changes are local. Cloud Run remains on its previously deployed image until
the updated web build is deployed.
