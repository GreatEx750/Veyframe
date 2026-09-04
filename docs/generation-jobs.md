# Durable generation and video quality

## Local development

Run the API and web app normally. In a separate terminal, from the repository root run:

```powershell
node scripts/python-runner.mjs -m demodirector_api.job_worker
```

The worker reads the same SQLite database and artifact directory as the API. Keep those paths consistent. Closing the browser does not stop the worker. Stopping the worker preserves completed checkpoints; restarting it resumes queued work. Interrupted paid stages require explicit approval before retry. There is a maximum of three attempts per stage.

## Cloud configuration

Generation uses Cloud Tasks with the existing API image, Firestore, and private Cloud Storage. Set `DEMO_GENERATION_TASK_URL` to the API's HTTPS origin, `DEMO_TASK_QUEUE`, `DEMO_TASK_LOCATION`, and `DEMO_TASK_INVOKER_SERVICE_ACCOUNT`. The API runtime needs task-enqueue permission, and the task identity needs invocation permission on the API. The task endpoint also verifies Google's OIDC signature, audience, verified email, and exact service account; user sessions cannot invoke it.

Use a 900-second API request timeout for stage delivery. Keep the services at minimum zero and maximum one instance. No Cloud Run configuration is changed by the local implementation. Configure the queue's dispatch concurrency to one for the current low-cost deployment. The API must have sufficient CPU/memory for the same browser/render work it previously performed synchronously.

For authenticated self-capture only, inject `DEMO_JOB_TOKEN_KEY` as a Fernet key from Secret Manager and retain it across revisions. The session is encrypted in the private job input record, never returned in status responses or task payloads. Public website generation does not store a session. Locally a key is created under the ignored artifact directory with restrictive creation permissions. Expired or revoked sessions still cannot authenticate to the captured site.

## Failure semantics

Each stage saves a durable checkpoint before queuing the next stage. Cloud media checkpoints reference private object storage, not ephemeral disk. A compare-and-swap lease prevents concurrent duplicate execution. A crash after a provider response but before saving cannot be guaranteed exactly-once: the job pauses for explicit retry rather than silently repeating paid work. A queued dispatch can be safely reissued from the progress page. Do not delete job metadata while work is active.

## Evidence approval

Generation pauses before capture until the owner reviews narration evidence and approves the saved storyboard. The approval fingerprints the storyboard, brief, sources, and product understanding. Script or evidence changes invalidate it. Narration uses the frozen approved capture/script snapshot. Exact excerpt matches, model-attributed sources, user assertions, and unverified statements are distinct labels; none claims independent verification. Source-linked and unsupported statements require explicit acknowledgement. Viewing evidence and approving it make no model calls.

## Rendered review and repair

Quality review sends the actual MP4 through the Google Gen AI SDK using inline video. Limits are 180 seconds, 12 MiB, 1 fps visual sampling, a 90-second provider timeout, one request per attempt, and at most three explicitly retried attempts per export. Successful reviews are reused. No provider-side uploaded file is created. Evidence references are checked against submitted media windows; semantic correctness of an AI observation still needs human judgment.

Optimization proposes up to three deterministic caption/camera edits, requires approval, runs one cycle, and makes at most one follow-up review call. It never rewrites narration meaning or recaptures silently. Original exports remain available and preferred, including when the candidate score falls. Scores are AI assessments rather than measured conversion or business outcomes.

The default tests use fake providers. `RUN_LIVE_VIDEO_REVIEW=1` opts into the small paid video-review smoke; it is not enabled by ordinary test runs.
