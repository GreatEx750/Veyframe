from pathlib import Path

import pytest
from demodirector_api.projects import ProjectCreate
from demodirector_api.repositories import SQLiteProjectRepository
from demodirector_worker.presentation_assets import capture_settings_for_template, load_pack
from demodirector_worker.promo_assets import load_promo_pack, promo_root, promo_schedule
from test_generation import FakeCaptureWorker, build_service


@pytest.mark.parametrize("mode,seconds,count", [("spotlight_demo", 30, 3), ("short_demo", 45, 5)])
@pytest.mark.parametrize("orientation", ["landscape", "vertical"])
def test_promo_templates_and_storage_are_independent(
    tmp_path: Path, mode: str, seconds: int, count: int, orientation: str
) -> None:
    _, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    original = projects.get("project-one-click")
    assert original
    payload = original.model_dump()
    payload.update(
        demo_mode=mode, requested_duration_seconds=seconds, output_orientation=orientation
    )
    project = type(original).model_validate(payload)
    db = SQLiteProjectRepository(tmp_path / "new.db")
    db.create(project)
    assert db.get(project.id) == project
    pack = load_promo_pack(promo_root(mode, orientation))
    schedule = promo_schedule(pack)
    assert len(schedule) == count and schedule[-1][1]["end_ms"] == seconds * 1000
    for template, _, _ in schedule:
        if template["requires_product"]:
            settings = capture_settings_for_template(template)
            assert settings.viewport_width == template["product_aperture"]["width"]
        for slot in template["copy_slots"]:
            rect = slot["rect"]
            assert rect["x"] + rect["width"] <= pack["canvas"]["width"]
            assert rect["y"] + rect["height"] <= pack["canvas"]["height"]
    assert load_pack()["pack_id"] == "presentation-story@2"
    assert original.demo_mode == "product_demo" and original.output_orientation == "landscape"


@pytest.mark.parametrize("mode,duration", [("spotlight_demo", 120), ("short_demo", 30)])
def test_api_rejects_wrong_promo_duration(mode: str, duration: int) -> None:
    with pytest.raises(ValueError):
        ProjectCreate.model_validate(
            dict(
                name="Wikipedia",
                website_url="https://wikipedia.com",
                product_summary="Explore Wikipedia search",
                audience="Readers",
                tone="friendly",
                requested_duration_seconds=duration,
                cta="Explore",
                demo_mode=mode,
            )
        )


@pytest.mark.parametrize(
    "orientation,dimensions", [("landscape", (1920, 1080)), ("vertical", (1080, 1920))]
)
def test_reexport_preserves_orientation(
    tmp_path: Path, orientation: str, dimensions: tuple[int, int]
) -> None:
    from demodirector_api.exports import ExportService, SQLiteExportRepository
    from demodirector_contracts import Timeline
    from test_exports import FileRenderer

    out = tmp_path / "exports"
    service = ExportService(FileRenderer(out), SQLiteExportRepository(tmp_path / "exports.db"), out)
    value = Timeline.model_validate(
        {
            "project_id": "promo",
            "duration_ms": 30000,
            "demo_mode": "spotlight_demo",
            "output_orientation": orientation,
        }
    )
    result = service.create("promo", value, "1080p")
    assert result.status == "succeeded"
    assert (result.width, result.height) == dimensions
