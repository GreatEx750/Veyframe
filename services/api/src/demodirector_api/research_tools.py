from collections.abc import Callable

from demodirector_api.parallel_search import ProjectResearchService
from demodirector_api.repositories import ProjectRepository


def create_product_research_tool(
    projects: ProjectRepository,
    research: ProjectResearchService,
) -> Callable[[str], dict[str, object]]:
    def search_product_context(project_id: str) -> dict[str, object]:
        """Search current official product pages for a DemoDirector project."""
        project = projects.get(project_id)
        if project is None:
            return {"project_id": project_id, "sources": [], "warning": "Project not found"}
        result = research.analyze(project)
        return {
            "project_id": project_id,
            "sources": [source.model_dump(mode="json") for source in result.sources],
            "warning": result.warning,
        }

    return search_product_context
