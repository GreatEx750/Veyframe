from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from demodirector_api.generation_jobs import (
    CaptureTokenVault,
    CloudGenerationDispatcher,
    GenerationJobs,
    GenerationStages,
    JobConflict,
    LocalJobDispatcher,
)
from demodirector_api.longform_director import (
    LongFormDirector,
    LongFormGatewayResult,
)
from demodirector_api.records import SQLiteRecordStore
from demodirector_contracts import (
    InteractionEvent,
    ResearchSource,
    Scene,
    SceneCaptureResult,
    Viewport,
)
from demodirector_contracts.attention import (
    AnimatedCallout,
    AttentionPlan,
    AttentionRequest,
    AttentionRunStep,
    TargetObservation,
)
from demodirector_contracts.jobs import GenerationJob
from demodirector_contracts.longform import (
    LongFormDirectionRequest,
    LongFormVideoPlan,
)
from demodirector_contracts.motion import (
    ADKMotionRun,
    MotionCue,
    MotionDirectionPlan,
    MotionDirectionRequest,
    MotionTokenSet,
)
from demodirector_contracts.style import (
    StyleDirectionDecision,
    StyleDirectionPlan,
    StyleDirectionRequest,
    StyleRunStep,
    VariantSceneDefaults,
)
from test_generation import FakeCaptureWorker, build_service

from test_support.longform import longform_plan


class FakeMotionDirector:
    model_name = "gemini-test"
    agent_name = "demodirector_motion_director"

    def __init__(self) -> None:
        self.plans: dict[str, MotionDirectionPlan] = {}
        self.runs: dict[str, ADKMotionRun] = {}
        self.calls = 0

    def direct(
        self,
        request: MotionDirectionRequest,
        context: dict[str, object],
        *,
        retry_count: int = 0,
    ) -> tuple[ADKMotionRun, MotionDirectionPlan]:
        del context
        self.calls += 1
        now = datetime.now(UTC)
        plan = MotionDirectionPlan(
            id=f"motion-plan-{request.job_id}",
            project_id=request.project_id,
            job_id=request.job_id,
            run_id=f"motion-run-{request.job_id}",
            request_fingerprint="b" * 64,
            design_tokens=MotionTokenSet(),
            duration_ms=request.duration_ms,
            scene_ids=request.scene_ids,
            product_clip_refs=request.product_clip_refs,
            summary="Keep the product visible.",
            cues=[
                MotionCue(
                    id="motion-cue-1",
                    scene_id=request.scene_ids[0],
                    primitive="fade_slide",
                    layer="transition",
                    start_ms=0,
                    end_ms=600,
                    easing="standard",
                    text="Show the working product",
                    product_clip_ref=request.product_clip_refs[0],
                )
            ],
            created_at=now,
        )
        run = ADKMotionRun(
            id=plan.run_id,
            project_id=request.project_id,
            job_id=request.job_id,
            session_id=f"motion-session-{request.job_id}",
            agent_name="demodirector_motion_director",
            model=self.model_name,
            status="succeeded",
            started_at=now,
            completed_at=now,
            elapsed_ms=0,
            retry_count=retry_count,
            workflow_runs=1,
            input_artifact_ids=[f"storyboard:{request.storyboard_id}"],
            output_plan_id=plan.id,
            validation_status="passed",
            message="Validated Google ADK motion direction saved.",
        )
        self.plans[request.job_id] = plan
        self.runs[request.job_id] = run
        return run, plan

    def plan(self, project_id: str, job_id: str) -> MotionDirectionPlan:
        plan = self.plans[job_id]
        if plan.project_id != project_id:
            raise KeyError("Motion direction plan not found")
        return plan

    def run(self, project_id: str, job_id: str) -> ADKMotionRun:
        run = self.runs[job_id]
        if run.project_id != project_id:
            raise KeyError("ADK motion run not found")
        return run


class FakeAttentionDirector:
    model_name = "gemini-test"
    agent_name = "demodirector_attention_director"

    def direct(
        self,
        request: AttentionRequest,
        targets: list[TargetObservation],
        context: dict[str, object],
    ) -> tuple[AttentionRunStep, AttentionPlan]:
        del context
        now = datetime.now(UTC)
        callouts = []
        if targets:
            callouts.append(
                AnimatedCallout(
                    id="callout-1",
                    target_id=targets[0].id,
                    callout_type="label_connector",
                    placement="top_left",
                    start_ms=1_000,
                    end_ms=2_000,
                    text="Select this control",
                )
            )
        plan = AttentionPlan(
            id=f"attention-plan-{request.job_id}",
            project_id=request.project_id,
            job_id=request.job_id,
            parent_run_id=request.parent_run_id,
            duration_ms=request.duration_ms,
            targets=targets,
            narration_statement_ids=request.narration_statement_ids,
            summary="Guide attention to observed controls.",
            callouts=callouts,
            caption_emphasis=[],
            created_at=now,
        )
        run = AttentionRunStep(
            id=f"attention-run-{request.job_id}",
            project_id=request.project_id,
            job_id=request.job_id,
            parent_run_id=request.parent_run_id,
            session_id=f"attention-session-{request.job_id}",
            agent_name="demodirector_attention_director",
            model=self.model_name,
            status="succeeded",
            started_at=now,
            completed_at=now,
            elapsed_ms=0,
            workflow_runs=1,
            input_target_count=len(targets),
            proposed_cue_count=len(callouts),
            accepted_cue_count=len(callouts),
            validation_status="passed",
            output_plan_id=plan.id,
            message="Validated Google ADK attention plan saved.",
        )
        return run, plan


class FakeStyleDirector:
    model_name = "gemini-test"
    agent_name = "demodirector_style_director"

    def direct(
        self,
        request: StyleDirectionRequest,
        context: dict[str, object],
    ) -> tuple[StyleRunStep, StyleDirectionPlan]:
        del context
        now = datetime.now(UTC)
        plan = StyleDirectionPlan(
            id=f"style-plan-{request.job_id}",
            project_id=request.project_id,
            job_id=request.job_id,
            parent_run_id=request.parent_run_id,
            audience=request.audience,
            purpose=request.purpose,
            scene_ids=request.scene_ids,
            allowed_evidence_refs=request.evidence_refs,
            recommendation_evidence_refs=request.evidence_refs[:1],
            rationale="Keep the working product large and motion restrained.",
            decision=StyleDirectionDecision(
                recommended_variant="product_spotlight",
                selected_variant="product_spotlight",
                outcome="recommended",
                decided_at=now,
            ),
            defaults=[
                VariantSceneDefaults(
                    variant_id="editorial_story",
                    product_scale="composed",
                    callout_density="medium",
                    motion_pace="deliberate",
                ),
                VariantSceneDefaults(
                    variant_id="product_spotlight",
                    product_scale="large",
                    callout_density="low",
                    motion_pace="calm",
                ),
                VariantSceneDefaults(
                    variant_id="technical_proof",
                    product_scale="evidence_focused",
                    callout_density="medium",
                    motion_pace="precise",
                ),
            ],
            created_at=now,
        )
        run = StyleRunStep(
            id=f"style-run-{request.job_id}",
            project_id=request.project_id,
            job_id=request.job_id,
            parent_run_id=request.parent_run_id,
            session_id=f"style-session-{request.job_id}",
            agent_name="demodirector_style_director",
            model=self.model_name,
            status="succeeded",
            started_at=now,
            completed_at=now,
            elapsed_ms=0,
            workflow_runs=1,
            validation_status="passed",
            output_plan_id=plan.id,
            message="Validated Google ADK style recommendation saved.",
        )
        return run, plan


class FakeLongFormGateway:
    model_name = "gemini-test"

    def __init__(self) -> None:
        self.context: dict[str, object] | None = None

    def execute(
        self,
        request: LongFormDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> LongFormGatewayResult:
        del session_id
        self.context = context
        payload = longform_plan().model_dump(mode="json")
        source_ref = request.evidence_refs[0]
        clip_ref = request.product_clip_refs[0]
        payload.update({
            "id": request.plan_id,
            "project_id": request.project_id,
            "job_id": request.job_id,
            "adk_run_id": request.run_id,
            "parent_motion_run_id": request.parent_motion_run_id,
            "visual_variant": request.visual_variant,
            "research_status": request.research_status,
            "evidence_refs": request.evidence_refs,
            "parallel_source_refs": request.parallel_source_refs,
            "product_clip_refs": request.product_clip_refs,
            "target_ids": request.target_ids,
        })
        for section in payload["sections"]:
            section["source_refs"] = [source_ref]
            section["product_clip_ref"] = clip_ref
        for beat in payload["beats"]:
            beat["source_refs"] = [source_ref]
            beat["product_clip_ref"] = clip_ref
            beat["target_id"] = None
        for chapter in payload["chapters"]:
            chapter["project_id"] = request.project_id
            chapter["project_state_ref"] = "storyboard:storyboard-one-click:1"
            chapter["cursor_continuity_key"] = f"cursor:{request.project_id}"
        plan = LongFormVideoPlan.model_validate(payload)
        refs = (source_ref,)
        return LongFormGatewayResult(
            output=plan.model_dump_json(),
            evidence_reads=1,
            steps=(
                ("narrative", refs),
                ("template", refs),
                ("attention", refs),
                ("style", refs),
            ),
        )


class LongFormCaptureWorker:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.scenes: list[Any] = []

    def capture_scene(
        self,
        scene: Scene,
        *,
        session_token: str | None = None,
    ) -> SceneCaptureResult:
        del session_token
        self.scenes.append(scene)
        output = self.root / f"{len(self.scenes)}-{scene.id}.webm"
        output.write_bytes(f"capture:{scene.id}".encode())
        duration_ms = round(scene.duration_seconds * 1_000)
        return SceneCaptureResult(
            scene_id=scene.id,
            status="succeeded",
            retryable=False,
            duration_ms=duration_ms,
            raw_clip_path=str(output),
            interaction_events=[InteractionEvent(
                timestamp_ms=min(1_000, max(0, duration_ms - 1)),
                event_type="click",
                locator="button:Create",
                x=640,
                y=360,
                viewport=Viewport(width=1280, height=720),
            )],
        )


def longform_jobs_fixture(
    tmp_path: Path,
) -> tuple[GenerationJobs, LongFormCaptureWorker, FakeLongFormGateway]:
    capture = LongFormCaptureWorker(tmp_path)
    service, projects, _, _ = build_service(tmp_path, capture)
    project = projects.get("project-one-click")
    assert project is not None
    projects.update(project.model_copy(update={"requested_duration_seconds": 180}))
    service.research_sources.replace_partner_sources(
        project.id,
        [ResearchSource.model_validate({
            "id": "parallel-source-1",
            "project_id": project.id,
            "title": "Independent product context",
            "url": "https://example.com/product-context",
            "snippet": "A saved result returned directly by Parallel Search.",
            "source_type": "partner_search",
            "retrieved_at": datetime.now(UTC),
        })],
    )
    records = SQLiteRecordStore(tmp_path / "longform-jobs.sqlite")
    vault = CaptureTokenVault(tmp_path, False)
    gateway = FakeLongFormGateway()
    jobs = GenerationJobs(
        records,
        GenerationStages(
            service,
            records,
            vault,
            motion_director=FakeMotionDirector(),
            attention_director=FakeAttentionDirector(),
            style_director=FakeStyleDirector(),
            longform_director=LongFormDirector(records, gateway),
        ),
        LocalJobDispatcher(),
        service,
        vault,
    )
    return jobs, capture, gateway


def jobs_fixture(tmp_path: Path) -> GenerationJobs:
    service, _, _, _ = build_service(tmp_path, FakeCaptureWorker())
    records = SQLiteRecordStore(tmp_path / "jobs.sqlite")
    vault = CaptureTokenVault(tmp_path, False)
    return GenerationJobs(
        records,
        GenerationStages(
            service,
            records,
            vault,
            motion_director=FakeMotionDirector(),
            attention_director=FakeAttentionDirector(),
            style_director=FakeStyleDirector(),
        ),
        LocalJobDispatcher(),
        service,
        vault,
    )


def test_stage_checkpoints_survive_reconstruction(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.start("project-one-click")
    assert job.status == "queued"
    assert jobs.start(job.project_id).id == job.id
    for expected in [
        "research",
        "understanding",
        "storyboard",
        "motion",
        "capture",
        "attention",
        "style",
    ]:
        job = jobs.step(job.id)
        assert job.stage == expected and job.status == "queued"
    restored = GenerationJobs(
        SQLiteRecordStore(tmp_path / "jobs.sqlite"),
        jobs.executor,
        LocalJobDispatcher(),
        jobs.generation,
        jobs.vault,
    )
    while job.status != "succeeded":
        job = restored.step(job.id)
    assert len(job.completed_stages) == 10 and job.export_id == "export-one-click"
    assert restored.step(job.id) == job
    assert len(jobs.generation.capture_worker.scenes) == 1  # type: ignore[attr-defined]
    with pytest.raises(KeyError):
        restored.get(job.id, "foreign")


def test_validated_motion_plan_is_queryable_and_bound_to_timeline(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.start("project-one-click")
    while job.stage != "capture":
        job = jobs.step(job.id)

    plan = jobs.motion_plan(job.project_id)
    run = jobs.motion_run(job.project_id)
    assert run.output_plan_id == plan.id
    assert run.workflow_runs == 1

    while job.status != "succeeded":
        job = jobs.step(job.id)
    history = jobs.generation.timelines.current(job.project_id)
    assert history is not None
    assert history.current.timeline.motion_plan_id == plan.id
    assert history.current.timeline.motion_design_version == plan.design_tokens.version
    assert history.current.timeline.attention_plan_id == f"attention-plan-{job.id}"
    assert history.current.timeline.style_plan_id == f"style-plan-{job.id}"
    assert history.current.timeline.visual_variant == "product_spotlight"


def test_two_minute_presentation_mode_is_snapshotted_without_longform_inference(
    tmp_path: Path,
) -> None:
    jobs = jobs_fixture(tmp_path)
    project = jobs.generation.projects.get("project-one-click")
    assert project is not None
    jobs.generation.projects.update(
        project.model_copy(
            update={
                "demo_mode": "presentation_demo",
                "requested_duration_seconds": 120,
                "zoom_enabled": False,
            }
        )
    )

    job = jobs.start(project.id)
    while job.status != "succeeded":
        job = jobs.step(job.id)

    state = jobs.generation.timelines.current(project.id)
    assert state is not None
    timeline = state.current.timeline
    assert timeline.duration_ms == 120_000
    assert timeline.demo_mode == "presentation_demo"
    assert timeline.presentation_pack_id == "presentation-story@1"
    assert timeline.presentation.zoom_enabled is False
    assert timeline.long_form_plan_id is None
    assert timeline.zoom_clips
    assert any(event.event_type == "click" for event in timeline.cursor_events)


def test_three_minute_generation_consumes_adk_plan_and_keeps_chapters_restartable(
    tmp_path: Path,
) -> None:
    jobs, capture, gateway = longform_jobs_fixture(tmp_path)
    job = jobs.start("project-one-click")
    while job.status != "succeeded":
        job = jobs.step(job.id)

    plan = jobs.longform_plan(job.project_id)
    assert plan.duration_ms == 180_000
    assert plan.parallel_source_refs == ["source:parallel-source-1"]
    assert gateway.context is not None
    assert gateway.context["direct_parallel_source_refs"] == plan.parallel_source_refs

    state = jobs.generation.timelines.current(job.project_id)
    assert state is not None
    timeline = state.current.timeline
    assert timeline.duration_ms == 180_000
    assert timeline.long_form_plan_id == plan.id
    assert [(clip.start_ms, clip.end_ms) for clip in timeline.scene_clips] == [
        (chapter.start_ms, chapter.end_ms) for chapter in plan.chapters
    ]
    assert len(capture.scenes) == len(plan.chapters) + 1
    trace = jobs.trace(job.project_id)
    render_trace = next(stage for stage in trace.stages if stage.kind == "render")
    assert any(
        item.key == "adk_plan_consumed" and item.value == 1
        for item in render_trace.contributions
    )
    before = jobs.longform_checkpoints(job.project_id)
    assert [item.status for item in before] == ["captured"] * len(plan.chapters)
    prior_sources = [clip.source_uri for clip in timeline.scene_clips]

    retried = jobs.retry_longform_chapter(job.project_id, plan.chapters[1].id)
    after = jobs.longform_checkpoints(job.project_id)
    assert retried.status == "captured" and retried.attempt == 1
    assert after[0] == before[0] and after[2:] == before[2:]
    updated_state = jobs.generation.timelines.current(job.project_id)
    assert updated_state is not None and updated_state.current.version == 2
    updated_sources = [clip.source_uri for clip in updated_state.current.timeline.scene_clips]
    assert updated_sources[0] == prior_sources[0]
    assert updated_sources[1] != prior_sources[1]
    assert updated_sources[2:] == prior_sources[2:]


def test_style_switch_and_scene_override_are_provider_free_and_undoable(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.start("project-one-click")
    while job.status != "succeeded":
        job = jobs.step(job.id)
    director = jobs.executor.style_director  # type: ignore[attr-defined]
    original = jobs.style_plan(job.project_id)
    state = jobs.generation.timelines.current(job.project_id)
    assert state is not None
    switched = jobs.select_style(job.project_id, state.current.version, "technical_proof")
    assert switched.decision.outcome == "overridden"
    assert switched.scene_ids == original.scene_ids
    assert switched.recommendation_evidence_refs == original.recommendation_evidence_refs
    assert director is jobs.executor.style_director  # type: ignore[attr-defined]
    state = jobs.generation.timelines.current(job.project_id)
    assert state is not None
    overridden = jobs.select_style(
        job.project_id,
        state.current.version,
        "editorial_story",
        scene_id=original.scene_ids[0],
    )
    assert overridden.overrides[0].variant_id == "editorial_story"
    state = jobs.generation.timelines.current(job.project_id)
    assert state is not None
    reset = jobs.select_style(
        job.project_id,
        state.current.version,
        "technical_proof",
        scene_id=original.scene_ids[0],
        reset_scene=True,
    )
    assert reset.overrides == []
    undone = jobs.generation.timelines.undo(job.project_id)
    assert undone.current.timeline.style_plan_id == overridden.id


def test_callout_edit_creates_undoable_typed_plan_version(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.start("project-one-click")
    while job.status != "succeeded":
        job = jobs.step(job.id)
    original = jobs.attention_plan(job.project_id)
    assert original.callouts
    state = jobs.generation.timelines.current(job.project_id)
    assert state is not None

    updated = jobs.edit_attention(
        job.project_id,
        original.callouts[0].id,
        state.current.version,
        {"text": "Open the working project", "target_x": 0.4, "target_y": 0.2},
    )

    assert updated.id != original.id and updated.manual_override_of == original.id
    assert updated.callouts[0].text == "Open the working project"
    current = jobs.generation.timelines.current(job.project_id)
    assert current is not None and current.current.timeline.attention_plan_id == updated.id
    undone = jobs.generation.timelines.undo(job.project_id)
    assert undone.current.timeline.attention_plan_id == original.id


def test_duplicate_delivery_and_uncertain_paid_stage_require_approval(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.step(jobs.start("project-one-click").id)
    claimed = jobs._save(
        job, status="running", attempts=1, lease_until=datetime.now(UTC) + timedelta(minutes=5)
    )
    with pytest.raises(JobConflict):
        jobs.step(job.id)
    jobs._save(claimed, lease_until=datetime.now(UTC) - timedelta(seconds=1))
    interrupted = jobs.step(job.id)
    assert interrupted.status == "awaiting_retry" and interrupted.stage == "research"
    with pytest.raises(JobConflict):
        jobs.retry(job.project_id, job.id, False)
    retried = jobs.retry(job.project_id, job.id, True)
    assert retried.status == "queued"
    assert jobs.step(job.id).stage == "understanding"


def test_saved_paid_checkpoint_is_reused_after_crash(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.step(jobs.start("project-one-click").id)
    claimed = jobs._save(
        job, status="running", attempts=1, lease_until=datetime.now(UTC) - timedelta(seconds=1)
    )
    jobs.records.put(f"job-stage-{job.id}-research", 0, {"warning": None})

    class MustNotExecute:
        def execute(self, job: GenerationJob) -> dict[str, Any]:
            raise AssertionError("Saved stage must not execute")

    jobs.executor = MustNotExecute()
    result = jobs.step(claimed.id)
    assert result.stage == "understanding" and result.status == "queued"


def test_local_tick_ignores_non_job_generation_records(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    jobs.records.put(
        "generation-trace-not-a-job",
        0,
        {"id": "trace-not-a-job", "status": "running"},
    )

    assert jobs.local_tick() is False


def test_bounded_retries_and_no_plaintext_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_CAPTURE_AUTH_ORIGINS", "https://example.com")
    jobs = jobs_fixture(tmp_path)
    job = jobs.start("project-one-click", "private-test-session")
    context = jobs.records.get(f"job-input-{job.id}")
    assert context is not None and "private-test-session" not in str(context)
    assert jobs.vault.decrypt(context[1]["capture_token"]) == "private-test-session"

    class Failing:
        def execute(self, job: GenerationJob) -> dict[str, Any]:
            raise ValueError("private exception")

    jobs.executor = Failing()
    for attempt in range(3):
        failed = jobs.step(job.id)
        expected = "failed" if attempt == 2 else "awaiting_retry"
        assert failed.status == expected and "private exception" not in failed.message
        if attempt < 2:
            jobs.retry(job.project_id, job.id, True)
    with pytest.raises(JobConflict):
        jobs.retry(job.project_id, job.id, True)


def test_cloud_dispatch_is_oidc_and_contains_no_session_token() -> None:
    from demodirector_api.cloud import CloudTasksSettings
    from test_cloud import TasksClient

    client = TasksClient()
    settings = CloudTasksSettings(
        "p", "us-central1", "queue", "https://api.example", "tasks@example"
    )
    CloudGenerationDispatcher(client, settings).dispatch("job1", 1)
    assert client.task["http_request"]["url"] == "https://api.example/tasks/generate"
    assert client.task["http_request"]["oidc_token"]["audience"] == "https://api.example"
    assert client.task["http_request"]["body"] == b'{"job_id": "job1"}'


def test_job_api_ownership_and_task_endpoint_fail_closed(tmp_path: Path) -> None:
    from demodirector_api.auth import (
        AuthService,
        AuthSettings,
        FakeIdentityProvider,
        SQLiteAuthRepository,
    )
    from demodirector_api.main import create_app
    from fastapi.testclient import TestClient
    from test_auth import bearer, signup

    jobs = jobs_fixture(tmp_path)
    auth = AuthService(
        FakeIdentityProvider(verified=True),
        SQLiteAuthRepository(tmp_path / "auth.sqlite"),
        AuthSettings(required=True),
    )
    app = create_app(repository=jobs.generation.projects, auth_service=auth)
    app.state.generation_jobs = jobs
    client = TestClient(app)
    owner = signup(client, "owner@example.test")
    outsider = signup(client, "outsider@example.test")
    project = jobs.generation.projects.get("project-one-click")
    assert project is not None
    jobs.generation.projects.update(
        project.model_copy(update={"owner_user_id": owner["session"]["user"]["user_id"]})
    )
    path = "/projects/project-one-click/generate"
    assert client.post(path).status_code == 401
    assert client.post(path, headers=bearer(outsider)).status_code == 404
    started = client.post(path, headers=bearer(owner))
    assert started.status_code == 202
    assert (
        client.get("/projects/project-one-click/generation", headers=bearer(owner)).json()["id"]
        == started.json()["id"]
    )
    assert (
        client.get("/projects/project-one-click/generation", headers=bearer(outsider)).status_code
        == 404
    )
    trace = client.get("/projects/project-one-click/generation/trace", headers=bearer(owner))
    assert trace.status_code == 200
    assert trace.json()["project_id"] == "project-one-click"
    assert (
        client.get(
            "/projects/project-one-click/generation/trace", headers=bearer(outsider)
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/tasks/generate", json={"job_id": started.json()["id"]}, headers=bearer(owner)
        ).status_code
        == 403
    )
