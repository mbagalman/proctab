"""Tests for T3: STAT_EXPRS — the stat-name → narwhals-expression registry.

Each stat is verified twice (pandas + polars) on numeric data and on
data with nulls, confirming the NaN-skip semantics documented in
TABULATE_API.md.
"""

from __future__ import annotations

import pytest

import narwhals.stable.v1 as nw

from legible._engine import wrap
from legible.tabulate import STAT_EXPRS, SUPPORTED_STATS


def _scalar(nw_df, col, stat):
    """Apply one stat to one column and return the scalar result."""
    selected = nw_df.select(STAT_EXPRS[stat](col).alias("__r__"))
    return selected.to_native()["__r__"][0]


# === Registry shape ========================================================


class TestRegistryShape:
    def test_keys_match_supported_stats(self):
        """Invariant: the registry covers exactly SUPPORTED_STATS."""
        assert set(STAT_EXPRS.keys()) == SUPPORTED_STATS

    def test_each_value_is_callable(self):
        for stat, fn in STAT_EXPRS.items():
            assert callable(fn), f"{stat!r} entry must be callable"

    def test_each_callable_returns_narwhals_expr(self):
        for stat, fn in STAT_EXPRS.items():
            expr = fn("x")
            assert expr is not None, f"{stat!r} returned None"
            # Narwhals expressions support .alias(); cheap structural check
            assert hasattr(expr, "alias"), f"{stat!r} not a narwhals Expr"


# === Numeric data (no nulls) ===============================================


@pytest.fixture(params=["pandas", "polars"])
def df_numeric(request):
    data = {"x": [1.0, 2.0, 3.0, 4.0]}
    if request.param == "pandas":
        pd = pytest.importorskip("pandas")
        return pd.DataFrame(data)
    pl = pytest.importorskip("polars")
    return pl.DataFrame(data)


class TestStatsOnNumeric:
    def test_sum(self, df_numeric):
        assert _scalar(wrap(df_numeric), "x", "sum") == 10.0

    def test_mean(self, df_numeric):
        assert _scalar(wrap(df_numeric), "x", "mean") == 2.5

    def test_count(self, df_numeric):
        # 4 non-null values
        assert _scalar(wrap(df_numeric), "x", "count") == 4

    def test_min(self, df_numeric):
        assert _scalar(wrap(df_numeric), "x", "min") == 1.0

    def test_max(self, df_numeric):
        assert _scalar(wrap(df_numeric), "x", "max") == 4.0

    def test_median(self, df_numeric):
        # median of [1, 2, 3, 4] = (2+3)/2 = 2.5
        assert _scalar(wrap(df_numeric), "x", "median") == 2.5


# === Data with nulls (skip semantics) =====================================


@pytest.fixture(params=["pandas", "polars"])
def df_with_nulls(request):
    data = {"x": [1.0, 2.0, None, 3.0]}
    if request.param == "pandas":
        pd = pytest.importorskip("pandas")
        return pd.DataFrame(data)
    pl = pytest.importorskip("polars")
    return pl.DataFrame(data)


class TestNullSkipSemantics:
    def test_sum_skips_nulls(self, df_with_nulls):
        # 1 + 2 + 3 = 6 (null skipped)
        assert _scalar(wrap(df_with_nulls), "x", "sum") == 6.0

    def test_mean_skips_nulls_in_both_numerator_and_denominator(self, df_with_nulls):
        # (1 + 2 + 3) / 3 = 2.0, NOT / 4
        assert _scalar(wrap(df_with_nulls), "x", "mean") == 2.0

    def test_count_excludes_nulls(self, df_with_nulls):
        # 3 non-null values
        assert _scalar(wrap(df_with_nulls), "x", "count") == 3

    def test_min_skips_nulls(self, df_with_nulls):
        assert _scalar(wrap(df_with_nulls), "x", "min") == 1.0

    def test_max_skips_nulls(self, df_with_nulls):
        assert _scalar(wrap(df_with_nulls), "x", "max") == 3.0

    def test_median_skips_nulls(self, df_with_nulls):
        # median of [1, 2, 3] = 2
        assert _scalar(wrap(df_with_nulls), "x", "median") == 2.0


# === Larger / mixed inputs to catch off-by-one or order bugs ==============


@pytest.fixture(params=["pandas", "polars"])
def df_seven(request):
    # 7 distinct values; sum=28, mean=4, median=4, min=1, max=7
    data = {"x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]}
    if request.param == "pandas":
        pd = pytest.importorskip("pandas")
        return pd.DataFrame(data)
    pl = pytest.importorskip("polars")
    return pl.DataFrame(data)


class TestStatsOnSeven:
    def test_sum_seven(self, df_seven):
        assert _scalar(wrap(df_seven), "x", "sum") == 28.0

    def test_mean_seven(self, df_seven):
        assert _scalar(wrap(df_seven), "x", "mean") == 4.0

    def test_median_seven(self, df_seven):
        # Odd-count median = middle value
        assert _scalar(wrap(df_seven), "x", "median") == 4.0

    def test_min_seven(self, df_seven):
        assert _scalar(wrap(df_seven), "x", "min") == 1.0

    def test_max_seven(self, df_seven):
        assert _scalar(wrap(df_seven), "x", "max") == 7.0
