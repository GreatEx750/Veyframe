from datetime import UTC, datetime

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
