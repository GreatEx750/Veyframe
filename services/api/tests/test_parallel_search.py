from datetime import UTC, datetime
from typing import cast
from uuid import NAMESPACE_URL, uuid5

import pytest
from demodirector_api.parallel_search import (
    DEFAULT_SEARCH_MODE,
    MAX_CHARS_TOTAL,
    MAX_RESULTS,
    ParallelConfigurationError,
    ParallelResultItem,
    ParallelSearchAdapter,
    ParallelSearchSettings,
    build_product_search,
    normalize_sources,
    product_domain,
)
from demodirector_contracts import Project
from pydantic import HttpUrl


class StubWebResult:
    def __init__(self, url: str, title: str | None, excerpts: list[str]) -> None:
        self.url = url
        self.title = title
        self.excerpts = excerpts


class StubSearchResponse:
    def __init__(self, results: list[StubWebResult]) -> None:
        self.results = results


class StubParallelClient:
    def __init__(self, response: StubSearchResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> StubSearchResponse:
        self.calls.append(kwargs)
        return self.response


def project() -> Project:
    now = datetime.now(UTC)
    return Project.model_validate(
        {
            "id": "project-1",
            "name": "Product demo",
            "website_url": "https://www.example.com/product",
            "product_summary": "A focused workflow product.",
            "audience": "Product leaders",
            "tone": "Professional",
            "requested_duration_seconds": 90,
            "cta": "Book a demo",
            "created_at": now,
            "updated_at": now,
        }
    )


def test_parallel_settings_default_to_low_cost_fast_mode() -> None:
    settings = ParallelSearchSettings.from_environment({"PARALLEL_API_KEY": " test-key "})

    assert settings.api_key == "test-key"
    assert settings.mode == DEFAULT_SEARCH_MODE
    assert settings.is_configured


def test_parallel_settings_reject_unknown_mode() -> None:
    with pytest.raises(ParallelConfigurationError, match="PARALLEL_SEARCH_MODE"):
        ParallelSearchSettings.from_environment({"PARALLEL_SEARCH_MODE": "expensive-magic"})


def test_search_adapter_uses_domain_policy_and_bounded_fast_request() -> None:
    client = StubParallelClient(
        StubSearchResponse(
            [StubWebResult("https://example.com/docs", "Docs", ["Official documentation."])]
        )
    )
    adapter = ParallelSearchAdapter(
        ParallelSearchSettings(api_key="test-key", mode="fast"),
        client=client,
    )

    results = adapter.search(
        objective="Find official product documentation.",
        queries=["example.com product docs"],
        domain="example.com",
    )

    assert results == [
        ParallelResultItem(
            url="https://example.com/docs",
            title="Docs",
            excerpts=("Official documentation.",),
        )
    ]
    call = client.calls[0]
    assert call["mode"] == "fast"
    assert call["max_chars_total"] == MAX_CHARS_TOTAL
    assert call["advanced_settings"] == {
        "max_results": MAX_RESULTS,
        "source_policy": {"include_domains": ["example.com"]},
    }


def test_product_search_prioritizes_official_domain_and_brief() -> None:
    demo_project = project()
    domain = product_domain(str(demo_project.website_url))

    objective, queries = build_product_search(demo_project, domain)

    assert domain == "example.com"
    assert demo_project.product_summary in objective
    assert demo_project.audience in objective
    assert all(domain in query for query in queries)


def test_normalization_creates_stable_typed_sources_and_skips_invalid_results() -> None:
    timestamp = datetime.now(UTC)
    results = [
        ParallelResultItem(
            url="https://example.com/docs",
            title="Official docs",
            excerpts=("Feature one.", "Feature two."),
        ),
        ParallelResultItem(url="not-a-url", title="Invalid", excerpts=("Ignored.",)),
    ]

    first = normalize_sources("project-1", results, timestamp)
    second = normalize_sources("project-1", results, timestamp)

    assert first == second
    assert len(first) == 1
    assert first[0].source_type == "partner_search"
    assert first[0].snippet == "Feature one.\n\nFeature two."
    assert first[0].id != str(
        uuid5(NAMESPACE_URL, "project-1:https://example.com/docs")
    )


def test_research_uses_inspected_redirect_and_records_broader_retry() -> None:
    from demodirector_api.parallel_search import research_product
    from demodirector_contracts import ResearchSource

    demo = project().model_copy(update={"website_url": "https://www.wikipedia.com/"})
    page = ResearchSource(
        id="landing", project_id=demo.id, title="Wikipedia",
        url=cast(HttpUrl, "https://www.wikipedia.org/"), snippet="Search Wikipedia",
        source_type="website", retrieved_at=demo.created_at,
    )

    class RetryingSearch:
        configured = True

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def search(self, **kwargs: object) -> list[ParallelResultItem]:
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return [ParallelResultItem("https://en.wikipedia.org/", "Empty", ())]
            return [ParallelResultItem(
                "https://en.wikipedia.org/wiki/Help:Searching", "Searching", ("Use search.",)
            )]

    search = RetryingSearch()
    result = research_product(search, demo, [page])
    assert len(result.sources) == 1
    assert all(call["domain"] == "wikipedia.org" for call in search.calls)
    assert search.calls[0]["queries"] != search.calls[1]["queries"]
    assert result.attempts[0]["returned_count"] == 1
    assert result.attempts[0]["accepted_count"] == 0
    assert result.attempts[1]["accepted_count"] == 1


def test_empty_research_is_bounded_and_reports_zero_results() -> None:
    from demodirector_api.parallel_search import FakeParallelSearchAdapter, research_product

    search = FakeParallelSearchAdapter()
    result = research_product(search, project(), [])
    assert len(search.calls) == 2
    assert result.sources == []
    assert result.warning
    assert all(attempt["returned_count"] == 0 for attempt in result.attempts)
