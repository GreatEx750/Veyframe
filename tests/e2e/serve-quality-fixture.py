"""Provider-free local browser fixture. Bind only to loopback; never deploy this server."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/api/tests"))
fixture_root = Path(tempfile.mkdtemp(prefix="demodirector-quality-ui-"))
os.environ["DEMO_DATABASE_PATH"] = str(fixture_root / "app.sqlite")
os.environ["DEMO_METADATA_BACKEND"] = "sqlite"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_CLOUD_PROJECT"] = ""
os.environ["PARALLEL_API_KEY"] = ""

from demodirector_api.auth import AuthService, AuthSettings, FakeIdentityProvider, SQLiteAuthRepository
from demodirector_api.evidence import EvidenceService
from demodirector_api.exports import ExportService, SQLiteExportRepository
from demodirector_api.generation_jobs import GenerationStages
from demodirector_api.google_ai import FakeGoogleAIService, GoogleAISettings
from demodirector_api.main import create_app
from demodirector_api.optimization import OptimizationService
from demodirector_api.video_reviews import FakeVideoCritic, VideoReviewService
from demodirector_contracts import RenderConfig, RenderResult, SignupRequest, Timeline
from test_exports import media_binary
from test_generation_jobs import jobs_fixture
from test_video_reviews import critic_output

os.environ["FFPROBE_PATH"] = media_binary("ffprobe")
jobs = jobs_fixture(fixture_root)
s = jobs.generation
auth = AuthService(FakeIdentityProvider(verified=True), SQLiteAuthRepository(fixture_root / "auth.sqlite"), AuthSettings(required=True))
account = auth.signup(SignupRequest(email="reviewer@example.test", password="fixture-password-only"))
project = s.projects.get("project-one-click")
assert project is not None
s.projects.update(project.model_copy(update={"owner_user_id": account.session.user.user_id}))


class FixtureRenderer:
    def render(self, timeline: Timeline, config: RenderConfig) -> RenderResult:
        path = fixture_root / config.output_filename
        shutil.copyfile(ROOT / "artifacts/verification/golden-export-20s.mp4", path)
        return RenderResult(status="succeeded", output_path=str(path), duration_ms=20000,
                            width=1920, height=1080, has_video=True, has_audio=True)


exports = ExportService(FixtureRenderer(), SQLiteExportRepository(fixture_root / "exports.sqlite"),
                        fixture_root, records=jobs.records, timelines=s.timelines)
s.exports = exports
evidence = EvidenceService(s.projects, s.research_sources, s.storyboards, s.understandings, jobs.records)
assert isinstance(jobs.executor, GenerationStages)
jobs.executor.approval = evidence
reviews = VideoReviewService(exports, jobs.records, FakeVideoCritic(critic_output()))
app = create_app(repository=s.projects, research_repository=s.research_sources,
                 inspection_repository=s.inspections, product_understanding_repository=s.understandings,
                 storyboard_repository=s.storyboards, timeline_repository=s.timelines,
                 auth_service=auth, ai_service=FakeGoogleAIService({}),
                 ai_settings=GoogleAISettings("fixture", None, None, "us-central1"))
app.state.generation_jobs = jobs
app.state.evidence_service = evidence
app.state.export_service = exports
app.state.video_review_service = reviews
app.state.optimization_service = OptimizationService(reviews, s.timelines, jobs.records)
job = jobs.start(project.id)


def run_worker() -> None:
    while True:
        jobs.local_tick()
        threading.Event().wait(0.5)


if __name__ == "__main__":
    import uvicorn
    threading.Thread(target=run_worker, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8100)
