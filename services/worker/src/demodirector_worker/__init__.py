"""DemoDirector background worker."""

from demodirector_worker.attention import AttentionCompiler
from demodirector_worker.auto_camera import (
    AutoCameraService,
    AutoCameraSettings,
    DeterministicFocusSelector,
    GeminiFocusSelector,
)
from demodirector_worker.captions import CaptionService
from demodirector_worker.capture import CaptureSettings, PlaywrightCaptureWorker
from demodirector_worker.cloud_storage import CloudStorageArtifactStore
from demodirector_worker.editorial import EditorialCompositionCompiler
from demodirector_worker.longform import LongFormCompiler
from demodirector_worker.motion import MotionCompositionCompiler, motion_state
from demodirector_worker.narration import (
    FixtureTTSAdapter,
    GeminiTTSAdapter,
    GeminiTTSSettings,
    NarrationService,
)
from demodirector_worker.renderer import FFmpegRenderer, FFmpegSettings, RendererError
from demodirector_worker.style import StyleCompiler
from demodirector_worker.website_inspector import (
    InspectorSettings,
    PlaywrightWebsiteInspector,
    WebsiteInspector,
)

__all__ = [
    "AutoCameraService",
    "AutoCameraSettings",
    "AttentionCompiler",
    "CaptureSettings",
    "CaptionService",
    "MotionCompositionCompiler",
    "LongFormCompiler",
    "motion_state",
    "CloudStorageArtifactStore",
    "FixtureTTSAdapter",
    "FFmpegRenderer",
    "FFmpegSettings",
    "DeterministicFocusSelector",
    "EditorialCompositionCompiler",
    "GeminiTTSAdapter",
    "GeminiTTSSettings",
    "GeminiFocusSelector",
    "InspectorSettings",
    "NarrationService",
    "PlaywrightCaptureWorker",
    "PlaywrightWebsiteInspector",
    "RendererError",
    "StyleCompiler",
    "WebsiteInspector",
]

__version__ = "0.1.0"
