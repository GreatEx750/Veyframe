import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

from demodirector_worker import (
    AutoCameraService,
    CaptionService,
    FFmpegRenderer,
    GeminiTTSAdapter,
    GeminiTTSSettings,
    InspectorSettings,
    NarrationService,
    PlaywrightCaptureWorker,
    PlaywrightWebsiteInspector,
    WebsiteInspector,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from demodirector_api.ai_routes import router as ai_router
from demodirector_api.auth import (
    AuthenticationError,
    AuthService,
    AuthSettings,
    FirestoreAuthRepository,
    GoogleIdentityPlatformProvider,
    SQLiteAuthRepository,
    UnavailableIdentityProvider,
)
from demodirector_api.auth_routes import bearer_token, judge_router
from demodirector_api.auth_routes import router as auth_router
from demodirector_api.brief_coverage import BriefCoverageService
from demodirector_api.cloud import (
    CloudCaptureDispatcher,
    CloudTasksSettings,
    FirestoreProjectRepository,
)
from demodirector_api.cloud_routes import router as cloud_router
from demodirector_api.director_agent import create_director_workflow
from demodirector_api.edit_planner import EditPlannerService
from demodirector_api.edit_routes import router as edit_router
from demodirector_api.export_routes import router as export_router
from demodirector_api.exports import ExportService, SQLiteExportRepository
from demodirector_api.generation import DemoGenerationService
from demodirector_api.generation_routes import router as generation_router
from demodirector_api.google_ai import (
    AIConfigurationError,
    GoogleAIService,
    GoogleAISettings,
    StructuredAIService,
    UnavailableGoogleAIService,
)
from demodirector_api.health import HealthResponse
from demodirector_api.inspection_routes import router as inspection_router
from demodirector_api.parallel_search import (
    ParallelConfigurationError,
    ParallelSearchAdapter,
    ParallelSearchGateway,
    ParallelSearchSettings,
    ProjectResearchService,
    UnavailableParallelSearchAdapter,
)
from demodirector_api.product_understanding import ProductUnderstandingService
from demodirector_api.projects import router as projects_router
from demodirector_api.qa_routes import router as qa_router
from demodirector_api.repair import MissingRequirementRepairService
from demodirector_api.repair_routes import router as repair_router
from demodirector_api.repositories import (
    ProductUnderstandingRepository,
    ProjectRepository,
    ResearchSourceRepository,
    SQLiteProductUnderstandingRepository,
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteStoryboardRepository,
    SQLiteTimelineRepository,
    SQLiteWebsiteInspectionRepository,
    StoryboardRepository,
    TimelineRepository,
    WebsiteInspectionRepository,
)
from demodirector_api.research_routes import router as research_router
from demodirector_api.research_tools import create_product_research_tool
from demodirector_api.storyboard_generation import StoryboardGenerationService
from demodirector_api.storyboard_routes import router as storyboard_router
from demodirector_api.timeline_edits import TimelineEditService
from demodirector_api.timeline_routes import router as timeline_router
from demodirector_api.understanding_routes import router as understanding_router


def create_app(
    repository: ProjectRepository | None = None,
    ai_service: StructuredAIService | None = None,
    ai_settings: GoogleAISettings | None = None,
    research_repository: ResearchSourceRepository | None = None,
    project_research_service: ProjectResearchService | None = None,
    parallel_settings: ParallelSearchSettings | None = None,
    inspection_repository: WebsiteInspectionRepository | None = None,
    website_inspector: WebsiteInspector | None = None,
    product_understanding_repository: ProductUnderstandingRepository | None = None,
    storyboard_repository: StoryboardRepository | None = None,
    timeline_repository: TimelineRepository | None = None,
    auth_service: AuthService | None = None,
) -> FastAPI:
    application = FastAPI(title="DemoDirector API", version="0.1.0")
    database_path = Path(os.getenv("DEMO_DATABASE_PATH", "artifacts/demodirector.db"))
    cloud_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    metadata_backend = os.getenv("DEMO_METADATA_BACKEND", "sqlite")
    firestore_client = None
    if repository is not None:
        projects = repository
    elif metadata_backend == "firestore":
        if not cloud_project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Firestore metadata.")
        from google.cloud import firestore

        firestore_client = firestore.Client(
            project=cloud_project_id,
            database=os.getenv("DEMO_FIRESTORE_DATABASE", "(default)"),
        )
        projects = FirestoreProjectRepository(firestore_client)
    else:
        projects = SQLiteProjectRepository(database_path)
    research_sources = research_repository or SQLiteResearchSourceRepository(database_path)
    inspections = inspection_repository or SQLiteWebsiteInspectionRepository(database_path)
    understandings = product_understanding_repository or SQLiteProductUnderstandingRepository(
        database_path
    )
    storyboards = storyboard_repository or SQLiteStoryboardRepository(database_path)
    timelines = timeline_repository or SQLiteTimelineRepository(database_path)
    application.state.project_repository = projects
    auth_settings = AuthSettings.from_environment()
    if auth_service is not None:
        resolved_auth_service = auth_service
    else:
        auth_repository = (
            FirestoreAuthRepository(firestore_client)
            if firestore_client is not None
            else SQLiteAuthRepository(database_path)
        )
        identity_provider = (
            GoogleIdentityPlatformProvider(auth_settings.identity_platform_api_key)
            if auth_settings.identity_platform_api_key
            else UnavailableIdentityProvider()
        )
        resolved_auth_service = AuthService(identity_provider, auth_repository, auth_settings)
    application.state.auth_service = resolved_auth_service
    application.state.website_inspection_repository = inspections
    application.state.research_source_repository = research_sources
    application.state.product_understanding_repository = understandings
    application.state.storyboard_repository = storyboards
    application.state.timeline_repository = timelines
    application.state.timeline_edit_service = TimelineEditService(timelines)
    application.state.generation_service = None
    application.state.capture_dispatcher = None
    worker_url = os.getenv("DEMO_WORKER_URL")
    queue = os.getenv("DEMO_TASK_QUEUE")
    invoker_service_account = os.getenv("DEMO_TASK_INVOKER_SERVICE_ACCOUNT")
    if cloud_project_id and worker_url and queue and invoker_service_account:
        from google.cloud import tasks_v2

        application.state.capture_dispatcher = CloudCaptureDispatcher(
            cast(object, tasks_v2.CloudTasksClient()),  # type: ignore[arg-type]
            CloudTasksSettings(
                project_id=cloud_project_id,
                location=os.getenv("DEMO_TASK_LOCATION", "us-central1"),
                queue=queue,
                worker_url=worker_url,
                invoker_service_account=invoker_service_account,
            ),
        )
    artifact_root = Path(os.getenv("DEMO_ARTIFACTS_DIR", "artifacts"))
    export_root = artifact_root / "exports"
    application.state.export_service = ExportService(
        FFmpegRenderer(artifact_root, export_root),
        SQLiteExportRepository(database_path),
        export_root,
    )
    application.state.website_inspector = website_inspector or PlaywrightWebsiteInspector(
        Path(os.getenv("DEMO_ARTIFACTS_DIR", "artifacts")) / "inspections",
        InspectorSettings(
            max_pages=int(os.getenv("INSPECT_MAX_PAGES", "3")),
            max_depth=int(os.getenv("INSPECT_MAX_DEPTH", "1")),
            timeout_ms=int(os.getenv("INSPECT_TIMEOUT_MS", "10000")),
        ),
    )
    settings = ai_settings or GoogleAISettings.from_environment()
    if ai_service is None:
        try:
            resolved_ai_service: StructuredAIService = GoogleAIService(settings)
        except AIConfigurationError as error:
            resolved_ai_service = UnavailableGoogleAIService(settings.model_name, str(error))
    else:
        resolved_ai_service = ai_service
    application.state.ai_service = resolved_ai_service
    application.state.product_understanding_service = ProductUnderstandingService(
        resolved_ai_service
    )
    application.state.storyboard_generation_service = StoryboardGenerationService(
        resolved_ai_service
    )
    application.state.edit_planner_service = EditPlannerService(resolved_ai_service)
    application.state.brief_coverage_service = BriefCoverageService(resolved_ai_service)
    application.state.repair_service = None
    if settings.api_key is not None:
        repair_root = artifact_root / "repairs"
        tts_settings = GeminiTTSSettings.from_environment()
        application.state.repair_service = MissingRequirementRepairService(
            resolved_ai_service,
            application.state.brief_coverage_service,
            PlaywrightCaptureWorker(repair_root / "captures"),
            NarrationService(GeminiTTSAdapter(tts_settings), repair_root / "narration"),
            CaptionService(),
            AutoCameraService(),
            FFmpegRenderer(repair_root, repair_root / "renders"),
        )

    search_settings = parallel_settings or ParallelSearchSettings.from_environment()
    if project_research_service is None:
        try:
            search: ParallelSearchGateway = ParallelSearchAdapter(search_settings)
        except ParallelConfigurationError as error:
            search = UnavailableParallelSearchAdapter(str(error))
        resolved_research_service = ProjectResearchService(search, research_sources)
    else:
        resolved_research_service = project_research_service
    application.state.project_research_service = resolved_research_service
    application.state.parallel_search_mode = search_settings.mode

    if settings.api_key is not None:
        application.state.generation_service = DemoGenerationService(
            projects=projects,
            research_sources=research_sources,
            inspections=inspections,
            understandings=understandings,
            storyboards=storyboards,
            timelines=timelines,
            research=resolved_research_service,
            inspector=application.state.website_inspector,
            understanding_generator=application.state.product_understanding_service,
            storyboard_generator=application.state.storyboard_generation_service,
            capture_worker=PlaywrightCaptureWorker(artifact_root / "captures"),
            narration=NarrationService(
                GeminiTTSAdapter(GeminiTTSSettings.from_environment()),
                artifact_root / "narration",
            ),
            captions=CaptionService(),
            camera=AutoCameraService(),
            exports=application.state.export_service,
        )

    research_tool = create_product_research_tool(projects, resolved_research_service)
    application.state.director_workflow = create_director_workflow(
        settings.model_name,
        tools=[research_tool],
    )
    application.include_router(projects_router)
    application.include_router(auth_router)
    application.include_router(judge_router)
    application.include_router(ai_router)
    application.include_router(research_router)
    application.include_router(inspection_router)
    application.include_router(understanding_router)
    application.include_router(storyboard_router)
    application.include_router(edit_router)
    application.include_router(timeline_router)
    application.include_router(qa_router)
    application.include_router(repair_router)
    application.include_router(export_router)
    application.include_router(generation_router)
    application.include_router(cloud_router)

    @application.middleware("http")
    async def authorize_project_routes(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path_parts = [part for part in request.url.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] == "projects":
            project_id = path_parts[1]
            authorization = request.headers.get("authorization")
            token = bearer_token(authorization)
            if token is None and not resolved_auth_service.settings.required:
                return await call_next(request)
            if token is None:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "code": "authentication_required",
                            "message": "Authentication is required.",
                        }
                    },
                    headers={"Cache-Control": "no-store"},
                )
            try:
                active_session = resolved_auth_service.authenticate(token)
            except AuthenticationError:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "code": "authentication_required",
                            "message": "Authentication is required.",
                        }
                    },
                    headers={"Cache-Control": "no-store"},
                )
            if active_session.user.role == "judge_demo" and request.method not in {
                "GET",
                "HEAD",
                "DELETE",
            }:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": {
                            "code": "judge_read_only",
                            "message": "Judge mode uses pre-generated, read-only product data.",
                        }
                    },
                    headers={"Cache-Control": "no-store"},
                )
            project = projects.get(project_id)
            if project is None or project.owner_user_id != active_session.user.user_id:
                return JSONResponse(
                    status_code=404,
                    content={"detail": "Project not found"},
                    headers={"Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if path_parts and path_parts[0] in {"projects", "auth"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="api")

    return application


app = create_app()
