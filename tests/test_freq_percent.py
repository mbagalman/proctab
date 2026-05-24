"""Tests for F4b: derive_percentages() — body matrix + MissingReason.

These tests construct CountResult inputs directly (skipping F4a) so we
isolate the percentage math from the aggregation kernel.
"""

from __future__ import annotations

import numpy as np
import pytest

from legible.freq import (
    CountResult,
    FreqSpec,
    PercentResult,
    derive_percentages,
)
from legible.model import Category, MissingReason


def _counts_1d(values, cats=None) -> CountResult:
    arr = np.array(values, dtype=np.float64)
    if cats is None:
        cats = tuple(Category(f"cat{i}") for i in range(len(values)))
    return CountResult(row_categories=cats, col_categories=None, counts=arr)


def _counts_2d(matrix, row_cats=None, col_cats=None) -> CountResult:
    arr = np.array(matrix, dtype=np.float64)
    R, C = arr.shape
    if row_cats is None:
        row_cats = tuple(Category(f"r{i}") for i in range(R))
    if col_cats is None:
        col_cats = tuple(Category(f"c{j}") for j in range(C))
    return CountResult(row_categories=row_cats, col_categories=col_cats, counts=arr)


def _spec(keys, **kwargs) -> FreqSpec:
    return FreqSpec(keys=tuple(keys), **kwargs)


# === One-way ================================================================


class TestOneWayBasic:
    def test_returns_percent_result(self):
        result = derive_percentages(_counts_1d([2, 3, 2]), _spec(("region",)))
        assert isinstance(result, PercentResult)

    def test_stat_categories_are_n_pct_cumn_cumpct(self):
        result = derive_percentages(_counts_1d([2, 3, 2]), _spec(("region",)))
        values = [c.value for c in result.stat_categories]
        assert values == ["N", "Pct", "CumN", "CumPct"]

    def test_body_shape_with_totals(self):
        result = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=True))
        assert result.body.shape == (4, 4)
        assert result.has_row_total is True

    def test_body_shape_without_totals(self):
        result = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=False))
        assert result.body.shape == (3, 4)
        assert result.has_row_total is False

    def test_n_column_matches_input(self):
        result = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=True))
        np.testing.assert_array_equal(result.body[:, 0], [2, 3, 2, 7])

    def test_pct_column_values(self):
        result = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=True))
        expected = [2/7*100, 3/7*100, 2/7*100, 100.0]
        np.testing.assert_array_almost_equal(result.body[:, 1], expected)

    def test_cumn_column_values(self):
        result = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=True))
        np.testing.assert_array_equal(result.body[:, 2], [2, 5, 7, 7])

    def test_cumpct_column_values(self):
        result = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=True))
        expected = [2/7*100, 5/7*100, 100.0, 100.0]
        np.testing.assert_array_almost_equal(result.body[:, 3], expected)

    def test_no_missing_when_all_present(self):
        result = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=True))
        assert np.all(result.missing == MissingReason.PRESENT)


class TestOneWayEdge:
    def test_empty_counts_yields_empty_body(self):
        result = derive_percentages(_counts_1d([]), _spec(("x",), totals=True))
        assert result.body.shape == (0, 4)
        assert result.has_row_total is False

    def test_all_zero_counts_na_percent_cells(self):
        result = derive_percentages(
            _counts_1d([0, 0, 0]), _spec(("x",), totals=True))
        # N and CumN cells are PRESENT with value 0
        np.testing.assert_array_equal(result.body[:, 0], [0, 0, 0, 0])
        np.testing.assert_array_equal(result.body[:, 2], [0, 0, 0, 0])
        assert np.all(result.missing[:, 0] == MissingReason.PRESENT)
        assert np.all(result.missing[:, 2] == MissingReason.PRESENT)
        # Pct and CumPct: NA across the board (divide by zero)
        assert np.all(result.missing[:, 1] == MissingReason.NOT_APPLICABLE)
        assert np.all(result.missing[:, 3] == MissingReason.NOT_APPLICABLE)

    def test_single_category_count(self):
        result = derive_percentages(_counts_1d([5]), _spec(("x",), totals=True))
        np.testing.assert_array_equal(result.body[:, 0], [5, 5])
        np.testing.assert_array_equal(result.body[:, 1], [100.0, 100.0])
        np.testing.assert_array_equal(result.body[:, 2], [5, 5])
        np.testing.assert_array_equal(result.body[:, 3], [100.0, 100.0])


# === Two-way ================================================================


class TestTwoWayBasic:
    """Baseline counts for these tests:
        [[1, 1],
         [2, 1],
         [1, 1]]
    row_sums = [2, 3, 2]; col_sums = [4, 3]; grand = 7
    """
    BASE = [[1, 1], [2, 1], [1, 1]]

    def test_returns_percent_result(self):
        result = derive_percentages(_counts_2d(self.BASE), _spec(("r", "c")))
        assert isinstance(result, PercentResult)

    def test_stat_labels(self):
        result = derive_percentages(_counts_2d(self.BASE), _spec(("r", "c")))
        labels = [c.label or c.value for c in result.stat_categories]
        assert labels == ["N", "Row%", "Col%", "Tot%"]

    def test_body_shape_with_totals(self):
        result = derive_percentages(
            _counts_2d(self.BASE), _spec(("r", "c"), totals=True))
        # (3+1) row groups × (2+1) col groups × 4 stats = (4, 12)
        assert result.body.shape == (4, 12)
        assert result.has_row_total is True
        assert result.has_col_total is True

    def test_body_shape_without_totals(self):
        result = derive_percentages(
            _counts_2d(self.BASE), _spec(("r", "c"), totals=False))
        assert result.body.shape == (3, 8)
        assert result.has_row_total is False
        assert result.has_col_total is False

    def test_n_cells(self):
        # Total col index in body = n_cols_data * n_stats = 2 * 4 = 8
        result = derive_percentages(
            _counts_2d(self.BASE), _spec(("r", "c"), totals=True))
        # Data N cells
        assert result.body[0, 0] == 1   # r0, c0
        assert result.body[0, 4] == 1   # r0, c1
        assert result.body[1, 0] == 2   # r1, c0
        assert result.body[1, 4] == 1   # r1, c1
        # Total col N cells: row_sums
        assert result.body[0, 8] == 2
        assert result.body[1, 8] == 3
        assert result.body[2, 8] == 2
        # Total row N cells: col_sums + grand
        assert result.body[3, 0] == 4
        assert result.body[3, 4] == 3
        assert result.body[3, 8] == 7

    def test_row_percent_cells(self):
        result = derive_percentages(
            _counts_2d(self.BASE), _spec(("r", "c"), totals=True))
        # Stat 1 = Row%
        # Row 0: 1/2*100, 1/2*100, Total col Row% = 100
        assert result.body[0, 1] == 50.0
        assert result.body[0, 5] == 50.0
        assert result.body[0, 9] == 100.0
        # Row 1: 2/3*100, 1/3*100, 100
        assert result.body[1, 1] == pytest.approx(2/3*100)
        assert result.body[1, 5] == pytest.approx(1/3*100)
        assert result.body[1, 9] == 100.0
        # Total row Row% (col_sum / grand): 4/7, 3/7, 100
        assert result.body[3, 1] == pytest.approx(4/7*100)
        assert result.body[3, 5] == pytest.approx(3/7*100)
        assert result.body[3, 9] == 100.0

    def test_col_percent_cells(self):
        result = derive_percentages(
            _counts_2d(self.BASE), _spec(("r", "c"), totals=True))
        # Stat 2 = Col%
        # Row 0: 1/4*100=25, 1/3*100, Total col Col% = 2/7*100
        assert result.body[0, 2] == 25.0
        assert result.body[0, 6] == pytest.approx(1/3*100)
        assert result.body[0, 10] == pytest.approx(2/7*100)
        # Total row Col% = 100 by definition for every col
        assert result.body[3, 2] == 100.0
        assert result.body[3, 6] == 100.0
        assert result.body[3, 10] == 100.0

    def test_tot_percent_cells(self):
        result = derive_percentages(
            _counts_2d(self.BASE), _spec(("r", "c"), totals=True))
        # Stat 3 = Tot% (n / grand)
        # Row 0: 1/7, 1/7, 2/7
        assert result.body[0, 3] == pytest.approx(1/7*100)
        assert result.body[0, 7] == pytest.approx(1/7*100)
        assert result.body[0, 11] == pytest.approx(2/7*100)
        # Total row Tot%: 4/7, 3/7, 100
        assert result.body[3, 3] == pytest.approx(4/7*100)
        assert result.body[3, 7] == pytest.approx(3/7*100)
        assert result.body[3, 11] == 100.0

    def test_no_missing_when_all_present(self):
        result = derive_percentages(
            _counts_2d(self.BASE), _spec(("r", "c"), totals=True))
        assert np.all(result.missing == MissingReason.PRESENT)


class TestTwoWayDivByZero:
    def test_all_zero_row_marks_row_percent_na(self):
        # Row 1 is all zeros → row_sum[1] = 0 → Row% NA in row 1
        result = derive_percentages(
            _counts_2d([[1, 1], [0, 0], [1, 1]]),
            _spec(("r", "c"), totals=True),
        )
        # Row% in row 1: data cols + Total col
        assert result.missing[1, 1] == MissingReason.NOT_APPLICABLE
        assert result.missing[1, 5] == MissingReason.NOT_APPLICABLE
        assert result.missing[1, 9] == MissingReason.NOT_APPLICABLE
        # N in row 1 is still PRESENT with value 0
        assert result.missing[1, 0] == MissingReason.PRESENT
        assert result.body[1, 0] == 0
        # Col% in row 1: denominators are col_sums (>0), so values are
        # 0/col_sum * 100 = 0 — PRESENT, not NA
        assert result.missing[1, 2] == MissingReason.PRESENT
        assert result.body[1, 2] == 0
        # Other rows have valid Row%
        assert result.missing[0, 1] == MissingReason.PRESENT
        assert result.missing[2, 1] == MissingReason.PRESENT

    def test_all_zero_col_marks_col_percent_na(self):
        # Col 1 all zeros → col_sum[1] = 0 → Col% NA in col 1
        result = derive_percentages(
            _counts_2d([[1, 0], [2, 0], [1, 0]]),
            _spec(("r", "c"), totals=True),
        )
        # Col% in col 1: data rows + Total row
        # j=1, stat 2 → col index = 1*4 + 2 = 6
        assert result.missing[0, 6] == MissingReason.NOT_APPLICABLE
        assert result.missing[1, 6] == MissingReason.NOT_APPLICABLE
        assert result.missing[2, 6] == MissingReason.NOT_APPLICABLE
        assert result.missing[3, 6] == MissingReason.NOT_APPLICABLE


class TestTwoWayEdge:
    def test_empty_returns_empty_body(self):
        empty = CountResult(
            row_categories=(), col_categories=(),
            counts=np.zeros((0, 0), dtype=np.float64),
        )
        result = derive_percentages(empty, _spec(("r", "c"), totals=True))
        assert result.body.shape == (0, 0)
        assert result.has_row_total is False
        assert result.has_col_total is False

    def test_row_only_empty(self):
        result = derive_percentages(
            CountResult(
                row_categories=(),
                col_categories=(Category("a"), Category("b")),
                counts=np.zeros((0, 2), dtype=np.float64),
            ),
            _spec(("r", "c"), totals=True),
        )
        # No row data, no Total row/col
        assert result.body.shape == (0, 8)
        assert result.has_row_total is False
        assert result.has_col_total is False

    def test_col_only_empty(self):
        result = derive_percentages(
            CountResult(
                row_categories=(Category("a"), Category("b")),
                col_categories=(),
                counts=np.zeros((2, 0), dtype=np.float64),
            ),
            _spec(("r", "c"), totals=True),
        )
        assert result.body.shape == (2, 0)
        assert result.has_row_total is False
        assert result.has_col_total is False


class TestPercentResultMetadata:
    def test_pass_through_row_categories(self):
        cats = (Category("West"), Category("East"))
        counts = CountResult(
            row_categories=cats, col_categories=None,
            counts=np.array([2.0, 3.0]),
        )
        result = derive_percentages(counts, _spec(("region",)))
        assert result.row_categories == cats
        assert result.col_categories is None

    def test_value_kinds_one_way(self):
        result = derive_percentages(_counts_1d([1]), _spec(("x",)))
        assert result.stat_value_kinds == ("count", "percent", "count", "percent")

    def test_value_kinds_two_way(self):
        result = derive_percentages(_counts_2d([[1, 1]]), _spec(("r", "c")))
        assert result.stat_value_kinds == ("count", "percent", "percent", "percent")

    def test_formats_one_way(self):
        result = derive_percentages(_counts_1d([1]), _spec(("x",)))
        assert result.stat_formats == ("{:.0f}", "{:.1f}%", "{:.0f}", "{:.1f}%")

    def test_formats_two_way(self):
        result = derive_percentages(_counts_2d([[1, 1]]), _spec(("r", "c")))
        assert result.stat_formats == ("{:.0f}", "{:.1f}%", "{:.1f}%", "{:.1f}%")
