# Hosted full-presentation verification — September 5, 2026

## Scope and current result

Cloud verification **did not pass**; no finished two-minute video was produced. The request is a full
two-minute Wikipedia Presentation Demo using the same authored v2 slide-by-slide pipeline as
the local result. This is not the nested DemoDirector self-demo and not a first-five-slide preview.

- Hosted origin: https://demodirector-web-cq5t2gao5q-uc.a.run.app
- Title: **Wikipedia — Cloud 2-minute Presentation Test**
- Project: `d8613612-98b1-4f48-864b-cc873ba445cb`
- Job: `a049de35-910e-4d6b-b6f4-cd49f2c33e61`
- Target: `https://www.wikipedia.org/`
- Studio settings: Presentation Demo, 120 seconds, full sequence, 1440p landscape, narration,
  highlighted captions and smooth zoom enabled. Brief requests Solar System search, article
  sections, and following the Earth link. The shared demo account owns the project.
- Created through the real hosted Studio UI; creation redirected to the selected Jobs detail.
  Existing projects and exports are preserved.

## Cloud changes and observed failures

The hosted app previously lacked the local authored coordinator. The updated backend uses
authenticated Cloud Tasks for one slide per delivery and final assembly, private content-addressed
Storage checkpoints, and Firestore-backed project/timeline/export repositories. It does not rely
on an API instance's background thread or local SQLite surviving a request or restart.

1. First real attempt rendered slide 1, but Firestore rejected directly nested recipe arrays.
   Recipes now use named maps. A regression asserts this representation.
2. Second attempt durably saved slides 1–3, then Cloud Run logged a 4,096 MiB memory-limit
   violation (4,179 MiB used) while slide 4 was rendering. The saved checkpoint contained 116
   files totaling 23.22 MiB and remained readable after the instance terminated.
3. Cloud capture receipts also exposed missing late interactions: slides 2 and 3 retained only
   one and two events from their three-action plans. Presentation capture now records the entire
   sequence and its final result, fitting both video and interaction timestamps to the fixed slide
   duration. Explicit retries invalidate incomplete old recordings. Product Demo is unchanged.
4. API revision `demodirector-api-00038-f2c` deploys the fixes with two CPUs and 8 GiB memory.
   Minimum zero/maximum one instance, concurrency two, existing secrets, task identity and
   authentication are preserved. The queue remains single-dispatch. Higher memory increases
   active-instance resource usage; no concurrency increase was made.
5. The normal UI retry (attempt 3) restored the checkpoint on the new revision and rebuilt slides
   2 and 3 with all three planned interactions each. Slide 2's complete 22.915-second capture was
   fitted to ten seconds, retaining all clicks. Its composed midpoint visibly contains the actual
   Wikipedia page, pointer, rounded product window and highlighted caption.
6. At 21:53:17 UTC the job failed during slide 4 narration with `NarrationTimingError`, after all
   three bounded speech attempts. This happened before slide 4 rendering, so the larger memory
   allowance is deployed but has not yet passed that render. The UI correctly shows failed,
   attempt 3/3, no active lease, and a disabled retry button. No attempt counter was reset and
   no replacement project was created to circumvent the limit.

The saved log exposes the narration exception type but not its measured cause. The validator
rejects insufficient/excessive speech duration after a bounded 0.9–1.1 tempo adjustment, or an
internal pause exceeding 1.25 seconds. The current evidence does not distinguish those cases.
The failed slide's unsaved audio/metrics are not in the committed cloud checkpoint. The next fix
should save safe timing diagnostics and bounded recovery checkpoints, then make narration fitting
reliable without accepting truncated speech or long silent padding. A fresh paid cloud test needs
explicit approval after the existing job exhausted its three attempts.

## Deployed builds

- Initial web/API build: `78fa64b5-0f37-4603-9ed8-234020ec6dbc`, successful.
- Recipe checkpoint correction: `53aa15e3-fafc-4e32-b495-5995b5def295`, successful.
- Complete-action capture correction: `71037d51-9a8a-4f22-9b24-6349fc636068`, successful.
- Hosted web revision: `demodirector-web-00021-4qc`.
- API image: `demodirector-api:presentation-20260905-r3` in the existing project repository.

These manual builds use the local source. During verification the changes were committed as
`861b902` (`cloud update`); the final failure-report update remains a working-tree change.
Image-only deployment preserves runtime settings, including the memory allowance.

## Automated verification

- Full package tests: **481 passed** — 359 Python, 88 web, 27 TypeScript contracts, seven runner;
  four opt-in provider checks skipped. Live cloud generation makes the real provider calls separately.
- Repository lint and strict typecheck passed (149 Python source/test files checked).
- Production compliance passed (315 files); whitespace check passed.
- Regression coverage includes cloud cache restore/tampering, scoped task authentication,
  duplicate delivery, ten-step sequencing, expired leases, map-based recipe serialization,
  injected cloud media publication, and complete interaction capture at five/ten-second budgets.

## Final media verification

Not reached: exact 120.000-second 2560×1440/30fps MP4, nine slide receipts, all planned
interactions retained, narration checks, real Parallel/ADK evidence, full media decode, authenticated
byte-range delivery, Projects membership, visual slide sampling and actual hosted editor playback.
The project and its first three cloud-saved slides remain preserved. This report must not be used
as proof that full cloud generation works yet.
