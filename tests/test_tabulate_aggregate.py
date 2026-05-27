"""Tests for T4a: aggregate_data_cells() — per-group statistic values
plus companion signals (row_count, nonnull_count) for T4c.

Cross-engine via the conftest sample_df fixture. Companion signals
get their own dedicated tests because T4c's EMPTY/NULL distinction
depends on them being correct.
"""

from __future__ import annotations

import numpy as np
import pytest

from proctab._engine import wrap
from proctab.tabulate import (
    AggregateResult,
    _parse_tabulate_args,
    aggregate_data_cells,
)


def _spec(**kwargs):
    return _parse_tabulate_args(**kwargs)


# === Structural ===========================================================


class TestStructure:
    def test_returns_aggregate_result(self, sample_df):
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        assert isinstance(result, AggregateResult)

    def test_one_row_no_cols_shapes(self, sample_df):
        # 3 region categories, 1 implicit col, 1 stat, 1 metric
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        assert result.stat_values.shape == (3, 1, 1)
        assert result.row_count.shape == (3, 1)
        assert result.nonnull_count.shape == (3, 1, 1)

    def test_one_row_one_col_shapes(self, sample_df):
        # 3 regions × 2 products, 1 stat, 1 metric
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", cols="product",
                  values={"revenue": "sum"}),
        )
        assert result.stat_values.shape == (3, 2, 1)
        assert result.row_count.shape == (3, 2)
        assert result.nonnull_count.shape == (3, 2, 1)

    def test_two_rows_shapes(self, sample_df):
        # 3 regions × 2 products = 6 row groups; no col dim → 1 col group
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows=["region", "product"],
                  values={"revenue": "sum"}),
        )
        assert result.stat_values.shape == (6, 1, 1)

    def test_categories_per_dim_preserved(self, sample_df):
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows=["region", "product"], cols="product",
                  values={"revenue": "sum"}),
        ) if False else aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", cols="product",
                  values={"revenue": "sum"}),
        )
        # row_categories is a tuple-of-tuples, one tuple per row dim
        assert len(result.row_categories) == 1  # rows=("region",)
        assert [c.value for c in result.row_categories[0]] == \
            ["East", "South", "West"]
        # col_categories similarly per col dim
        assert len(result.col_categories) == 1
        assert [c.value for c in result.col_categories[0]] == ["A", "B"]

    def test_no_cols_yields_empty_col_categories(self, sample_df):
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        assert result.col_categories == ()

    def test_metric_names_preserve_insertion_order(self, sample_df):
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region",
                  values={"revenue": ["sum", "mean"], "units": ["sum"]}),
        )
        assert result.metric_names == ("revenue", "units")


# === Numeric correctness ==================================================


class TestValuesOneRow:
    def test_sum_matches_handcomputed(self, sample_df):
        """Region counts: East rows 2/3, South rows 4/5/6, West rows 0/1.
        Revenue: [100, 80, 90, 70, 60, 55, 65]
        Sums: East = 90+70=160, South = 60+55+65=180, West = 100+80=180."""
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        # Categories sorted alphabetically: East, South, West
        np.testing.assert_array_equal(
            result.stat_values[:, 0, 0], [160.0, 180.0, 180.0],
        )

    def test_mean_matches_handcomputed(self, sample_df):
        # East mean = 160/2 = 80; South = 180/3 = 60; West = 180/2 = 90
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", values={"revenue": "mean"}),
        )
        np.testing.assert_array_almost_equal(
            result.stat_values[:, 0, 0], [80.0, 60.0, 90.0],
        )

    def test_count_matches_row_count(self, sample_df):
        """For a non-null metric, stat='count' equals row_count."""
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", values={"revenue": "count"}),
        )
        np.testing.assert_array_equal(
            result.stat_values[:, 0, 0], result.row_count[:, 0],
        )


class TestValuesTwoWay:
    def test_sum_per_cell(self, sample_df):
        """Cells (region × product, revenue sum):
        East/A=90, East/B=70, South/A=60+65=125, South/B=55,
        West/A=100, West/B=80"""
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", cols="product",
                  values={"revenue": "sum"}),
        )
        expected = np.array([
            [90.0, 70.0],
            [125.0, 55.0],
            [100.0, 80.0],
        ])
        np.testing.assert_array_equal(result.stat_values[:, :, 0], expected)


class TestValuesNestedRows:
    def test_two_row_dims_row_major_order(self, sample_df):
        """rows=[region, product] yields row-major flattening:
        (East, A), (East, B), (South, A), (South, B), (West, A), (West, B)
        revenue counts: East/A=1, East/B=1, South/A=2, South/B=1, West/A=1, West/B=1
        revenue sums:   90,        70,       125,        55,       100,      80"""
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows=["region", "product"],
                  values={"revenue": "sum"}),
        )
        np.testing.assert_array_equal(
            result.stat_values[:, 0, 0],
            [90.0, 70.0, 125.0, 55.0, 100.0, 80.0],
        )
        np.testing.assert_array_equal(
            result.row_count[:, 0],
            [1, 1, 2, 1, 1, 1],
        )


# === Multiple stats / metrics =============================================


class TestMultipleStatsAndMetrics:
    def test_multiple_stats_one_metric(self, sample_df):
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region",
                  values={"revenue": ["sum", "mean", "count"]}),
        )
        # S=3 stats; insertion order = list order
        assert result.stat_values.shape[2] == 3
        # East row: sum=160, mean=80, count=2
        np.testing.assert_array_almost_equal(
            result.stat_values[0, 0, :], [160.0, 80.0, 2.0],
        )

    def test_multiple_metrics_separate_nonnull_counts(self, sample_df):
        # Both revenue and units have no nulls in sample_df
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region",
                  values={"revenue": "sum", "units": "sum"}),
        )
        # M=2 metrics
        assert result.nonnull_count.shape[2] == 2
        # Both metrics have non-null counts equal to row_count
        for m_idx in range(2):
            np.testing.assert_array_equal(
                result.nonnull_count[:, 0, m_idx], result.row_count[:, 0],
            )


# === Companion signals ====================================================


class TestRowCount:
    def test_row_count_matches_groupby_size(self, sample_df):
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        # East=2, South=3, West=2
        np.testing.assert_array_equal(result.row_count[:, 0], [2, 3, 2])


class TestNonnullCount:
    @pytest.fixture(params=["pandas", "polars"])
    def df_with_metric_nulls(self, request):
        # revenue has a null for the East/A row
        data = {
            "region": ["East", "East", "West", "West"],
            "product": ["A", "B", "A", "B"],
            "revenue": [None, 70.0, 100.0, 80.0],
        }
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame({
                "region": data["region"],
                "product": data["product"],
                "revenue": pd.Series(data["revenue"], dtype="Float64"),
            })
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    def test_nonnull_count_excludes_null_metric_rows(self, df_with_metric_nulls):
        result = aggregate_data_cells(
            wrap(df_with_metric_nulls),
            _spec(rows="region", cols="product",
                  values={"revenue": "sum"}),
        )
        # East/A has 1 source row but revenue is null → nonnull=0
        # East/B has 1 source row, revenue=70 → nonnull=1
        # West/A has 1 source row, revenue=100 → nonnull=1
        # West/B has 1 source row, revenue=80 → nonnull=1
        np.testing.assert_array_equal(
            result.nonnull_count[:, :, 0],
            [[0, 1], [1, 1]],
        )
        # row_count is still 1 for all four groups
        np.testing.assert_array_equal(
            result.row_count, [[1, 1], [1, 1]],
        )


# === All-null metric (T4c hot path) =======================================


class TestAllNullMetric:
    @pytest.fixture(params=["pandas", "polars"])
    def df_all_null_revenue(self, request):
        # All 3 rows in West group have null revenue
        data = {
            "region": ["West", "West", "West", "East", "East"],
            "revenue": [None, None, None, 90.0, 70.0],
        }
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame({
                "region": data["region"],
                "revenue": pd.Series(data["revenue"], dtype="Float64"),
            })
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    def test_all_null_group_has_nonnull_count_zero(self, df_all_null_revenue):
        result = aggregate_data_cells(
            wrap(df_all_null_revenue),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        # Categories sorted: East, West.
        # East: 2 rows, nonnull=2.
        # West: 3 rows, nonnull=0 (all null) ← T4c's signal
        np.testing.assert_array_equal(
            result.nonnull_count[:, 0, 0], [2, 0],
        )
        np.testing.assert_array_equal(
            result.row_count[:, 0], [2, 3],
        )

    def test_all_null_group_sum_is_zero_not_null(self, df_all_null_revenue):
        # The canary: sum-of-all-null returns 0.0 in both engines.
        # T4c will use nonnull_count==0 to mark this NULL despite the
        # 0.0 in stat_values.
        result = aggregate_data_cells(
            wrap(df_all_null_revenue),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        assert result.stat_values[1, 0, 0] == 0.0  # West sum


# === Edge cases ===========================================================


class TestEdgeCases:
    def test_empty_dataframe(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": pd.Series([], dtype="object"),
            "revenue": pd.Series([], dtype="Float64"),
        })
        result = aggregate_data_cells(
            wrap(df), _spec(rows="region", values={"revenue": "sum"}),
        )
        # No row categories → zero rows in the output arrays
        assert result.stat_values.shape == (0, 1, 1)
        assert result.row_count.shape == (0, 1)

    def test_observed_false_with_unobserved_levels(self, sample_df):
        # sample_df has regions East, South, West; force "North" via levels
        result = aggregate_data_cells(
            wrap(sample_df),
            _spec(rows="region", observed=False,
                  levels={"region": ["East", "South", "West", "North"]},
                  values={"revenue": "sum"}),
        )
        # North is the 4th row, with row_count=0 → T4c will mark EMPTY
        assert result.row_count[3, 0] == 0
        assert result.nonnull_count[3, 0, 0] == 0
        # stat_values for North = 0 (no records contributed)
        assert result.stat_values[3, 0, 0] == 0.0
        # Observed regions populated correctly
        # levels order: East, South, West, North → indices 0,1,2,3
        np.testing.assert_array_equal(
            result.row_count[:, 0], [2, 3, 2, 0],
        )

    def test_dropna_true_drops_null_grouping_rows(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": ["West", "West", None, "East"],
            "revenue": [100.0, 80.0, 50.0, 90.0],
        })
        result = aggregate_data_cells(
            wrap(df),
            _spec(rows="region", dropna=True,
                  values={"revenue": "sum"}),
        )
        # Null-region row dropped → just East and West
        cats = [c.value for c in result.row_categories[0]]
        assert None not in cats
        assert cats == ["East", "West"]

    def test_dropna_false_keeps_missing_category(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": ["West", None, "East"],
            "revenue": [100.0, 50.0, 90.0],
        })
        result = aggregate_data_cells(
            wrap(df),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        cats = result.row_categories[0]
        # Last category is Missing (None value, "Missing" label)
        assert cats[-1].value is None
        assert cats[-1].label == "Missing"
        # The Missing row has the null-grouped record: revenue=50
        assert result.stat_values[-1, 0, 0] == 50.0


class TestPandasNullableNA:
    """Reviewer P1 regression: pd.NA in pandas nullable dtypes was not
    being normalized. The reviewer's exact reproducer is the second test
    here — expected Missing revenue 2.0, actual 0.0 before the fix.
    """

    def test_observed_mode_pd_na_becomes_missing(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": pd.Series(["West", pd.NA, "West"], dtype="string"),
            "revenue": pd.Series([1.0, 2.0, 1.0], dtype="Float64"),
        })
        result = aggregate_data_cells(
            wrap(df),
            _spec(rows="region", values={"revenue": "sum"}),
        )
        values = [c.value for c in result.row_categories[0]]
        # Sorted alphabetical: West, then Missing (None) at the end
        assert values == ["West", None]
        assert result.row_categories[0][-1].label == "Missing"
        # West revenue = 1+1 = 2.0; Missing revenue = 2.0 (the pd.NA row)
        np.testing.assert_array_almost_equal(
            result.stat_values[:, 0, 0], [2.0, 2.0],
        )

    def test_observed_false_with_levels_routes_pd_na_to_missing(self):
        """Reviewer's exact reproducer. Before the fix, the pd.NA row
        contributed 0.0 to Missing (silently dropped); after, it
        contributes its revenue (2.0)."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": pd.Series(["West", pd.NA, "West"], dtype="string"),
            "revenue": pd.Series([1.0, 2.0, 1.0], dtype="Float64"),
        })
        result = aggregate_data_cells(
            wrap(df),
            _spec(rows="region", observed=False,
                  levels={"region": ["West"]},
                  values={"revenue": "sum"}),
        )
        values = [c.value for c in result.row_categories[0]]
        assert values == ["West", None]
        # The critical assertion: Missing revenue must be 2.0, not 0.0
        np.testing.assert_array_almost_equal(
            result.stat_values[:, 0, 0], [2.0, 2.0],
        )
        # Row count and nonnull count should also reflect the pd.NA row
        np.testing.assert_array_equal(result.row_count[:, 0], [2, 1])
        np.testing.assert_array_equal(result.nonnull_count[:, 0, 0], [2, 1])

    def test_nullable_int_pd_na_also_normalized(self):
        """pd.NA appears in every pandas nullable dtype, not just strings.
        Spot-check that Int64 nullable also routes pd.NA to Missing."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "year": pd.Series([2020, pd.NA, 2020, 2021], dtype="Int64"),
            "revenue": pd.Series([10.0, 20.0, 10.0, 30.0], dtype="Float64"),
        })
        result = aggregate_data_cells(
            wrap(df),
            _spec(rows="year", values={"revenue": "sum"}),
        )
        values = [c.value for c in result.row_categories[0]]
        # Sorted numeric, then Missing
        assert values == [2020, 2021, None]
        assert result.row_categories[0][-1].label == "Missing"
