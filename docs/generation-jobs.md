# Durable generation and video quality

## Local development

`npm run dev` starts the web app, API, and generation worker together.
When running the web app and API separately, also run from the repository root:

```powershell
npm run dev:worker
```

The worker reads the same SQLite database and artifact directory as the API. Keep those paths consistent. Closing the browser does not stop the worker. Stopping the worker preserves completed checkpoints; restarting it resumes queued work. Interrupted paid stages require explicit approval before retry. There is a maximum of three attempts per stage.

## Authored Presentation Demo

New Presentation Demo requests use the same sequential, pre-authored `presentation-story@2`
pipeline: nine slides targeting 120 seconds, with a hard 140-second maximum, or an optional
first-five preview targeting 61 seconds (up to 81 seconds). Product Demo keeps its continuous recording pipeline. Full presentations no
longer use the legacy whole-storyboard generator. The old renderer remains for existing exports.

Each slide receives validated Google ADK/Gemini copy, Gemini narration, real browser footage at
the template's native aperture dimensions, visible cursor/click feedback, optional target-aware
smooth zoom inside the footage, and word-highlighted captions. Copy, narration, captures, and
compositions are cached separately. Each finished slide is checked before the next starts, then
the completed slides are assembled and their final media duration is checked before publication.
Parallel Search is called directly. When it returns no results, inspected website evidence may
ground the script instead; the activity log reports the separate source counts truthfully.

The authored schedule remains the baseline, not a forced final runtime. Product slides may extend
by up to five seconds each using a shared 20-second allowance. The three-second opening and
five-second closing remain fixed. Speech is measured first, with modest pitch-preserving tempo
adjustment; excessive pauses and out-of-budget audio still require a bounded narration rewrite.
Slide durations use 100 ms boundaries, aligned to 30 fps. Recording duration, captions, zooms,
scene offsets, final audio, export metadata and completion messages use the measured schedule.
The schedule and versioned narration receipts are saved locally and included in cloud checkpoints.
Retries recompute remaining allowance from saved prior slides rather than resetting the budget;
recordings with obsolete durations are invalidated. A short narration is not padded with seconds
of silence simply because a longer overall maximum is allowed.

Locally, authored presentations run in the API's background executor; keep the API running.
On the configured Firestore deployment, the same authored pipeline runs through authenticated
Cloud Tasks, one completed slide per request followed by a separate assembly request. A private
Cloud Storage checkpoint preserves completed scripts, narration, recordings, and compositions.
Checksummed, project-confined files are restored before continuation on another instance.
Duplicate task deliveries are rejected by a compare-and-swap claim and attempt/step identity.
Expired worker leases require explicit retry; unsaved paid work is never automatically repeated.
Restarted/interrupted local work also requires explicit Retry; completed slides are reused.
There are three generation attempts, shared account admission with
Product Demo, and no automatic whole-job paid retries. `/generation/presentation` is the full
presentation's status/retry endpoint; `/generation/presentation-preview` remains the short preview.
Completed full presentations with attempts remaining also expose **Rebuild from saved slides**.
This explicit action consumes another generation attempt, keeps existing exports, and reuses valid
saved work. Invalidated copy can require new Google narration calls. Rebuilding is rejected once
the saved timeline has been edited; create a new project instead of overwriting those edits.
Cloud requests require the same task queue and invoker configuration as Product Demo. Final
exports and timeline media use the existing private Cloud Storage/Firestore repositories, not
ephemeral SQLite. Each task has a 900-second delivery deadline and a 960-second recovery lease.
Authenticated recording only receives the current session for exact configured
`DEMO_CAPTURE_AUTH_ORIGINS`; local execution keeps it in memory and cloud execution encrypts it
with `DEMO_JOB_TOKEN_KEY` in private job metadata. It is never saved into the slide-file checkpoint.

## Job visibility and admission

The authenticated `/jobs` page polls saved backend progress every three seconds. It shows both
standard generations, full presentations, and local first-five-slide previews, with activity, safe errors,
saved checkpoints, elapsed time, retries, worker heartbeat, and a rough remaining-time range.
Workers save a heartbeat every ten seconds during work. Missing heartbeats after 45 seconds and
steps with no progress for three minutes are explicitly flagged; no reliable ETA is claimed for
queued, paused, unresponsive, unusually slow, or finished work. Legacy jobs retain their last saved
status but cannot reconstruct activity that was never recorded. Logs retain the latest 500 updates
per job and do not include raw provider responses, credentials, or private capture session data.

Account admission uses the record store's atomic compare-and-swap operation across both pipelines
and API processes. Queued, running, and approval-paused work occupies the single slot. A stopped
job awaiting an explicitly approved retry does not occupy it; retry must acquire the same slot
again. Active projects cannot be deleted. A worker heartbeat is a liveness signal, not proof that
a provider call is making progress. Historical generation times have not yet calibrated estimates.

## Cloud configuration

Generation uses Cloud Tasks with the existing API image, Firestore, and private Cloud Storage. Set `DEMO_GENERATION_TASK_URL` to the API's HTTPS origin, `DEMO_TASK_QUEUE`, `DEMO_TASK_LOCATION`, and `DEMO_TASK_INVOKER_SERVICE_ACCOUNT`. The API runtime needs task-enqueue permission, and the task identity needs invocation permission on the API. The task endpoint also verifies Google's OIDC signature, audience, verified email, and exact service account; user sessions cannot invoke it.

Use a 900-second API request timeout for stage delivery. Keep the services at minimum zero and maximum one instance. Configure the queue's dispatch concurrency to one for the current low-cost deployment. The QHD presentation worker uses the API service's two CPUs and 8 GiB memory allowance; the previous 4 GiB allowance was exhausted during a real slide render. Deployment updates preserve this runtime configuration. Monitor peak memory and generation latency before increasing workload concurrency.

Fixed-duration presentation captures retain the complete observed action sequence and its final result. If navigation exceeds the slide budget, the recording and its interaction timestamps are fitted together to the authored duration. Older cached recordings with missing planned interactions are re-recorded on an explicitly requested rebuild or retry. Product Demo's continuous recording behavior is unchanged.

For authenticated self-capture only, inject `DEMO_JOB_TOKEN_KEY` as a Fernet key from Secret Manager and retain it across revisions. The session is encrypted in the private job input record, never returned in status responses or task payloads. Public website generation does not store a session. Locally a key is created under the ignored artifact directory with restrictive creation permissions. Expired or revoked sessions still cannot authenticate to the captured site.

## Failure semantics

Presentation narration has a planning target of about 144 words per minute. Scripts above the
budget receive grounded text correction before speech; shorter valid scripts are accepted.
Short speech plays continuously at natural speed, then leaves a quiet hold while the product
recording continues. Captions end with the speech instead of retaining the last highlighted
word. Silent holds are measured and logged but do not fail the final export. Clipping, missing
audio, unsafe scripts, and typed-schema failures still block publication.
One corrective audio regeneration for overlong speech is allowed per slide;
raw successful speech is saved before timing checks so it can be reused after interruption.
Accepted saved slides do not need new speech merely because the planning policy changed.

Direction failures save a private receipt with the slide number, attempt, exception category,
validation field/type pairs and source-code check locations, excluding provider payloads and
credentials. Jobs shows the failed slide and check instead of only a generic ValueError.

Product slides may end up to two seconds earlier when previous slides have earned enough extra
time to keep the complete presentation at least 120 seconds. They may extend by up to five
seconds each, within the shared 140-second ceiling. Opening/closing durations are unchanged.
Capture and interaction timing, captions, and the export follow the resolved slide durations.

Only HTTP 429 from the default `gemini-3.1-flash-tts-preview` triggers one fallback request to
`gemini-2.5-flash-preview-tts`, with the same account, voice, and text. The local presentation
adapter then keeps using the fallback for its remaining work. Other provider errors do not
trigger fallback. If the fallback is also limited, generation stops and preserves saved work;
no account/key rotation or unbounded retry occurs. Jobs records the switch and subsequent model
requests; new narration receipts record the model that actually returned the audio.

Model availability and quota details: [Google TTS model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-preview-tts)
and [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Fallback capacity is
not guaranteed and remains subject to its own applicable limits.

Each stage saves a durable checkpoint before queuing the next stage. Cloud media checkpoints reference private object storage, not ephemeral disk. A compare-and-swap lease prevents concurrent duplicate execution. A crash after a provider response but before saving cannot be guaranteed exactly-once: the job pauses for explicit retry rather than silently repeating paid work. A queued dispatch can be safely reissued from the progress page. Do not delete job metadata while work is active.

## Evidence approval

Generation pauses before capture until the owner reviews narration evidence and approves the saved storyboard. The approval fingerprints the storyboard, brief, sources, and product understanding. Script or evidence changes invalidate it. Narration uses the frozen approved capture/script snapshot. Exact excerpt matches, model-attributed sources, user assertions, and unverified statements are distinct labels; none claims independent verification. Source-linked and unsupported statements require explicit acknowledgement. Viewing evidence and approving it make no model calls.

## Rendered review and repair

Quality review sends the actual MP4 through the Google Gen AI SDK using inline video. Limits are 180 seconds, 12 MiB, 1 fps visual sampling, a 90-second provider timeout, one request per attempt, and at most three explicitly retried attempts per export. Successful reviews are reused. No provider-side uploaded file is created. Evidence references are checked against submitted media windows; semantic correctness of an AI observation still needs human judgment.

Optimization proposes up to three deterministic caption/camera edits, requires approval, runs one cycle, and makes at most one follow-up review call. It never rewrites narration meaning or recaptures silently. Original exports remain available and preferred, including when the candidate score falls. Scores are AI assessments rather than measured conversion or business outcomes.

The default tests use fake providers. `RUN_LIVE_VIDEO_REVIEW=1` opts into the small paid video-review smoke; it is not enabled by ordinary test runs.
