# DemoDirector live smoke checklist

Use this only after the fake-adapter golden path passes. It intentionally limits paid model calls.

- Open the hosted library and create one 20-second project from the Northstar fixture or another
  non-sensitive test site. Confirm it remains after a scale-to-zero restart.
- Run website inspection and one Parallel research request. Confirm sources cite the inspected or
  returned URLs; do not repeat the research request unless it fails.
- Generate one storyboard with Gemini. Check that it has 5–7 grounded scenes and stays within the
  requested duration. This is the only required structured-generation call.
- Queue one capture scene. Confirm the private worker task succeeds and one clip appears beneath the
  project's Cloud Storage prefix. If it fails, verify a diagnostic screenshot is present.
- Render at 720p for the smoke run, apply one prompt edit, and run brief coverage once.
- Export once at 1080p, download it through the scoped token, and verify video dimensions/duration.
- In Cloud Run, confirm API and worker show minimum instances `0` and maximum instances `1`.
- Inspect the web service environment and compiled browser assets: Gemini and Parallel secret values
  and secret environment variable names must not appear in a `NEXT_PUBLIC_` variable.
