# Veyframe Cloud Run service rename

Project: `demodirector-507722`. Region: `us-central1`.

Cloud Run services were copied under the Veyframe names using their exact running
image digests, runtime configuration, service identities and IAM policies.

| Service | Verified revision | URL |
| --- | --- | --- |
| Web | veyframe-web-00001-rxf | https://veyframe-web-5zo4cenn3q-uc.a.run.app |
| API | veyframe-api-00002-6h9 | https://veyframe-api-5zo4cenn3q-uc.a.run.app |
| Worker | veyframe-worker-00001-rsx | https://veyframe-worker-5zo4cenn3q-uc.a.run.app |

The web proxy points to the new API. Capture tasks point to the new worker.
Generation tasks use the new API origin. Authenticated capture permits both the
old web origin and both new Cloud Run web URL forms. Firestore, Storage, queue,
Secret Manager references and service account names are unchanged.

## Verification

- All three services report Ready.
- Judge sign-in, session retrieval, job retrieval and logout passed.
- All seven existing projects are available through the new site.
- Saved Spotlight, Short and Presentation timelines and video range delivery passed.
- Browser playback of the saved Spotlight advanced beyond three seconds at 2560x1440
  with no media error. The editor contains one video player.
- API health returns 200; an unauthenticated worker request is rejected.
- Both deployment scripts passed lint.

Evidence is in `artifacts/cloud-veyframe/`: `services.json`, `verification.json`,
`project-library.png`, and `saved-video-playback.png`.
This verifies the renamed service wiring and access to existing media; it does not
claim a fresh full video generation was run during this service rename.

## Compatibility and deployment

The previous services remain intact for old links, queued tasks and rollback.
No projects, exports, storage resources or other Google Cloud projects were deleted.
In-app branding and container/package names have not been changed by this operation.

`cloudbuild.deploy.yaml` now targets the new service names; this is a local change
pending commit/push. The current project has no Cloud Build triggers in global or
us-central1. Automatic GitHub deployment was not configured by this operation.

The create script intentionally fails if target names already exist. Do not rerun
`scripts/rebrand-cloud-services.py --apply` after this successful cutover. Use image-only
updates on the existing Veyframe services for subsequent deployments.
