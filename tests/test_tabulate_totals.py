"""Tests for T4b: aggregate_totals() — subtotal and grand-total
aggregations computed FROM SOURCE.

The critical correctness test is for non-additive stats (mean, median):
a subtotal computed from source must NOT equal naive cell aggregation.
The TestNonAdditiveCorrectness class is the load-bearing one.
"""

from __future__ import annotations

import numpy as np
import pytest

from legible._engine import wrap
from legible.tabulate import (
    SectionResult,
    TotalsResult,
    _parse_tabulate_args,
    aggregate_data_cells,
    aggregate_totals,
)


def _spec(**kwargs):
    return _parse_tabulate_args(**kwargs)


def _both(nw_df, spec):
    """Run T4a + T4b and return (data_result, totals_result)."""
    data = aggregate_data_cells(nw_df, spec)
    totals = aggregate_totals(nw_df, spec, data)
    return data, totals


# === Empty / no-op cases ===================================================


class TestNoTotalsNoSubtotals:
    def test_returns_all_none_empty(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"},
                     totals=False)
        _, totals = _both(wrap(sample_df), spec)
        assert isinstance(totals, TotalsResult)
        assert totals.subtotals_data_cols == {}
        assert totals.subtotals_total_col == {}
        assert totals.grand_row is None
        assert totals.grand_col is None
        assert totals.grand_cell is None


class TestSubtotalsOnly:
    """Subtotal at outer row dim, totals=False → only subtotals_data_cols populated."""

    def test_two_rows_no_cols_no_totals(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        _, totals = _both(wrap(sample_df), spec)
        assert "region" in totals.subtotals_data_cols
        assert totals.subtotals_total_col == {}  # no Total col w/o totals
        assert totals.grand_row is None
        assert totals.grand_col is None
        assert totals.grand_cell is None


class TestGrandRowOnly:
    """1- or 2-row, no cols, totals=True → grand_row only (no grand_col / grand_cell)."""

    def test_one_row_zero_col_totals_true(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        _, totals = _both(wrap(sample_df), spec)
        assert totals.grand_row is not None
        assert totals.grand_col is None
        assert totals.grand_cell is None

    def test_grand_row_shape(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        _, totals = _both(wrap(sample_df), spec)
        # 1 row, 1 col (implicit), 1 stat
        assert totals.grand_row.stat_values.shape == (1, 1, 1)

    def test_grand_row_value_is_total_sum(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        _, totals = _both(wrap(sample_df), spec)
        # Total revenue across all 7 rows = 520
        assert totals.grand_row.stat_values[0, 0, 0] == 520.0


class TestGrandFullSet:
    """1+ rows AND cols=non-empty AND totals=True → grand_row + grand_col + grand_cell."""

    def test_one_row_one_col_all_three(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": "sum"}, totals=True)
        _, totals = _both(wrap(sample_df), spec)
        assert totals.grand_row is not None
        assert totals.grand_col is not None
        assert totals.grand_cell is not None

    def test_shapes_one_row_one_col(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": "sum"}, totals=True)
        data, totals = _both(wrap(sample_df), spec)
        R, C, S = data.stat_values.shape
        assert totals.grand_row.stat_values.shape == (1, C, S)
        assert totals.grand_col.stat_values.shape == (R, 1, S)
        assert totals.grand_cell.stat_values.shape == (1, 1, S)

    def test_grand_cell_equals_total_sum(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": "sum"}, totals=True)
        _, totals = _both(wrap(sample_df), spec)
        assert totals.grand_cell.stat_values[0, 0, 0] == 520.0

    def test_grand_row_per_product(self, sample_df):
        # cols=product, so grand_row has one entry per product.
        # Product A total revenue: 100+90+60+65 = 315
        # Product B total revenue:  80+70+55     = 205
        # Sorted alphabetically: A=315, B=205
        spec = _spec(rows="region", cols="product",
                     values={"revenue": "sum"}, totals=True)
        _, totals = _both(wrap(sample_df), spec)
        np.testing.assert_array_equal(
            totals.grand_row.stat_values[0, :, 0], [315.0, 205.0],
        )

    def test_grand_col_per_region(self, sample_df):
        # rows=region, so grand_col has one entry per region.
        # Region totals: East=160, South=180, West=180 (alphabetical)
        spec = _spec(rows="region", cols="product",
                     values={"revenue": "sum"}, totals=True)
        _, totals = _both(wrap(sample_df), spec)
        np.testing.assert_array_equal(
            totals.grand_col.stat_values[:, 0, 0], [160.0, 180.0, 180.0],
        )


# === Subtotal-with-Total-col compound case ================================


class TestSubtotalsAndTotalsCompound:
    """2 rows + 1 (non-overlapping) col + subtotals + totals=True → all
    five sections populated. sample_df has no third categorical column,
    so we build a custom DataFrame with rows=[region, product], cols=[channel]."""

    def test_all_five_sections_populated(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["West", "West", "East", "East", "West"],
            "product": ["A",    "B",    "A",    "B",    "A"],
            "channel": ["x",    "x",    "y",    "y",    "y"],
            "revenue": [100,    50,     90,     70,     200],
        })
        spec = _spec(rows=["region", "product"], cols="channel",
                     values={"revenue": "sum"},
                     subtotals="region", totals=True)
        _, totals = _both(wrap(df), spec)
        assert "region" in totals.subtotals_data_cols
        assert "region" in totals.subtotals_total_col
        assert totals.grand_row is not None
        assert totals.grand_col is not None
        assert totals.grand_cell is not None

    def test_section_shapes_match_dimensions(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["West", "West", "East", "East", "West"],
            "product": ["A",    "B",    "A",    "B",    "A"],
            "channel": ["x",    "x",    "y",    "y",    "y"],
            "revenue": [100,    50,     90,     70,     200],
        })
        spec = _spec(rows=["region", "product"], cols="channel",
                     values={"revenue": "sum"},
                     subtotals="region", totals=True)
        data, totals = _both(wrap(df), spec)
        n_regions = len(data.row_categories[0])
        n_channels = len(data.col_categories[0])
        n_row_groups = data.stat_values.shape[0]
        # Subtotal under data cols: (n_regions, n_channels, 1)
        assert totals.subtotals_data_cols["region"].stat_values.shape == \
            (n_regions, n_channels, 1)
        # Subtotal under Total col: (n_regions, 1, 1)
        assert totals.subtotals_total_col["region"].stat_values.shape == \
            (n_regions, 1, 1)
        # Grand row: (1, n_channels, 1)
        assert totals.grand_row.stat_values.shape == (1, n_channels, 1)
        # Grand col: (n_row_groups, 1, 1)
        assert totals.grand_col.stat_values.shape == (n_row_groups, 1, 1)
        # Grand cell: (1, 1, 1)
        assert totals.grand_cell.stat_values.shape == (1, 1, 1)


# === Non-additive correctness (the load-bearing test) ====================


class TestNonAdditiveCorrectness:
    """Subtotals of non-additive stats (mean, median) MUST be computed
    from source, not by averaging leaf cells. This is the test that
    validates the entire T4b architectural decision."""

    @pytest.fixture
    def df_uneven(self):
        # West/A has 2 rows (100, 200) — count varies
        # West/B has 1 row (50)
        # West subtotal mean from source: (100+200+50)/3 = 116.6667
        # Naive cell mean: (mean(West/A) + mean(West/B)) / 2
        #                = (150 + 50) / 2 = 100 ← WRONG
        pd = pytest.importorskip("pandas")
        return pd.DataFrame({
            "region":  ["West", "West", "West", "East", "East", "East"],
            "product": ["A",    "A",    "B",    "A",    "B",    "B"],
            "revenue": [100.0,  200.0,  50.0,   80.0,   60.0,   40.0],
        })

    def test_subtotal_mean_from_source_not_cells(self, df_uneven):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "mean"},
                     subtotals="region", totals=False)
        _, totals = _both(wrap(df_uneven), spec)
        sub = totals.subtotals_data_cols["region"]
        # Categories alphabetical: East, West
        # East mean from source: (80+60+40)/3 = 60
        # West mean from source: (100+200+50)/3 = 116.6667
        np.testing.assert_array_almost_equal(
            sub.stat_values[:, 0, 0], [60.0, 350.0 / 3.0],
        )

    def test_subtotal_mean_does_not_equal_naive_cell_mean(self, df_uneven):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "mean"},
                     subtotals="region", totals=False)
        data, totals = _both(wrap(df_uneven), spec)
        sub = totals.subtotals_data_cols["region"]
        # Compute naive (wrong) cell-mean and confirm the actual subtotal
        # differs from it — locks in the correctness contract.
        # data.stat_values shape (4, 1, 1): rows = East/A, East/B, West/A, West/B
        naive_west = (data.stat_values[2, 0, 0] + data.stat_values[3, 0, 0]) / 2
        actual_west = sub.stat_values[1, 0, 0]  # West is row 1 (alphabetical)
        assert naive_west != actual_west
        assert actual_west == pytest.approx(350.0 / 3.0)

    def test_subtotal_sum_matches_cell_sum_for_additive(self, df_uneven):
        # sum IS additive — both methods give same answer (this is the
        # control to show the non-additive issue is real, not noise)
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        data, totals = _both(wrap(df_uneven), spec)
        sub = totals.subtotals_data_cols["region"]
        # West sum from source: 100+200+50 = 350
        # West sum from cells: cells[2]+cells[3] = 300+50 = 350 ✓
        assert sub.stat_values[1, 0, 0] == 350.0
        cell_sum_west = data.stat_values[2, 0, 0] + data.stat_values[3, 0, 0]
        assert cell_sum_west == 350.0


# === Subtotal value correctness ===========================================


class TestSubtotalValues:
    """Direct numeric checks of subtotal sums against hand-computed values."""

    def test_subtotal_sum_per_region(self, sample_df):
        """sample_df: East rev=160, South rev=180, West rev=180."""
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        _, totals = _both(wrap(sample_df), spec)
        sub = totals.subtotals_data_cols["region"]
        np.testing.assert_array_equal(
            sub.stat_values[:, 0, 0], [160.0, 180.0, 180.0],
        )

    def test_subtotal_count_per_region(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "count"},
                     subtotals="region", totals=False)
        _, totals = _both(wrap(sample_df), spec)
        sub = totals.subtotals_data_cols["region"]
        # East=2, South=3, West=2
        np.testing.assert_array_equal(
            sub.stat_values[:, 0, 0], [2.0, 3.0, 2.0],
        )

    def test_subtotal_row_count_per_region(self, sample_df):
        # row_count companion signal also exposed per subtotal
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        _, totals = _both(wrap(sample_df), spec)
        sub = totals.subtotals_data_cols["region"]
        np.testing.assert_array_equal(sub.row_count[:, 0], [2, 3, 2])


# === Edge cases ===========================================================


class TestEmptyData:
    def test_empty_df_yields_no_totals(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": pd.Series([], dtype="object"),
            "revenue": pd.Series([], dtype="Float64"),
        })
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        _, totals = _both(wrap(df), spec)
        # No row leaves → no grand_row even with totals=True
        assert totals.grand_row is None
        assert totals.grand_col is None
        assert totals.grand_cell is None

    def test_observed_false_with_levels_includes_grand_row(self, sample_df):
        # Even with unobserved categories from levels=, row leaves exist
        # so grand_row should be computed.
        spec = _spec(
            rows="region", observed=False,
            levels={"region": ["East", "South", "West", "North"]},
            values={"revenue": "sum"}, totals=True,
        )
        _, totals = _both(wrap(sample_df), spec)
        assert totals.grand_row is not None
        # Grand sum over all source = 520 (North contributes nothing)
        assert totals.grand_row.stat_values[0, 0, 0] == 520.0
