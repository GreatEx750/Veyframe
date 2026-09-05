from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from demodirector_contracts import Project, ResearchSource
from dotenv import load_dotenv
from parallel import Parallel
from pydantic import ValidationError

from demodirector_api.repositories import ResearchSourceRepository

load_dotenv()

SearchMode = Literal["turbo", "fast", "basic", "advanced"]
ALLOWED_SEARCH_MODES: set[str] = {"turbo", "fast", "basic", "advanced"}
DEFAULT_SEARCH_MODE: SearchMode = "fast"
MAX_RESULTS = 5
MAX_CHARS_TOTAL = 5_000


class ParallelConfigurationError(RuntimeError):
    """Raised when the direct Parallel Search integration is not configured."""


class ParallelSearchError(RuntimeError):
    """Raised when Parallel cannot return a usable search response."""


@dataclass(frozen=True, slots=True)
class ParallelSearchSettings:
    api_key: str | None
    mode: SearchMode

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> ParallelSearchSettings:
        values = os.environ if environment is None else environment
        api_key = values.get("PARALLEL_API_KEY", "").strip() or None
        configured_mode = values.get("PARALLEL_SEARCH_MODE", "").strip() or DEFAULT_SEARCH_MODE
        if configured_mode not in ALLOWED_SEARCH_MODES:
            raise ParallelConfigurationError(
                "PARALLEL_SEARCH_MODE must be turbo, fast, basic, or advanced."
            )
        return cls(api_key=api_key, mode=cast(SearchMode, configured_mode))

    @property
    def is_configured(self) -> bool:
        return self.api_key is not None


@dataclass(frozen=True, slots=True)
class ParallelResultItem:
    url: str
    title: str | None
    excerpts: tuple[str, ...]


class ParallelSearchGateway(Protocol):
    configured: bool

    def search(
        self,
        *,
        objective: str,
        queries: Sequence[str],
        domain: str,
    ) -> list[ParallelResultItem]: ...


class ParallelSDKClient(Protocol):
    def search(self, **kwargs: object) -> ParallelSDKResponse: ...


class ParallelSDKResult(Protocol):
    @property
    def url(self) -> str: ...

    @property
    def title(self) -> str | None: ...

    @property
    def excerpts(self) -> Sequence[str]: ...


class ParallelSDKResponse(Protocol):
    @property
    def results(self) -> Sequence[ParallelSDKResult]: ...


class ParallelSearchAdapter:
    configured = True

    def __init__(
        self,
        settings: ParallelSearchSettings,
        client: ParallelSDKClient | None = None,
    ) -> None:
        if not settings.is_configured and client is None:
            raise ParallelConfigurationError(
                "Configure PARALLEL_API_KEY before running partner search."
            )
        self.mode = settings.mode
        self._client = client or cast(ParallelSDKClient, Parallel(api_key=settings.api_key))

    def search(
        self,
        *,
        objective: str,
        queries: Sequence[str],
        domain: str,
    ) -> list[ParallelResultItem]:
        try:
            response = self._client.search(
                objective=objective,
                search_queries=list(queries),
                mode=self.mode,
                max_chars_total=MAX_CHARS_TOTAL,
                advanced_settings={
                    "max_results": MAX_RESULTS,
                    "source_policy": {"include_domains": [domain]},
                },
            )
            raw_results = response.results
            return [
                ParallelResultItem(
                    url=str(result.url),
                    title=result.title,
                    excerpts=tuple(str(excerpt) for excerpt in result.excerpts),
                )
                for result in raw_results
            ]
        except Exception as error:
            raise ParallelSearchError(
                "Parallel Search could not retrieve product context; "
                "continuing with website-only context."
            ) from error


class FakeParallelSearchAdapter:
    configured = True

    def __init__(
        self,
        results: Sequence[ParallelResultItem] = (),
        error: ParallelSearchError | None = None,
    ) -> None:
        self.results = list(results)
        self.error = error
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        *,
        objective: str,
        queries: Sequence[str],
        domain: str,
    ) -> list[ParallelResultItem]:
        self.calls.append(
            {"objective": objective, "queries": list(queries), "domain": domain}
        )
        if self.error is not None:
            raise self.error
        return list(self.results)


class UnavailableParallelSearchAdapter:
    configured = False

    def __init__(self, detail: str) -> None:
        self.detail = detail

    def search(
        self,
        *,
        objective: str,
        queries: Sequence[str],
        domain: str,
    ) -> list[ParallelResultItem]:
        del objective, queries, domain
        raise ParallelSearchError(self.detail)


@dataclass(frozen=True, slots=True)
class ResearchRunResult:
    sources: list[ResearchSource]
    warning: str | None = None


class ProjectResearchService:
    def __init__(
        self,
        search: ParallelSearchGateway,
        repository: ResearchSourceRepository,
    ) -> None:
        self.search = search
        self.repository = repository

    def analyze(self, project: Project) -> ResearchRunResult:
        domain = product_domain(str(project.website_url))
        objective, queries = build_product_search(project, domain)
        try:
            results = self.search.search(
                objective=objective,
                queries=queries,
                domain=domain,
            )
        except ParallelSearchError as error:
            self.repository.replace_partner_sources(project.id, [])
            return ResearchRunResult(sources=[], warning=str(error))

        sources = normalize_sources(project.id, results)
        if not sources:
            self.repository.replace_partner_sources(project.id, [])
            return ResearchRunResult(
                sources=[],
                warning=(
                    "Parallel Search returned no usable official sources; "
                    "continuing with website-only context."
                ),
            )
        self.repository.replace_partner_sources(project.id, sources)
        return ResearchRunResult(sources=sources)


def product_domain(website_url: str) -> str:
    hostname = urlsplit(website_url).hostname
    if hostname is None:
        raise ValueError("project website URL must include a hostname")
    return hostname.removeprefix("www.").lower()


def build_product_search(project: Project, domain: str) -> tuple[str, list[str]]:
    objective = (
        f"Find current official product information for {domain} that supports a demo for "
        f"{project.audience}. Prioritize product features, documentation, and help pages "
        f"relevant to this brief: {project.product_summary}"
    )
    queries = [
        f"{domain} product features",
        f"{domain} official documentation",
        f"{domain} help guide",
    ]
    return objective, queries


def normalize_sources(
    project_id: str,
    results: Sequence[ParallelResultItem],
    retrieved_at: datetime | None = None,
) -> list[ResearchSource]:
    timestamp = retrieved_at or datetime.now(UTC)
    sources: list[ResearchSource] = []
    for result in results:
        snippet = "\n\n".join(excerpt.strip() for excerpt in result.excerpts if excerpt.strip())
        title = (result.title or product_domain(result.url)).strip()
        if not snippet or not title:
            continue
        try:
            source = ResearchSource.model_validate(
                {
                    "id": str(
                        uuid5(
                            NAMESPACE_URL,
                            f"{project_id}:partner_search:{result.url}",
                        )
                    ),
                    "project_id": project_id,
                    "title": title,
                    "url": result.url,
                    "snippet": snippet[:MAX_CHARS_TOTAL],
                    "source_type": "partner_search",
                    "retrieved_at": timestamp,
                }
            )
        except (ValidationError, ValueError):
            continue
        sources.append(source)
    return sources
