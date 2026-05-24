"""Shared pytest fixtures.

`sample_df` is parametrized over pandas and polars — any test taking it
runs twice, once per engine. The engine imports are deferred to fixture
bodies so test files that don't request these fixtures (model, examples,
freq-spec, etc.) can run in environments without pandas/polars installed.
Missing-engine variants are SKIPPED via `pytest.importorskip`, not
errored.
"""

from __future__ import annotations

import pytest


SAMPLE_DATA = {
    "region": ["West", "West", "East", "East", "South", "South", "South"],
    "product": ["A", "B", "A", "B", "A", "B", "A"],
    "revenue": [100.0, 80.0, 90.0, 70.0, 60.0, 55.0, 65.0],
    "units":   [10, 8, 9, 7, 6, 5, 6],
}


@pytest.fixture(params=["pandas", "polars"])
def sample_df(request):
    """Parametrized: yields the same logical DataFrame in both engines.

    Skips a variant if its engine isn't installed.
    """
    if request.param == "pandas":
        pd = pytest.importorskip("pandas")
        return pd.DataFrame(SAMPLE_DATA)
    pl = pytest.importorskip("polars")
    return pl.DataFrame(SAMPLE_DATA)


@pytest.fixture
def pandas_sample():
    """Pandas-only fixture (skipped if pandas not installed)."""
    pd = pytest.importorskip("pandas")
    return pd.DataFrame(SAMPLE_DATA)


@pytest.fixture
def polars_sample():
    """Polars-only fixture (skipped if polars not installed)."""
    pl = pytest.importorskip("polars")
    return pl.DataFrame(SAMPLE_DATA)
