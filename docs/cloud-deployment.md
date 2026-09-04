# DemoDirector Google Cloud deployment

The production boundary uses three Cloud Run services in `us-central1`. The public web service
proxies only to the public API and runs under a dedicated identity with no project roles. The API
stores project, research, inspection, storyboard, timeline, and export metadata in Firestore and
enqueues capture requests in Cloud Tasks. Generated source media and completed MP4 exports are
stored in Cloud Storage so projects remain playable after Cloud Run scales down or deploys a new
revision. A private worker accepts only authenticated task requests and writes capture artifacts
to the same private bucket.
Gemini, Parallel, and Identity Platform credentials are mounted from Secret Manager and are never
included in the web image.

All services use `--min-instances=0 --max-instances=1` to minimize idle cost. The web uses
768 MiB; a live post-deploy project/video load exceeded 512 MiB by 1 MiB. The API uses 2 CPUs,
4 GiB, and concurrency 2 because one-click generation currently runs its
inspector, capture, narration, and renderer in the request-bound API process; the second request
slot keeps lightweight session checks available during capture. The private Chromium worker uses
2 GiB. Memory is billed only while each scale-to-zero instance is active. The worker has no
public invoker binding.

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
service accounts. Give the web identity no project roles. Grant the API Datastore User, Cloud
Tasks Enqueuer, Secret Manager Secret Accessor, and Storage Object User on the artifact bucket.
The object role is required to upload completed exports and restore them for authenticated
streaming. Grant the worker Storage Object Creator on the artifact bucket. Grant the task identity
Cloud Run Invoker on the worker, and let only the API service account act as that task identity.

```powershell
gcloud storage buckets add-iam-policy-binding gs://habiwatch-demodirector-artifacts --member=serviceAccount:demodirector-api@habiwatch.iam.gserviceaccount.com --role=roles/storage.objectUser
```

## Build and deploy

```powershell
gcloud builds submit --tag us-central1-docker.pkg.dev/habiwatch/cloud-run-source-deploy/demodirector-web:latest --project habiwatch .
gcloud run deploy demodirector-web --image us-central1-docker.pkg.dev/habiwatch/cloud-run-source-deploy/demodirector-web:latest --region us-central1 --project habiwatch --service-account demodirector-web@habiwatch.iam.gserviceaccount.com --allow-unauthenticated --min-instances 0 --max-instances 1 --cpu 1 --memory 768Mi --set-env-vars API_BASE_URL=API_URL
gcloud builds submit --config cloudbuild.worker.yaml --project habiwatch .
gcloud run deploy demodirector-worker --image us-central1-docker.pkg.dev/habiwatch/cloud-run-source-deploy/demodirector-worker:latest --region us-central1 --project habiwatch --service-account demodirector-worker@habiwatch.iam.gserviceaccount.com --no-allow-unauthenticated --min-instances 0 --max-instances 1 --cpu 1 --memory 2Gi --set-env-vars DEMO_ARTIFACT_BUCKET=habiwatch-demodirector-artifacts
gcloud builds submit --config cloudbuild.api.yaml --project habiwatch .
gcloud run deploy demodirector-api --image us-central1-docker.pkg.dev/habiwatch/cloud-run-source-deploy/demodirector-api:latest --region us-central1 --project habiwatch --service-account demodirector-api@habiwatch.iam.gserviceaccount.com --allow-unauthenticated --min-instances 0 --max-instances 1 --concurrency 2 --timeout 900 --cpu 2 --memory 4Gi --set-env-vars GOOGLE_CLOUD_PROJECT=habiwatch,DEMO_METADATA_BACKEND=firestore,DEMO_FIRESTORE_DATABASE=demodirector,DEMO_ARTIFACT_BUCKET=habiwatch-demodirector-artifacts,DEMO_TASK_LOCATION=us-central1,DEMO_TASK_QUEUE=demodirector-jobs,DEMO_WORKER_URL=WORKER_URL,DEMO_TASK_INVOKER_SERVICE_ACCOUNT=demodirector-tasks@habiwatch.iam.gserviceaccount.com,DEMO_AUTH_REQUIRED=true,DEMO_AUTH_REQUIRE_VERIFIED_EMAIL=true,DEMO_JUDGE_ENABLED=true,DEMO_CAPTURE_AUTH_ORIGINS=https://demodirector-web-cq5t2gao5q-uc.a.run.app --set-secrets GEMINI_API_KEY=demodirector-gemini-api-key:latest,PARALLEL_API_KEY=demodirector-parallel-api-key:latest,IDENTITY_PLATFORM_API_KEY=demodirector-identity-platform-api-key:latest
```

Agent Engine is not required for the current implementation: the ADK coordinator is request-bound
inside the API and has no durable agent session of its own. If durable ADK sessions are introduced,
deploy that coordinator to Agent Engine rather than adding state to Cloud Run.

## Smoke verification

Check `/health`, complete signup/verification/login/logout with a disposable account, enter the
one-click judge demo, play its packaged 20-second Northstar fixture, and verify its isolated project
is read-only. Then create and retrieve a customer project through the hosted web/API, generate an
export, deploy a new API revision, and confirm the same project timeline and MP4 still load. Verify
the bucket contains both `timeline-media/...` and `exports/...` objects. Inspect the web service
environment and built JavaScript to confirm no credential name has a public `NEXT_PUBLIC_`
equivalent.

## Continuous deployment from GitHub

`cloudbuild.deploy.yaml` is the push deployment pipeline for the `main` branch. It builds the web,
API, and worker images in parallel, pushes commit-tagged images to Artifact Registry, and updates
only the image on each existing Cloud Run service. Runtime environment variables, Secret Manager
references, service identities, scaling, and ingress settings remain owned by the Cloud Run service
configuration.

The trigger runs as `demodirector-build@habiwatch.iam.gserviceaccount.com`. That identity needs
Artifact Registry Writer, Cloud Run Developer, and Logs Writer on the project, plus Service Account User
on each of the three DemoDirector runtime identities. Repository access is granted through the
Google Cloud Build GitHub App; no GitHub or Google credential is stored in this repository.
