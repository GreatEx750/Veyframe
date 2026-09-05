# DemoDirector

DemoDirector turns a public website and creative brief into an editable, narrated product demo.

## Repository layout

- `apps/web`: Next.js customer application
- `services/api`: FastAPI application API
- `services/worker`: background worker package
- `packages/contracts`: shared TypeScript contracts
- `tests/e2e`: browser-level product journeys

## Requirements

- Node.js 20.9 or newer
- Python 3.12 or newer

## Local setup

```bash
npm install
python -m venv .venv
```

Activate the virtual environment, then install Python dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` and provide only the credentials needed by the feature you are running.

## Development

```bash
npm run dev
```

The web app runs at `http://localhost:3000` and the API runs at `http://localhost:8000`.
This command also starts the generation worker. Keep it running while demos generate.

## Authentication

Hosted customer accounts use Google Identity Platform email/password authentication. The web
service keeps the application session in an HTTP-only secure cookie, while the API stores only a
hash of the opaque session token. Set `IDENTITY_PLATFORM_API_KEY`, enable
`DEMO_AUTH_REQUIRED=true`, and require verified email in hosted environments. Local tests use a
provider-free deterministic identity adapter and never call Identity Platform.

Judges can use the one-click Judge Demo from the login page. It creates an isolated, short-lived,
read-only sandbox backed by pre-generated fixture data, so evaluation does not spend Gemini or
Parallel quota.

## Quality checks

```bash
npm test
npm run lint
npm run typecheck
npm run compliance
```

## Runtime architecture

DemoDirector uses a Next.js frontend, FastAPI services, Google Cloud AI and Gemini for AI capabilities, Google ADK for agent workflows, Parallel Search for runtime web grounding, Playwright for browser capture, and FFmpeg for deterministic media rendering.

## Hosted demo

The scale-to-zero Cloud Run deployment is available at
https://demodirector-web-cq5t2gao5q-uc.a.run.app/. Choose **Enter Judge Demo** for immediate,
credential-free evaluation of the preloaded workflow.

## Generation, review, and approval

Demo generation runs as a durable job. Open **Jobs** in the sidebar to see the current step,
timestamped activity, worker heartbeat, saved stages, and estimated remaining time.
One generation per account may be queued, running, or waiting for storyboard approval.
Failed jobs require explicit retry approval; estimates are planning ranges, not deadlines.
If you start the API and web app separately instead of using `npm run dev`, also start the worker:

```powershell
npm run dev:worker
```

The editor's Quality tool reviews a saved export and proposes bounded, approved camera/caption repairs. Successful reviews are cached; ordinary tests make no paid calls. See [generation and cloud setup](docs/generation-jobs.md) before deploying this version, especially the API-targeted task queue and authenticated-capture encryption key.
