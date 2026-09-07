# Veyframe self-demonstration plan

Recording subject: the owner-authorized Roamstead application. Roamstead is a
previously built example site, not part of Veyframe's newly built implementation.
The local Veyframe instance records the cloud Veyframe instance. The inner
Roamstead example must finish first; no recursive concurrent generation is implied.

## Generated first two minutes

| Target | Actual screen | Narrative purpose |
| --- | --- | --- |
| 0–3s | Veyframe opening | Turn a working product into a story. |
| 3–13s | Finished Roamstead example playing inside Veyframe | Establish the result immediately. Label it “Previously generated example.” |
| 13–28s | Studio: Roamstead URL, descriptive title, audience and brief | Show the inputs and the human's control of the message. |
| 28–45s | Sources and generation trace from the completed project | Show the actual Parallel requests/results and Gemini/ADK contributions; do not imply retrieved sources when none were saved. |
| 45–61s | Recorded Roamstead map, markers and property details | Explain visible browser actions, pointer movement, narration and captions. |
| 61–78s | The saved job's stage history and timing | Show real progress and elapsed time. Explicitly identify omitted processing time. |
| 78–98s | Presentation, Spotlight and vertical Short example previews | Explain full explanations, focused feature highlights and social clips. These are distinct format choices, not a one-click batch conversion claim. |
| 98–115s | Project library, finished result and available controls | Show where outputs live and demonstrate only controls verified in the running app. |
| 115–120s | Veyframe closing | Less repetitive production work; more time for the story. |

The fixed authored slides remain the visual system. Google ADK/Gemini supplies
validated project-specific copy and narration. Slow setup belongs before each
scene's visible recording clock. Do not stretch speech to fill loading delays.

## User-recorded closing script — 40 seconds

Timing below assumes the preceding video is exactly two minutes. If the edited
showcase is longer, shift these timestamps and keep the final export under three minutes.

| Time | Screen direction | Narration |
| --- | --- | --- |
| 2:00–2:10 | Show the landing-page benchmark. Keep its estimate disclosure visible; do not present synthetic testimonials as customer evidence. | “Veyframe brings recording, narration, and video assembly into one workflow. This benchmark compares recorded or approximate generation times with clearly labeled manual-production estimates.” |
| 2:10–2:22 | Open `services/api/src/demodirector_api/parallel_search.py`. Briefly show the SDK import at line 13, then the client construction at line 111 and Search call at line 121. Enlarge the code so the call and its arguments are readable. | “Here is the actual integration: Veyframe creates the official Parallel client and calls its Search API with a research objective and targeted queries during generation.” |
| 2:22–2:30 | Show one genuine Parallel request and its returned results, then the matching saved sources in Veyframe. Use the same generation for both views. | “These request results become saved sources, giving Gemini and Google ADK evidence for project-specific scripts.” |
| 2:30–2:37 | Show the three Veyframe Cloud Run services and the enabled `veyframe-main-deploy` trigger. Show a successful build only after one actually succeeds. | “Google Cloud Run hosts the application, with GitHub push-triggered builds configured to deploy the web, API, and worker.” |
| 2:37–2:40 | Return to Veyframe's landing page or logo. | “Veyframe. Less production work. More story.” |

The runtime entry point is `services/api/src/demodirector_api/presentation_pipeline.py`
at lines 227–230. It instantiates the adapter and invokes `research_product` on a
fresh research run. Resumed generations can reuse cached sources; use a fresh run
when demonstrating a new Parallel request. Never display API keys or `.env`.

As of 2026-09-07, the GitHub trigger is enabled for `GreatEx750/Veyframe` main.
Its first verification build was cancelled before deployment because the remote
configuration still named older services. The trigger now has corrected inline
Veyframe targets; a successful end-to-end automatic deployment remains to be verified.

If the generated section exceeds its 120-second target, shorten it or rebalance
the final minute before assembly; do not claim the combined result is three
minutes until its exported duration has been measured.

## Verification required before delivery

1. Cloud example appears in the judge-access project library and plays with audio.
2. Every product-bearing slide contains actual successful footage, not loading screens.
3. Map markers and property photos finish loading before the narrated scene starts.
4. Mouse movement and click indicators are visible; optional zoom stays smooth.
5. Spotlight and Short appear in the story and are labeled accurately.
6. Research/AI claims match saved receipts and trace records.
7. Local generated output is saved in Projects, fully decoded and visually reviewed.

## Generated section delivered — 2026-09-06

The reviewed local generation uses the saved Google-color QHD templates and is
exactly 120 seconds. Local project: `3a0ab083-5be1-442e-a4c6-b0e594d5d4d0`;
final MP4: `artifacts/veyframe-self-demo/veyframe-google-presentation-120s.mp4`.
Cloud Roamstead remains saved separately, with its original theme. See
`qa-veyframe-self-demo.md` for verification evidence and remaining polish caveats.
The final user-recorded minute has not been assembled into this file.
