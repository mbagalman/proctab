"""Smoke tests for the public lg.tabulate() entry point.

Verifies the T2-T5 pipeline composes correctly through the public API.
Deep integration tests (does tabulate() reproduce the v0.1-clean
example_2 fixture?) land in T7; broad edge-case coverage in T8.
"""

from __future__ import annotations

import numpy as np
import pytest

import legible as lg
from legible.model import Table, TotalMarker


class TestOneRowThroughPublicAPI:
    def test_returns_table(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum"})
        assert isinstance(table, Table)

    def test_axes_validate(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum"})
        table.row_axis.validate()
        table.col_axis.validate()

    def test_body_shape_matches_axis_leaves(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum"}, totals=True)
        assert table.body.shape == (
            len(table.row_axis.leaves()),
            len(table.col_axis.leaves()),
        )

    def test_row_dim_name(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum"})
        assert [d.name for d in table.row_axis.dims] == ["region"]

    def test_col_dims_metric_stat(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum"})
        assert [d.name for d in table.col_axis.dims] == ["_metric", "_stat"]

    def test_includes_total_by_default(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum"})
        leaves = table.row_axis.leaves()
        assert leaves[-1].role == "total"

    def test_totals_false_omits_total_row(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum"}, totals=False)
        leaves = table.row_axis.leaves()
        assert all(leaf.role == "data" for leaf in leaves)

    def test_renders_to_text(self, sample_df):
        # Full pipeline + renderer round-trip
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum"})
        text = table.to_text()
        assert "East" in text
        assert "South" in text
        assert "Total" in text


class TestTwoRowsThroughPublicAPI:
    def test_returns_table(self, sample_df):
        table = lg.tabulate(sample_df, rows=["region", "product"],
                            values={"revenue": "sum"})
        assert isinstance(table, Table)

    def test_dims_per_axis(self, sample_df):
        table = lg.tabulate(sample_df, rows=["region", "product"],
                            values={"revenue": "sum"})
        assert [d.name for d in table.row_axis.dims] == ["region", "product"]

    def test_with_subtotals_and_totals(self, sample_df):
        table = lg.tabulate(sample_df, rows=["region", "product"],
                            values={"revenue": "sum"},
                            subtotals="region", totals=True)
        leaves = table.row_axis.leaves()
        # Per region: 2 data + 1 subtotal; × 3 regions; + 1 grand total = 10
        assert len(leaves) == 10
        assert leaves[-1].role == "total"
        assert leaves[2].role == "subtotal"

    def test_subtotal_values_correct(self, sample_df):
        table = lg.tabulate(sample_df, rows=["region", "product"],
                            values={"revenue": "sum"},
                            subtotals="region", totals=False)
        # Subtotal positions: 2, 5, 8 (after each region's 2 data rows)
        # Region sums (alphabetical): East=160, South=180, West=180
        assert table.body[2, 0] == 160
        assert table.body[5, 0] == 180
        assert table.body[8, 0] == 180


class TestWithColsThroughPublicAPI:
    @pytest.fixture
    def df_three_cols(self):
        pd = pytest.importorskip("pandas")
        return pd.DataFrame({
            "region":  ["W", "W", "E", "E"],
            "product": ["A", "B", "A", "B"],
            "channel": ["x", "x", "y", "y"],
            "revenue": [10, 20, 30, 40],
        })

    def test_with_cols_and_totals(self, df_three_cols):
        table = lg.tabulate(
            df_three_cols, rows="region", cols="channel",
            values={"revenue": "sum"}, totals=True,
        )
        # Row leaves: 2 regions + 1 Total = 3
        # Col leaves: 2 channels × 1 stat + 1 Total = 3
        assert table.body.shape == (3, 3)
        assert isinstance(table.col_axis.tree.children[-1].path[0], TotalMarker)

    def test_compound_subtotals_with_cols(self, df_three_cols):
        table = lg.tabulate(
            df_three_cols, rows=["region", "product"], cols="channel",
            values={"revenue": "sum"},
            subtotals="region", totals=True,
        )
        # Row leaves: 2 region × (2 product + 1 sub) + 1 grand total = 7
        # Col leaves: 2 channel × 1 stat + 1 Total = 3
        assert table.body.shape == (7, 3)
        table.row_axis.validate()
        table.col_axis.validate()


class TestMultipleStatsAndMetrics:
    def test_multiple_stats_one_metric(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": ["sum", "mean", "count"]})
        # 3 stats × 1 metric = 3 col leaves
        assert len(table.col_axis.leaves()) == 3
        # East sum=160, mean=80, count=2
        assert table.body[0, 0] == 160
        assert table.body[0, 1] == 80
        assert table.body[0, 2] == 2

    def test_multiple_metrics(self, sample_df):
        table = lg.tabulate(sample_df, rows="region",
                            values={"revenue": "sum", "units": "sum"})
        # 2 metrics × 1 stat = 2 col leaves
        assert len(table.col_axis.leaves()) == 2


class TestErrorsThroughPublicAPI:
    def test_missing_metric_column_raises_keyerror(self, sample_df):
        # Metric must exist in the DataFrame
        with pytest.raises(KeyError, match="not found"):
            lg.tabulate(sample_df, rows="region",
                        values={"nonexistent": "sum"})

    def test_missing_row_column_raises_keyerror(self, sample_df):
        with pytest.raises(KeyError, match="not found"):
            lg.tabulate(sample_df, rows="nonexistent",
                        values={"revenue": "sum"})

    def test_three_rows_raises_valueerror(self, sample_df):
        with pytest.raises(ValueError, match="at most 2 rows"):
            lg.tabulate(sample_df, rows=["region", "product", "units"],
                        values={"revenue": "sum"})

    def test_two_cols_raises_valueerror(self, sample_df):
        with pytest.raises(ValueError, match="at most 1 cols"):
            lg.tabulate(sample_df, rows="region",
                        cols=["product", "units"],
                        values={"revenue": "sum"})

    def test_rows_cols_overlap_raises(self, sample_df):
        with pytest.raises(ValueError, match="cannot share dims"):
            lg.tabulate(sample_df, rows="region", cols="region",
                        values={"revenue": "sum"})

    def test_unknown_stat_raises(self, sample_df):
        with pytest.raises(ValueError, match="unknown stat"):
            lg.tabulate(sample_df, rows="region",
                        values={"revenue": "stddev"})

    def test_weighted_mean_raises_notimplemented(self, sample_df):
        with pytest.raises(NotImplementedError, match="v0.2"):
            lg.tabulate(sample_df, rows="region",
                        values={"revenue": "weighted_mean"})

    def test_weight_raises_notimplemented(self, sample_df):
        with pytest.raises(NotImplementedError, match="v0.2"):
            lg.tabulate(sample_df, rows="region",
                        values={"revenue": "sum"},
                        weight={"revenue": "units"})

    def test_test_raises_notimplemented(self, sample_df):
        with pytest.raises(NotImplementedError, match="v0.2"):
            lg.tabulate(sample_df, rows="region",
                        values={"revenue": "sum"}, test="chi2")

    def test_innermost_subtotal_raises(self, sample_df):
        with pytest.raises(ValueError, match="innermost"):
            lg.tabulate(sample_df, rows=["region", "product"],
                        values={"revenue": "sum"},
                        subtotals="product")

    def test_non_dataframe_raises_typeerror(self):
        with pytest.raises(TypeError):
            lg.tabulate([1, 2, 3], rows="region",
                        values={"revenue": "sum"})


class TestPublicExport:
    def test_tabulate_importable_from_package(self):
        assert lg.tabulate is not None
        assert callable(lg.tabulate)
