# DemoDirector Google Cloud deployment

The production boundary uses three Cloud Run services in `us-central1`. The public web service
proxies only to the public API and runs under a dedicated identity with no project roles. The API
stores project metadata in Firestore and enqueues capture requests in Cloud Tasks. A private
worker accepts only authenticated task requests and writes capture artifacts to Cloud Storage.
Gemini, Parallel, and Identity Platform credentials are mounted from Secret Manager and are never
included in the web image.

All services use `--min-instances=0 --max-instances=1 --cpu=1` to minimize idle cost. Web and API
use 512 MiB. The private Chromium worker uses 768 MiB, the lowest tested limit that completes a
20-second capture reliably; memory is billed only while its scale-to-zero instance is active. The
worker has no public invoker binding.

## One-time infrastructure

```powershell
gcloud services enable run.googleapis.com firestore.googleapis.com storage.googleapis.com cloudtasks.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com identitytoolkit.googleapis.com --project habiwatch
gcloud firestore databases create --database=demodirector --location=us-central1 --type=firestore-native --project habiwatch
gcloud storage buckets create gs://habiwatch-demodirector-artifacts --project=habiwatch --location=us-central1 --default-storage-class=STANDARD --uniform-bucket-level-access
gcloud tasks queues create demodirector-jobs --location=us-central1 --project=habiwatch --max-concurrent-dispatches=1 --max-dispatches-per-second=1
```

Initialize Identity Platform for the billing-enabled project, enable the email/password provider,
create an API key restricted to `identitytoolkit.googleapis.com`, and store it as
`demodirector-identity-platform-api-key` in Secret Manager. Hosted deployments require verified
email before issuing a customer session.

Create `demodirector-web`, `demodirector-api`, `demodirector-worker`, and `demodirector-tasks`
service accounts. Give the web identity no project roles. Grant the API only Datastore User, Cloud
Tasks Enqueuer, and Secret Manager Secret Accessor. Grant the worker Storage Object Creator on the
artifact bucket. Grant the task identity Cloud Run Invoker on the worker, and let only the API
service account act as that task identity.

## Build and deploy

```powershell
gcloud builds submit --tag us-central1-docker.pkg.dev/habiwatch/cloud-run-source-deploy/demodirector-web:latest --project habiwatch .
gcloud run deploy demodirector-web --image us-central1-docker.pkg.dev/habiwatch/cloud-run-source-deploy/demodirector-web:latest --region us-central1 --project habiwatch --service-account demodirector-web@habiwatch.iam.gserviceaccount.com --allow-unauthenticated --min-instances 0 --max-instances 1 --cpu 1 --memory 512Mi --set-env-vars API_BASE_URL=API_URL
gcloud builds submit --config cloudbuild.worker.yaml --project habiwatch .
gcloud run deploy demodirector-worker --image us-central1-docker.pkg.dev/habiwatch/cloud-run-source-deploy/demodirector-worker:latest --region us-central1 --project habiwatch --service-account demodirector-worker@habiwatch.iam.gserviceaccount.com --no-allow-unauthenticated --min-instances 0 --max-instances 1 --cpu 1 --memory 768Mi --set-env-vars DEMO_ARTIFACT_BUCKET=habiwatch-demodirector-artifacts
gcloud builds submit --config cloudbuild.api.yaml --project habiwatch .
gcloud run deploy demodirector-api --image us-central1-docker.pkg.dev/habiwatch/cloud-run-source-deploy/demodirector-api:latest --region us-central1 --project habiwatch --service-account demodirector-api@habiwatch.iam.gserviceaccount.com --allow-unauthenticated --min-instances 0 --max-instances 1 --cpu 1 --memory 512Mi --set-env-vars GOOGLE_CLOUD_PROJECT=habiwatch,DEMO_METADATA_BACKEND=firestore,DEMO_FIRESTORE_DATABASE=demodirector,DEMO_TASK_LOCATION=us-central1,DEMO_TASK_QUEUE=demodirector-jobs,DEMO_WORKER_URL=WORKER_URL,DEMO_TASK_INVOKER_SERVICE_ACCOUNT=demodirector-tasks@habiwatch.iam.gserviceaccount.com,DEMO_AUTH_REQUIRED=true,DEMO_AUTH_REQUIRE_VERIFIED_EMAIL=true,DEMO_JUDGE_ENABLED=true --set-secrets GEMINI_API_KEY=demodirector-gemini-api-key:latest,PARALLEL_API_KEY=demodirector-parallel-api-key:latest,IDENTITY_PLATFORM_API_KEY=demodirector-identity-platform-api-key:latest
```

Agent Engine is not required for the current implementation: the ADK coordinator is request-bound
inside the API and has no durable agent session of its own. If durable ADK sessions are introduced,
deploy that coordinator to Agent Engine rather than adding state to Cloud Run.

## Smoke verification

Check `/health`, complete signup/verification/login/logout with a disposable account, enter the
one-click judge demo, and verify its isolated 20-second project is read-only. Then create and
retrieve a customer project through the hosted web/API, enqueue one fixture capture, and confirm a
`gs://habiwatch-demodirector-artifacts/captures/...` object exists. Inspect the web service
environment and built JavaScript to confirm no credential name has a public `NEXT_PUBLIC_`
equivalent.
