from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from demodirector_contracts import (
    ProductUnderstanding,
    Project,
    ResearchSource,
    WebsiteInspection,
)

from demodirector_api.google_ai import StructuredAIService


class GroundingError(RuntimeError):
    """Raised when product understanding contains unsupported source references."""


class ProductUnderstandingService:
    def __init__(self, ai_service: StructuredAIService) -> None:
        self.ai_service = ai_service

    def generate(
        self,
        *,
        project: Project,
        inspection: WebsiteInspection,
        sources: list[ResearchSource],
    ) -> ProductUnderstanding:
        all_sources = list(
            {
                source.id: source
                for source in [*website_sources(project.id, inspection), *sources]
            }.values()
        )
        prompt = build_understanding_prompt(project, inspection, all_sources)
        understanding = self.ai_service.generate_structured(
            prompt=prompt,
            response_model=ProductUnderstanding,
        )
        validate_grounding(understanding, project.id, all_sources)
        return understanding


def website_sources(
    project_id: str,
    inspection: WebsiteInspection,
    retrieved_at: datetime | None = None,
) -> list[ResearchSource]:
    timestamp = retrieved_at or datetime.now(UTC)
    sources: list[ResearchSource] = []
    for page in inspection.pages:
        element_names = [
            element.accessible_name or element.text
            for element in page.elements
            if element.accessible_name or element.text
        ]
        snippet_parts = [page.title, *page.headings, *element_names]
        snippet = "\n".join(part for part in snippet_parts if part.strip())
        if not snippet:
            continue
        sources.append(
            ResearchSource.model_validate(
                {
                    "id": str(uuid5(NAMESPACE_URL, f"{project_id}:{page.url}")),
                    "project_id": project_id,
                    "title": page.title or str(page.url),
                    "url": page.url,
                    "snippet": snippet,
                    "source_type": "website",
                    "retrieved_at": timestamp,
                }
            )
        )
    return sources


def build_understanding_prompt(
    project: Project,
    inspection: WebsiteInspection,
    sources: list[ResearchSource],
) -> str:
    context = {
        "project": project.model_dump(mode="json"),
        "inspection": inspection.model_dump(mode="json"),
        "sources": [source.model_dump(mode="json") for source in sources],
    }
    return (
        "Create a grounded ProductUnderstanding object for this demo project. "
        "Every feature and external claim must cite one or more source IDs from the supplied "
        "sources. Claims that come only from the user's project brief must set "
        "user_provided=true. Never invent product features, source IDs, or claims.\n\n"
        + json.dumps(context, separators=(",", ":"))
    )


def validate_grounding(
    understanding: ProductUnderstanding,
    project_id: str,
    sources: list[ResearchSource],
) -> None:
    if understanding.project_id != project_id:
        raise GroundingError("Product understanding project ID does not match the request.")
    allowed_source_ids = {source.id for source in sources}
    referenced_source_ids = {
        source_id
        for feature in understanding.features
        for source_id in feature.source_ids
    } | {
        source_id
        for claim in understanding.claims
        for source_id in claim.source_ids
    }
    unsupported = referenced_source_ids - allowed_source_ids
    if unsupported:
        raise GroundingError(
            "Product understanding referenced unsupported source IDs: "
            + ", ".join(sorted(unsupported))
        )
