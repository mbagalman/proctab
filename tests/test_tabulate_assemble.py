"""Tests for T4c: assemble_body() — final body + missing matrices and
row/col layouts.

Verifies the section-dispatch table and MissingReason priority. The
TestMissingReasonPriority class is the load-bearing one; it locks in
how the EMPTY / NULL / PRESENT decisions interact, including the
'count' stat exception.
"""

from __future__ import annotations

import numpy as np
import pytest

from proctab._engine import wrap
from proctab.model import MissingReason
from proctab.tabulate import (
    ColLeafEntry,
    RowLeafEntry,
    TabulateAssembled,
    _parse_tabulate_args,
    aggregate_data_cells,
    aggregate_totals,
    assemble_body,
)


def _spec(**kwargs):
    return _parse_tabulate_args(**kwargs)


def _assemble(nw_df, spec):
    """Run T4a + T4b + T4c and return TabulateAssembled."""
    data = aggregate_data_cells(nw_df, spec)
    totals = aggregate_totals(nw_df, spec, data)
    return assemble_body(data, totals, spec)


# === Layout shape =========================================================


class TestRowLayout:
    def test_one_row_no_totals(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=False)
        result = _assemble(wrap(sample_df), spec)
        # 3 regions, no Total
        assert len(result.row_layout) == 3
        assert all(e.role == "data" for e in result.row_layout)
        assert [e.data_row_idx for e in result.row_layout] == [0, 1, 2]

    def test_one_row_with_totals(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        result = _assemble(wrap(sample_df), spec)
        assert len(result.row_layout) == 4
        assert result.row_layout[-1].role == "total"

    def test_two_rows_no_subtotals_no_totals(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"}, totals=False)
        result = _assemble(wrap(sample_df), spec)
        # 3 regions × 2 products = 6, no subtotals or totals
        assert len(result.row_layout) == 6
        assert all(e.role == "data" for e in result.row_layout)

    def test_two_rows_with_subtotals_at_outer(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        result = _assemble(wrap(sample_df), spec)
        # Per region: 2 products + 1 subtotal = 3 entries × 3 regions = 9
        assert len(result.row_layout) == 9
        roles = [e.role for e in result.row_layout]
        # Pattern: data, data, subtotal, data, data, subtotal, data, data, subtotal
        assert roles == ["data", "data", "subtotal"] * 3
        # Subtotal entries point to outer cat indices 0, 1, 2
        sub_indices = [e.subtotal_row_idx for e in result.row_layout
                       if e.role == "subtotal"]
        assert sub_indices == [0, 1, 2]

    def test_two_rows_with_subtotals_and_totals(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=True)
        result = _assemble(wrap(sample_df), spec)
        # 9 (per the previous test) + 1 Grand Total = 10
        assert len(result.row_layout) == 10
        assert result.row_layout[-1].role == "total"


class TestColLayout:
    def test_no_cols_just_stats(self, sample_df):
        # Single metric, single stat → 1 col leaf
        spec = _spec(rows="region", values={"revenue": "sum"})
        result = _assemble(wrap(sample_df), spec)
        assert len(result.col_layout) == 1
        assert result.col_layout[0].role == "data"
        assert result.col_layout[0].stat_idx == 0

    def test_no_cols_multiple_stats(self, sample_df):
        spec = _spec(rows="region",
                     values={"revenue": ["sum", "mean"]})
        result = _assemble(wrap(sample_df), spec)
        assert len(result.col_layout) == 2
        assert [e.stat_idx for e in result.col_layout] == [0, 1]

    def test_no_cols_no_total_col_even_with_totals(self, sample_df):
        # totals=True but cols=() → no Total col block
        spec = _spec(rows="region",
                     values={"revenue": "sum"}, totals=True)
        result = _assemble(wrap(sample_df), spec)
        assert all(e.role == "data" for e in result.col_layout)

    def test_with_cols_and_totals_appends_total_block(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": ["sum", "mean"]},
                     totals=True)
        result = _assemble(wrap(sample_df), spec)
        # 2 product cats × 2 stats + 1 Total col × 2 stats = 6
        assert len(result.col_layout) == 6
        # Last 2 are Total col
        assert result.col_layout[-2].role == "total"
        assert result.col_layout[-1].role == "total"
        # Stats interleave correctly
        for c_i in range(2):
            for s in range(2):
                idx = c_i * 2 + s
                assert result.col_layout[idx].role == "data"
                assert result.col_layout[idx].col_group_idx == c_i
                assert result.col_layout[idx].stat_idx == s


# === Body shape ===========================================================


class TestBodyShape:
    def test_shape_matches_layout_lengths(self, sample_df):
        spec = _spec(rows=["region", "product"], cols=(),
                     values={"revenue": ["sum", "mean"]},
                     subtotals="region", totals=True)
        result = _assemble(wrap(sample_df), spec)
        assert result.body.shape == (
            len(result.row_layout), len(result.col_layout),
        )
        assert result.missing.shape == result.body.shape

    def test_2x1_with_totals_shape(self):
        # 2 rows + 1 col + totals + subtotals
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["W", "W", "E", "E"],
            "product": ["A", "B", "A", "B"],
            "channel": ["x", "x", "y", "y"],
            "revenue": [10, 20, 30, 40],
        })
        spec = _spec(rows=["region", "product"], cols="channel",
                     values={"revenue": "sum"},
                     subtotals="region", totals=True)
        result = _assemble(wrap(df), spec)
        # Row leaves: 4 data + 2 subtotal + 1 total = 7
        # Col leaves: 2 channels × 1 stat + 1 Total × 1 stat = 3
        assert result.body.shape == (7, 3)


# === Body values per section ==============================================


class TestBodyValues:
    def test_data_cell_values(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        result = _assemble(wrap(sample_df), spec)
        # Region sums (alphabetical East, South, West): 160, 180, 180
        np.testing.assert_array_equal(result.body[:3, 0], [160, 180, 180])

    def test_grand_total_cell_in_one_way(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        result = _assemble(wrap(sample_df), spec)
        # Total row value = 160+180+180 = 520
        assert result.body[3, 0] == 520

    def test_subtotal_row_values(self, sample_df):
        # rows=[region, product], subtotals="region"
        # Subtotal at region (across products) per region: 160, 180, 180
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        result = _assemble(wrap(sample_df), spec)
        # Subtotal leaves are at positions 2, 5, 8 in row_layout
        # (after East/A, East/B; after South/A, South/B; after West/A, West/B)
        subtotal_positions = [i for i, e in enumerate(result.row_layout)
                              if e.role == "subtotal"]
        sub_values = result.body[subtotal_positions, 0]
        np.testing.assert_array_equal(sub_values, [160, 180, 180])

    def test_total_col_values_per_row(self):
        # Build a 1-row 1-col case to check grand_col routing
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["W", "W", "E", "E"],
            "channel": ["x", "y", "x", "y"],
            "revenue": [10, 20, 30, 40],
        })
        spec = _spec(rows="region", cols="channel",
                     values={"revenue": "sum"}, totals=True)
        result = _assemble(wrap(df), spec)
        # Layout: row=[E, W, Total], col=[x, y, Total]
        # Body shape (3, 3)
        # Total col per region: E = 30+40 = 70; W = 10+20 = 30
        # Last col is Total
        assert result.body[0, 2] == 70  # E
        assert result.body[1, 2] == 30  # W

    def test_grand_total_cell_in_two_way(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["W", "W", "E", "E"],
            "channel": ["x", "y", "x", "y"],
            "revenue": [10, 20, 30, 40],
        })
        spec = _spec(rows="region", cols="channel",
                     values={"revenue": "sum"}, totals=True)
        result = _assemble(wrap(df), spec)
        # Grand total (last row, last col) = 100
        assert result.body[-1, -1] == 100


# === MissingReason priority ==============================================


class TestMissingReasonPriority:
    """Locks in the per-cell priority: row_count=0 → EMPTY, then
    nonnull=0 (except count stat) → NULL, otherwise PRESENT."""

    def test_present_when_data_real(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        result = _assemble(wrap(sample_df), spec)
        # All cells in this case are populated
        assert np.all(result.missing == MissingReason.PRESENT)

    def test_empty_when_zero_row_group(self, sample_df):
        # observed=False + levels= adds an unobserved category → row_count=0
        spec = _spec(
            rows="region", observed=False,
            levels={"region": ["East", "South", "West", "North"]},
            values={"revenue": "sum"}, totals=True,
        )
        result = _assemble(wrap(sample_df), spec)
        # North is row index 3 (last data row before Total)
        # Find the row_layout entry for North
        north_position = 3  # in user-supplied levels order
        assert result.row_layout[north_position].role == "data"
        assert result.row_layout[north_position].data_row_idx == 3
        # That row should be EMPTY (no source records)
        assert result.missing[north_position, 0] == MissingReason.EMPTY

    def test_null_when_metric_all_null_in_nonempty_group(self):
        """A non-empty group where every metric value is null → NULL
        (except the count stat which reports 0 meaningfully)."""
        pd = pytest.importorskip("pandas")
        # West has 3 rows, ALL revenue null. East has 2 rows with valid revenue.
        df = pd.DataFrame({
            "region": ["W", "W", "W", "E", "E"],
            "revenue": pd.Series([None, None, None, 50.0, 30.0], dtype="Float64"),
        })
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=False)
        result = _assemble(wrap(df), spec)
        # Layout: [E, W] (sorted)
        # E sum = 80 → PRESENT; W sum is all-null → NULL
        assert result.missing[0, 0] == MissingReason.PRESENT
        assert result.body[0, 0] == 80
        assert result.missing[1, 0] == MissingReason.NULL

    def test_count_stat_on_all_null_group_stays_present(self):
        """Reviewer-anticipated exception: count of an all-null group
        is 0 (meaningful), not NULL."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": ["W", "W", "W", "E", "E"],
            "revenue": pd.Series([None, None, None, 50.0, 30.0], dtype="Float64"),
        })
        spec = _spec(rows="region", values={"revenue": "count"}, totals=False)
        result = _assemble(wrap(df), spec)
        # E count = 2 → PRESENT, value 2; W count = 0 → PRESENT, value 0
        assert result.missing[0, 0] == MissingReason.PRESENT
        assert result.body[0, 0] == 2
        assert result.missing[1, 0] == MissingReason.PRESENT
        assert result.body[1, 0] == 0

    def test_empty_dominates_null(self):
        """A zero-record group (EMPTY) takes priority over all-null
        (NULL) — but a zero-record group is also all-null by definition.
        This test confirms the priority order using observed=False+levels
        to create a truly EMPTY (zero-record) group."""
        spec = _spec(
            rows="region", observed=False,
            levels={"region": ["East", "South", "West", "North"]},
            values={"revenue": "sum"}, totals=True,
        )
        # sample_df has no "North" → North row is EMPTY (row_count=0).
        # If we had marked it NULL, the priority would be wrong.
        df = pytest.importorskip("pandas").DataFrame({
            "region": ["East", "East", "West"],
            "revenue": [50.0, 30.0, 20.0],
        })
        result = _assemble(wrap(df), spec)
        north_position = 3
        assert result.missing[north_position, 0] == MissingReason.EMPTY
        # NOT NULL — the priority correctly prefers EMPTY
        assert result.missing[north_position, 0] != MissingReason.NULL


# === Edge cases ===========================================================


class TestEdgeCases:
    def test_empty_dataframe_yields_empty_assembled(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": pd.Series([], dtype="object"),
            "revenue": pd.Series([], dtype="Float64"),
        })
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        result = _assemble(wrap(df), spec)
        assert result.row_layout == ()
        # Col layout still has stat leaves
        assert len(result.col_layout) == 1
        # Body shape (0, 1)
        assert result.body.shape == (0, 1)

    def test_multiple_stats_layout_interleaves(self, sample_df):
        spec = _spec(rows="region",
                     values={"revenue": ["sum", "mean", "count"]},
                     totals=False)
        result = _assemble(wrap(sample_df), spec)
        # 3 col leaves: sum, mean, count
        assert len(result.col_layout) == 3
        assert [e.stat_idx for e in result.col_layout] == [0, 1, 2]
        # Each region row has 3 values
        assert result.body.shape == (3, 3)

    def test_returns_tabulate_assembled(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"})
        result = _assemble(wrap(sample_df), spec)
        assert isinstance(result, TabulateAssembled)
