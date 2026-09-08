# Current timing correction — September 7, 2026

Supersedes the historical timing methodology below. Per user instruction, current public values count the selected successful attempt only: Presentation 535 seconds, Spotlight 142 seconds, Short 211 seconds (all rounded up). Failed attempts and retry waiting are excluded. Short is explicitly labeled resumed/cached work. Product Demo remains the user-reported 1216-second estimate.

With the unchanged estimated five-minute brief/review allowance, totals are 13m55s, 7m22s and 8m31s. Presentation comparison is 88%; Spotlight 79%; Short 81%. Presentation's 120-minute manual baseline is now attributed to the creator's reported measured average; other totals and all stage allocations remain estimates. Sample size is not available in the snapshot.

Updated shared docs/images/benchmark.png (referenced by README and devpost-submission.md), landing data/copy, downloadable JSON, and desktop/mobile verification captures. Six focused tests, web typecheck and lint passed. Browser checks verified displayed values, resumed labeling and mobile page width. Local assets updated; publication/deployment is separate.

---

# Landing-page production-time comparison

## Scope

Added a public benchmark section beneath the existing video examples. The design takes inspiration from LiveBench's comparison table, filters, dated data and inspectable details; no LiveBench scores, branding or affiliation are used. Existing Veyframe colors and Inter typography are retained. No runtime generation behavior, provider configuration, project records or cloud deployment changed.

The table shows all four formats without a date/sample toolbar or format filter. It retains expandable run/estimate details, fixed manual-time assumptions, a downloadable sanitized timing snapshot, and explicit methodology. Manual estimates are fixed at 60, 120, 35 and 45 minutes for Product Demo, Presentation, Spotlight and Short; visitors cannot edit them. Mobile users can scroll the table independently without overflowing the page.

## Evidence and assumptions

Snapshot: September 6, 2026, local development. These are three selected completed jobs, not a controlled benchmark, population average or success-rate study. Full job-creation-to-completion windows include retries and intervening gaps, rounded up to whole seconds.

| Format | Recorded window | Attempts | Manual estimate | Veyframe total with estimated 5m brief/review | Estimated difference |
| --- | --- | --- | --- | --- | --- |
| Product Demo, 90s assumption | Not measured | Not available | 60m | Not available | Not available |
| Presentation, 120s | 27m 8s | 3 | 120m | 32m 8s | 1h 27m 52s less / 73% |
| Spotlight, 30s | 2m 22s | 1 | 35m | 7m 22s | 27m 38s less / 79% |
| Short, 45s | 6m 41s | 2 | 45m | 11m 41s | 33m 19s less / 74% |

The public snapshot contains job IDs and timestamps for auditability, no credentials or private filesystem paths. Presentation refers to the original application-generated job, not the independently edited showcase. Product Demo has a manual estimate only: the inspected local job list has no matched successful Product generation. The packaged Northstar asset is not a timed generation run. Its timestamps, job ID and attempts remain null, and no total or savings are calculated.

The user requested reasonable manual estimates. These assume an editor familiar with the product, existing templates, research/script, recording, voiceover, captions/layout and one review pass. They are not timed trials or industry averages. The five-minute Veyframe brief/review allowance is also explicitly estimated. Setup, prepared recording workflows, earlier development/debugging and later revisions are outside the window; human intervention was not separately timed. Savings are estimated elapsed-time differences, not proven labor hours eliminated.

## Verification

- Tests were added before implementation; the initial focused run failed on missing modules, then all 12 focused benchmark/landing tests passed.
- Full web package: 118 tests passed. Contracts: 27 passed. Script runner: 7 passed.
- Full Python regression: 432 passed, four opt-in provider tests skipped. Total automated checks: 584 passed, four skipped. No test failures remain.
- Repository lint and strict typecheck passed; the new browser-check script also passed its direct lint check.
- Production build passed, including the final contrast/mobile-guidance changes.
- Production readiness check passed (386 files after adding this report); whitespace check passed.
- Real Chromium checks at 1440px and 390px passed: displayed arithmetic, details, negative savings, reset, filtering, public timing JSON, independent horizontal scrolling, no page overflow and no browser errors.
- Screenshots and browser results: `artifacts/landing-benchmark/`.

## Fixed-estimate follow-up

At the user's request, removed numeric inputs, estimate state, reset controls and editing instructions. Values and savings are unchanged and remain explicitly labeled estimates. Updated regression tests and the browser check assert static values and absence of edit/reset controls. The arithmetic helper retains defensive validation and negative-difference handling. No backend logic or benchmark evidence changed.

Follow-up verification: 118 web tests, web lint/typecheck, production build, desktop/mobile browser checks, verification-script lint and whitespace checks passed. The earlier full-backend results above are from the original feature verification, not a rerun for this UI-only follow-up.

No cloud deployment or paid generation was performed for this feature.

## Four-format and simplified-header follow-up

Removed the date/sample toolbar and Format dropdown, including filter state and unused styling. All four formats are visible together. Added Product Demo with a fixed 30-minute manual planning estimate (5 script, 5 capture, 7 narration, 10 edit/captions, 3 review), explicitly scoped to a 20-second continuous demo. Missing measurements remain unavailable rather than being treated as zero. Existing measured rows are unchanged. The UI skill kept existing Inter, colors and table styling.

Verification: four new/adjusted assertions failed before implementation; all 118 web tests then passed. Web lint, typecheck, production build, verification-script lint and whitespace checks passed. The build retried two static pages after timeout warnings and ultimately exited successfully; its reported elapsed time was unusually long. Real Chromium desktop/mobile checks passed for all four rows, no date/filter controls, fixed estimates, unavailable Product timing, details, public JSON, horizontal scrolling and no page overflow or browser errors. Desktop screenshot visually inspected. No backend regression rerun for this UI-only change; no cloud deployment or new generation.

## Product Demo baseline correction

Replaced the original 20-second/30-minute assumption with the user's typical 90-second Product Demo and approximately 60 minutes of professional manual production. The fixed total is explicitly attributed as a user-provided estimate. Its illustrative stage split is 10 minutes scripting, 10 recording, 15 narration, 20 editing/captions/layout and 5 review/export; individual stages were not timed. This changes benchmark data only, not Studio durations or generation behavior. Generation timing and savings remain unavailable without a matched completed job.

Verification: two expected regression failures before the data change, then all 118 web tests passed; web lint/typecheck, verification-script lint and desktop/mobile browser checks passed. Downloaded JSON and the visible row both report 90 seconds and 60 minutes. No cloud deployment or paid generation.
