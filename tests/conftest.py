"""Shared pytest fixtures.

The `sample_df` fixture is parametrized over pandas and polars — any test
function that takes `sample_df` automatically runs twice, once per engine.
Used by every engine-agnostic test from F3 onward.
"""

from __future__ import annotations

import pandas as pd
import polars as pl
import pytest


SAMPLE_DATA = {
    "region": ["West", "West", "East", "East", "South", "South", "South"],
    "product": ["A", "B", "A", "B", "A", "B", "A"],
    "revenue": [100.0, 80.0, 90.0, 70.0, 60.0, 55.0, 65.0],
    "units":   [10, 8, 9, 7, 6, 5, 6],
}


def _make_pandas() -> pd.DataFrame:
    return pd.DataFrame(SAMPLE_DATA)


def _make_polars() -> pl.DataFrame:
    return pl.DataFrame(SAMPLE_DATA)


@pytest.fixture(params=["pandas", "polars"])
def sample_df(request):
    """Parametrized fixture: yields the same logical DataFrame in both engines."""
    if request.param == "pandas":
        return _make_pandas()
    return _make_polars()


@pytest.fixture
def pandas_sample() -> pd.DataFrame:
    """Engine-specific pandas fixture (use when a test is intentionally pandas-only)."""
    return _make_pandas()


@pytest.fixture
def polars_sample() -> pl.DataFrame:
    """Engine-specific polars fixture (use when a test is intentionally polars-only)."""
    return _make_polars()
