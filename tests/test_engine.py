"""Tests for src/proctab/_engine.py — the pandas/polars narwhals wrapper."""

from __future__ import annotations

import numpy as np
import pytest

from proctab._engine import wrap


class TestWrapBothEngines:
    """`wrap()` accepts both pandas and polars DataFrames identically."""

    def test_wrap_yields_dataframe_with_expected_columns(self, sample_df):
        nw_df = wrap(sample_df)
        # narwhals exposes .columns as a list of strings, engine-independent
        assert "region" in nw_df.columns
        assert "product" in nw_df.columns
        assert "revenue" in nw_df.columns
        assert "units" in nw_df.columns

    def test_wrap_preserves_row_count(self, sample_df):
        nw_df = wrap(sample_df)
        # narwhals shape is (n_rows, n_cols), matching pandas/polars convention
        assert nw_df.shape[0] == 7


class TestRequiredColumns:
    def test_all_required_columns_present_ok(self, sample_df):
        wrap(sample_df, required_columns=("region", "product"))

    def test_missing_required_column_raises_keyerror(self, sample_df):
        with pytest.raises(KeyError, match="not found"):
            wrap(sample_df, required_columns=("region", "nonexistent"))

    def test_missing_column_error_lists_available(self, sample_df):
        with pytest.raises(KeyError, match="Available columns"):
            wrap(sample_df, required_columns=("nonexistent",))

    def test_no_required_columns_skips_check(self, sample_df):
        wrap(sample_df, required_columns=())


class TestRejectsNonDataFrames:
    def test_list_raises_typeerror(self):
        with pytest.raises(TypeError):
            wrap([1, 2, 3])

    def test_dict_raises_typeerror(self):
        with pytest.raises(TypeError):
            wrap({"region": ["W", "E"]})

    def test_ndarray_raises_typeerror(self):
        with pytest.raises(TypeError):
            wrap(np.array([[1, 2], [3, 4]]))

    def test_string_raises_typeerror(self):
        with pytest.raises(TypeError):
            wrap("not a dataframe")

    def test_none_raises_typeerror(self):
        with pytest.raises(TypeError):
            wrap(None)


class TestRejectsLazyFrames:
    def test_polars_lazyframe_raises_typeerror(self, polars_sample):
        lazy = polars_sample.lazy()
        with pytest.raises(TypeError):
            wrap(lazy)

    def test_lazyframe_error_message_mentions_eager_or_dataframe(self, polars_sample):
        lazy = polars_sample.lazy()
        with pytest.raises(TypeError, match="(?i)eager|dataframe"):
            wrap(lazy)


class TestSeriesRejected:
    """A Series (1-D) is not a DataFrame; freq() needs columns by name."""

    def test_pandas_series_raises_typeerror(self, pandas_sample):
        with pytest.raises(TypeError):
            wrap(pandas_sample["region"])

    def test_polars_series_raises_typeerror(self, polars_sample):
        with pytest.raises(TypeError):
            wrap(polars_sample["region"])
