"""Generate the portrait landing example through the local application pipeline."""

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
for relative in ["packages/contracts/python", "services/api/src", "services/worker/src"]:
    sys.path.insert(0, str(ROOT / relative))

from demodirector_api.presentation_pipeline import run_presentation  # noqa: E402
from demodirector_api.product_understanding import website_sources  # noqa: E402
from demodirector_api.repositories import (  # noqa: E402
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
)
from demodirector_contracts import Project  # noqa: E402
from demodirector_worker.website_inspector import (  # noqa: E402
    InspectorSettings,
    PlaywrightWebsiteInspector,
)


def main() -> None:
    output = ROOT / "artifacts/landing-short-google"
    output.mkdir(parents=True, exist_ok=True)
    db = ROOT / "artifacts/demodirector.db"
    projects = SQLiteProjectRepository(db)
    saved = output / "project.json"
    if saved.exists():
        project = Project.model_validate_json(saved.read_text("utf-8"))
    else:
        now = datetime.now(UTC)
        project = Project.model_validate({
            "id": str(uuid4()), "name": "Wikipedia — Blue and coral Short",
            "website_url": "https://www.wikipedia.org/",
            "product_summary": (
                "Introduce Wikipedia: search for Solar System, navigate article sections, "
                "and follow the Earth link. Use Wikipedia as the short brand label and "
                "concise top descriptions. Show real mouse movement and clicks."
            ),
            "audience": "Curious readers", "tone": "Clear and inviting",
            "requested_duration_seconds": 45, "cta": "Explore Wikipedia",
            "demo_mode": "short_demo", "output_orientation": "vertical",
            "owner_user_id": "judge-demo", "created_at": now, "updated_at": now,
        })
        projects.create(project)
        saved.write_text(project.model_dump_json(indent=2), "utf-8")
    inspection_file = output / "inspection.json"
    if not inspection_file.exists():
        inspected = PlaywrightWebsiteInspector(
            output / "inspection", InspectorSettings(max_pages=1, timeout_ms=30000),
        ).inspect(project_id=project.id, website_url=str(project.website_url))
        if not inspected.pages:
            raise ValueError("Website inspection did not return any pages")
        SQLiteResearchSourceRepository(db).replace_website_sources(
            project.id, website_sources(project.id, inspected),
        )
        inspection_file.write_text(inspected.model_dump_json(indent=2), "utf-8")
    result = run_presentation(
        project, ROOT, output, db, lambda message: print(message, flush=True),
        preview=False, template_theme="google",
    )
    export = result["export"]
    shutil.copyfile(
        ROOT / "artifacts/exports" / export["filename"], output / "short-google-45s.mp4",
    )
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
