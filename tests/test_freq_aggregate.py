"""Tests for F4a: `aggregate_counts()` — raw count matrix construction.

All cross-engine tests use the `sample_df` fixture from conftest.py, which
parametrizes pandas + polars automatically. Null-handling and empty-frame
tests use locally-defined parametrized fixtures.
"""

from __future__ import annotations

import numpy as np
import pytest

from legible._engine import wrap
from legible.freq import (
    CountResult,
    _parse_freq_args,
    aggregate_counts,
)


def _spec(*keys, **kwargs):
    return _parse_freq_args(*keys, **kwargs)


class TestOneWay:
    def test_returns_count_result(self, sample_df):
        result = aggregate_counts(wrap(sample_df), _spec("region"))
        assert isinstance(result, CountResult)
        assert result.col_categories is None
        assert result.counts.shape == (3,)

    def test_categories_sorted_alphabetically(self, sample_df):
        result = aggregate_counts(wrap(sample_df), _spec("region"))
        assert [c.value for c in result.row_categories] == ["East", "South", "West"]

    def test_region_counts_match_expected(self, sample_df):
        result = aggregate_counts(wrap(sample_df), _spec("region"))
        np.testing.assert_array_equal(result.counts, [2, 3, 2])

    def test_product_counts_match_expected(self, sample_df):
        result = aggregate_counts(wrap(sample_df), _spec("product"))
        assert [c.value for c in result.row_categories] == ["A", "B"]
        np.testing.assert_array_equal(result.counts, [4, 3])


class TestTwoWay:
    def test_shape_and_categories(self, sample_df):
        result = aggregate_counts(wrap(sample_df), _spec("region", "product"))
        assert result.counts.shape == (3, 2)
        assert [c.value for c in result.row_categories] == ["East", "South", "West"]
        assert [c.value for c in result.col_categories] == ["A", "B"]

    def test_counts_match_expected(self, sample_df):
        result = aggregate_counts(wrap(sample_df), _spec("region", "product"))
        expected = np.array([[1, 1], [2, 1], [1, 1]], dtype=np.float64)
        np.testing.assert_array_equal(result.counts, expected)


class TestLevelsOverride:
    def test_levels_changes_category_order(self, sample_df):
        result = aggregate_counts(
            wrap(sample_df),
            _spec("region", levels={"region": ["West", "East", "South"]}),
        )
        assert [c.value for c in result.row_categories] == ["West", "East", "South"]
        np.testing.assert_array_equal(result.counts, [2, 2, 3])

    def test_levels_includes_unobserved_yields_zero(self, sample_df):
        result = aggregate_counts(
            wrap(sample_df),
            _spec("region",
                  levels={"region": ["West", "East", "South", "North"]}),
        )
        np.testing.assert_array_equal(result.counts, [2, 2, 3, 0])

    def test_levels_subset_filters_categories(self, sample_df):
        result = aggregate_counts(
            wrap(sample_df), _spec("region", levels={"region": ["East"]}),
        )
        assert [c.value for c in result.row_categories] == ["East"]
        np.testing.assert_array_equal(result.counts, [2])


class TestNullHandling:
    @pytest.fixture(params=["pandas", "polars"])
    def df_with_nulls(self, request):
        data = {"region": ["West", "West", None, "East"]}
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame(data)
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    def test_dropna_false_appends_missing_category(self, df_with_nulls):
        result = aggregate_counts(wrap(df_with_nulls), _spec("region"))
        values = [c.value for c in result.row_categories]
        assert values == ["East", "West", None]
        assert result.row_categories[-1].label == "Missing"
        np.testing.assert_array_equal(result.counts, [1, 2, 1])

    def test_dropna_true_drops_nulls_no_missing_category(self, df_with_nulls):
        result = aggregate_counts(
            wrap(df_with_nulls), _spec("region", dropna=True),
        )
        values = [c.value for c in result.row_categories]
        assert values == ["East", "West"]
        np.testing.assert_array_equal(result.counts, [1, 2])

    def test_pandas_nan_normalized_to_none(self):
        """Pandas exposes object-column nulls as NaN; we normalize to None."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"region": ["West", None, "East"]})
        result = aggregate_counts(wrap(df), _spec("region"))
        assert result.row_categories[-1].value is None
        assert result.row_categories[-1].label == "Missing"


class TestLevelsNullInteraction:
    """`levels=` must still honor the dropna=False Missing-category policy.

    Regression coverage for the reviewer's finding that the old fast-path
    return from _resolve_categories() silently dropped null grouping rows
    when levels= was supplied.
    """

    @pytest.fixture(params=["pandas", "polars"])
    def df_with_nulls(self, request):
        data = {"region": ["East", "West", None, "West"]}
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame(data)
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    def test_levels_with_nulls_dropna_false_appends_missing(self, df_with_nulls):
        result = aggregate_counts(
            wrap(df_with_nulls),
            _spec("region", levels={"region": ["East", "West"]}),
        )
        values = [c.value for c in result.row_categories]
        assert values == ["East", "West", None]
        assert result.row_categories[-1].label == "Missing"
        np.testing.assert_array_equal(result.counts, [1, 2, 1])

    def test_levels_with_nulls_dropna_true_no_missing(self, df_with_nulls):
        result = aggregate_counts(
            wrap(df_with_nulls),
            _spec("region", levels={"region": ["East", "West"]}, dropna=True),
        )
        values = [c.value for c in result.row_categories]
        assert values == ["East", "West"]
        np.testing.assert_array_equal(result.counts, [1, 2])

    def test_levels_with_explicit_none_no_double_missing(self, df_with_nulls):
        # User explicitly listed None in levels — don't double-append.
        # User's Category(None) is used as-is (no "Missing" label).
        result = aggregate_counts(
            wrap(df_with_nulls),
            _spec("region", levels={"region": ["East", "West", None]}),
        )
        values = [c.value for c in result.row_categories]
        assert values == ["East", "West", None]
        # No "Missing" label — user provided None explicitly without a label
        assert result.row_categories[-1].label is None
        np.testing.assert_array_equal(result.counts, [1, 2, 1])


class TestObservedFalse:
    def test_observed_false_without_levels_raises(self, sample_df):
        with pytest.raises(ValueError, match="observed=False"):
            aggregate_counts(
                wrap(sample_df), _spec("region", observed=False),
            )

    def test_observed_false_with_levels_works(self, sample_df):
        result = aggregate_counts(
            wrap(sample_df),
            _spec("region", observed=False,
                  levels={"region": ["West", "East", "South", "North"]}),
        )
        np.testing.assert_array_equal(result.counts, [2, 2, 3, 0])


class TestEmptyDataFrame:
    def test_empty_pandas_returns_empty_result(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"region": pd.Series([], dtype="object")})
        result = aggregate_counts(wrap(df), _spec("region"))
        assert result.row_categories == ()
        assert result.col_categories is None
        assert result.counts.shape == (0,)

    def test_empty_polars_returns_empty_result(self):
        pl = pytest.importorskip("polars")
        df = pl.DataFrame(schema={"region": pl.String})
        result = aggregate_counts(wrap(df), _spec("region"))
        assert result.row_categories == ()
        assert result.counts.shape == (0,)


class TestSortingFallback:
    def test_mixed_type_column_falls_back_to_observed_order(self):
        """A column with non-orderable mixed types should not crash; it
        should fall back to observed order rather than sorting."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"mixed": ["a", 1, "b", 2, "a"]})
        # No sort possible — implementation should not raise
        result = aggregate_counts(wrap(df), _spec("mixed"))
        # Both observed values appear (order is implementation-defined under
        # the fallback path; we only assert the values are present)
        values = {c.value for c in result.row_categories}
        assert values == {"a", 1, "b", 2}
