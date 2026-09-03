"""DemoDirector background worker."""

from demodirector_worker.auto_camera import (
    AutoCameraService,
    AutoCameraSettings,
    DeterministicFocusSelector,
    GeminiFocusSelector,
)
from demodirector_worker.captions import CaptionService
from demodirector_worker.capture import CaptureSettings, PlaywrightCaptureWorker
from demodirector_worker.cloud_storage import CloudStorageArtifactStore
from demodirector_worker.narration import (
    FixtureTTSAdapter,
    GeminiTTSAdapter,
    GeminiTTSSettings,
    NarrationService,
)
from demodirector_worker.renderer import FFmpegRenderer, FFmpegSettings, RendererError
from demodirector_worker.website_inspector import (
    InspectorSettings,
    PlaywrightWebsiteInspector,
    WebsiteInspector,
)

__all__ = [
    "AutoCameraService",
    "AutoCameraSettings",
    "CaptureSettings",
    "CaptionService",
    "CloudStorageArtifactStore",
    "FixtureTTSAdapter",
    "FFmpegRenderer",
    "FFmpegSettings",
    "DeterministicFocusSelector",
    "GeminiTTSAdapter",
    "GeminiTTSSettings",
    "GeminiFocusSelector",
    "InspectorSettings",
    "NarrationService",
    "PlaywrightCaptureWorker",
    "PlaywrightWebsiteInspector",
    "RendererError",
    "WebsiteInspector",
]

__version__ = "0.1.0"
