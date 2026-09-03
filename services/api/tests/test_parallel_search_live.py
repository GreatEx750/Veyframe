import os

import pytest
from demodirector_api.parallel_search import ParallelSearchAdapter, ParallelSearchSettings

pytestmark = pytest.mark.live


def test_live_parallel_search_returns_an_official_source() -> None:
    if os.getenv("PARALLEL_LIVE_SMOKE_TEST") != "1":
        pytest.skip("Set PARALLEL_LIVE_SMOKE_TEST=1 to run the paid Parallel smoke test.")
    settings = ParallelSearchSettings.from_environment()
    if not settings.is_configured:
        pytest.skip("Parallel credentials are not configured.")

    results = ParallelSearchAdapter(settings).search(
        objective="Find the official Parallel Search API documentation.",
        queries=["parallel.ai Search API documentation"],
        domain="parallel.ai",
    )

    assert results
    assert all("parallel.ai" in result.url for result in results)
