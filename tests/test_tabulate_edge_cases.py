"""T8 — Edge-case integration tests through the public lg.tabulate() API.

Belt-and-braces coverage. Some scenarios are tested at lower layers
(T2 parser, T4a–T4c, T5); T8 verifies behavior end-to-end and locks in
contracts that are most visible to users — especially:

- EMPTY vs NULL distinction (TestAllNullValueColumn)
- non-additive subtotal correctness (TestNonAdditiveSubtotalEndToEnd)
- Missing-category propagation under various dropna/observed configs

Out of scope (already covered at T6 smoke level): KeyError on missing
cols, dim cap violations, reserved kwargs, innermost-dim subtotal,
non-DataFrame inputs.
"""

from __future__ import annotations

import numpy as np
import pytest

import legible as lg
from legible.model import MissingReason


# === Empty DataFrame =======================================================


class TestEmptyDataFrame:
    @pytest.fixture(params=["pandas", "polars"])
    def empty_df(self, request):
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame({
                "region": pd.Series([], dtype="object"),
                "revenue": pd.Series([], dtype="Float64"),
            })
        pl = pytest.importorskip("polars")
        return pl.DataFrame(schema={
            "region": pl.String, "revenue": pl.Float64,
        })

    def test_yields_zero_row_leaves(self, empty_df):
        table = lg.tabulate(empty_df, rows="region",
                            values={"revenue": "sum"})
        assert len(table.row_axis.leaves()) == 0

    def test_col_axis_still_has_stat_leaves(self, empty_df):
        table = lg.tabulate(empty_df, rows="region",
                            values={"revenue": "sum"})
        # Col axis independent of row data
        assert len(table.col_axis.leaves()) == 1

    def test_body_shape_zero_rows(self, empty_df):
        table = lg.tabulate(empty_df, rows="region",
                            values={"revenue": "sum"}, totals=True)
        assert table.body.shape == (0, 1)

    def test_axes_validate(self, empty_df):
        table = lg.tabulate(empty_df, rows="region",
                            values={"revenue": "sum"})
        table.row_axis.validate()
        table.col_axis.validate()

    def test_renders_to_text(self, empty_df):
        table = lg.tabulate(empty_df, rows="region",
                            values={"revenue": "sum"})
        # Should not raise; headers still render
        text = table.to_text()
        assert "revenue" in text


# === All-null value column (NULL semantics through public API) ============


class TestAllNullValueColumn:
    """The load-bearing T4c contract surfaces at the public level:
    a non-empty group whose metric is all-null gets NULL (except for
    the count stat, which correctly reports 0)."""

    @pytest.fixture(params=["pandas", "polars"])
    def df(self, request):
        # West: 2 rows, revenue all null. East: 2 rows, revenue valid.
        data = {
            "region":  ["W", "W", "E", "E"],
            "revenue": [None, None, 100.0, 200.0],
        }
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame({
                "region": data["region"],
                "revenue": pd.Series(data["revenue"], dtype="Float64"),
            })
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    def test_sum_on_all_null_group_is_null_not_zero(self, df):
        table = lg.tabulate(df, rows="region",
                            values={"revenue": "sum"}, totals=False)
        # Categories alphabetical: East, West
        # East row 0: PRESENT with value 300
        assert table.missing[0, 0] == MissingReason.PRESENT
        assert table.body[0, 0] == 300.0
        # West row 1: NULL (records exist but all-null metric)
        assert table.missing[1, 0] == MissingReason.NULL

    def test_mean_on_all_null_group_is_null(self, df):
        table = lg.tabulate(df, rows="region",
                            values={"revenue": "mean"}, totals=False)
        assert table.missing[1, 0] == MissingReason.NULL

    def test_count_on_all_null_group_is_present_zero(self, df):
        # The count exception: count of all-null group is 0 (meaningful),
        # not NULL.
        table = lg.tabulate(df, rows="region",
                            values={"revenue": "count"}, totals=False)
        # East count = 2, West count = 0
        assert table.missing[0, 0] == MissingReason.PRESENT
        assert table.body[0, 0] == 2
        assert table.missing[1, 0] == MissingReason.PRESENT
        assert table.body[1, 0] == 0


# === Null grouping columns (dropna both ways) =============================


class TestNullGroupingDropna:
    @pytest.fixture(params=["pandas", "polars"])
    def df_partial_nulls(self, request):
        data = {
            "region":  ["W", "W", None, "E"],
            "revenue": [100.0, 80.0, 50.0, 90.0],
        }
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame(data)
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    def test_dropna_false_creates_missing_row(self, df_partial_nulls):
        table = lg.tabulate(df_partial_nulls, rows="region",
                            values={"revenue": "sum"}, totals=False)
        # Categories: East, West, Missing → 3 row leaves
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        values = [leaf.path[0].value for leaf in data_leaves]
        assert values == ["E", "W", None]
        # Last data leaf is the synthetic Missing
        assert data_leaves[-1].path[0].label == "Missing"
        # Body values: E=90, W=180, Missing=50
        np.testing.assert_array_equal(table.body[:, 0], [90, 180, 50])

    def test_dropna_true_drops_null_rows(self, df_partial_nulls):
        table = lg.tabulate(df_partial_nulls, rows="region",
                            values={"revenue": "sum"}, totals=False,
                            dropna=True)
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        values = [leaf.path[0].value for leaf in data_leaves]
        assert None not in values
        # E=90, W=180; Missing row dropped
        np.testing.assert_array_equal(table.body[:, 0], [90, 180])


# === observed=False + levels= (EMPTY semantics through public API) ========


class TestObservedFalsePublic:
    def test_with_levels_unobserved_row_has_empty_cells(self, sample_df):
        # sample_df has regions East, South, West; add "North" via levels=
        table = lg.tabulate(
            sample_df, rows="region", observed=False,
            levels={"region": ["East", "South", "West", "North"]},
            values={"revenue": "sum"}, totals=True,
        )
        # North = row 3; row_count = 0 → EMPTY
        assert table.body[3, 0] == 0
        assert table.missing[3, 0] == MissingReason.EMPTY

    def test_observed_false_without_levels_raises(self, sample_df):
        with pytest.raises(ValueError, match="observed=False"):
            lg.tabulate(sample_df, rows="region",
                        values={"revenue": "sum"}, observed=False)


# === Exotic column types ==================================================


class TestExoticColumnTypes:
    def test_numeric_grouping_column(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "year": [2020, 2020, 2021, 2022, 2021],
            "revenue": [100.0, 200.0, 150.0, 175.0, 125.0],
        })
        table = lg.tabulate(df, rows="year",
                            values={"revenue": "sum"}, totals=False)
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        # Sorted numerically: 2020, 2021, 2022
        assert [leaf.path[0].value for leaf in data_leaves] == [2020, 2021, 2022]
        # Sums: 2020=300, 2021=275, 2022=175
        np.testing.assert_array_equal(table.body[:, 0], [300, 275, 175])

    def test_boolean_grouping_column(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "flag": [True, False, True, True],
            "value": [10.0, 20.0, 30.0, 40.0],
        })
        table = lg.tabulate(df, rows="flag",
                            values={"value": "sum"}, totals=False)
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        # Sorted: False, True
        assert [leaf.path[0].value for leaf in data_leaves] == [False, True]
        # False group sum=20, True group sum=10+30+40=80
        np.testing.assert_array_equal(table.body[:, 0], [20, 80])


# === Single-row DataFrame =================================================


class TestSingleRow:
    def test_single_row_works(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"region": ["West"], "revenue": [100.0]})
        table = lg.tabulate(df, rows="region",
                            values={"revenue": "sum"}, totals=True)
        # 1 region + 1 Total = 2 row leaves
        assert len(table.row_axis.leaves()) == 2
        # West: 100; Total: 100
        np.testing.assert_array_equal(table.body[:, 0], [100, 100])


# === All six stats together ===============================================


class TestAllSupportedStats:
    def test_all_six_stats_one_metric(self, sample_df):
        table = lg.tabulate(
            sample_df, rows="region",
            values={"revenue": ["sum", "mean", "count", "min", "max", "median"]},
            totals=False,
        )
        # 6 col leaves
        assert len(table.col_axis.leaves()) == 6
        # East row values:
        # East has 2 rows with revenue [90, 70]
        # sum=160, mean=80, count=2, min=70, max=90, median=80
        expected_east = [160.0, 80.0, 2.0, 70.0, 90.0, 80.0]
        np.testing.assert_array_almost_equal(table.body[0, :], expected_east)


# === Non-additive subtotal correctness through public API ==================


class TestNonAdditiveSubtotalEndToEnd:
    """Closes the loop on T4b's architectural decision: subtotals
    computed from source (not by aggregating cells) must give the
    correct answer for non-additive stats — visible at the public API."""

    def test_subtotal_mean_correct_through_public_api(self):
        pd = pytest.importorskip("pandas")
        # West: A has 2 rows (100, 200), B has 1 (50)
        # West subtotal mean from source: (100+200+50)/3 = 116.6667
        # Naive cell-mean: (mean(W/A)=150 + mean(W/B)=50) / 2 = 100 ← wrong
        df = pd.DataFrame({
            "region":  ["W", "W", "W", "E", "E"],
            "product": ["A", "A", "B", "A", "B"],
            "revenue": [100.0, 200.0, 50.0, 80.0, 60.0],
        })
        table = lg.tabulate(
            df, rows=["region", "product"],
            values={"revenue": "mean"},
            subtotals="region", totals=False,
        )
        # Subtotal leaves at positions 2 (East) and 5 (West) given
        # row order East/A, East/B, East Subtotal, West/A, West/B, West Subtotal.
        # East subtotal mean: (80+60)/2 = 70
        # West subtotal mean: (100+200+50)/3 = 116.6667
        assert table.body[2, 0] == 70.0
        assert table.body[5, 0] == pytest.approx(350.0 / 3.0)
        # Negative: confirm it's NOT the naive cell mean
        naive_west = (table.body[3, 0] + table.body[4, 0]) / 2
        assert naive_west != table.body[5, 0]


# === levels= subset filter (through public API) ===========================


class TestLevelsSubsetFilter:
    def test_levels_filters_to_listed_categories(self, sample_df):
        # sample_df regions: East, South, West. Request only East.
        table = lg.tabulate(
            sample_df, rows="region",
            levels={"region": ["East"]},
            values={"revenue": "sum"}, totals=False,
        )
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        assert len(data_leaves) == 1
        assert data_leaves[0].path[0].value == "East"
        # East revenue = 90+70 = 160
        assert table.body[0, 0] == 160.0


class TestLevelsRespectedInTotals:
    """Reviewer P1 regression: total sections collapse one or both axes
    (no key in the groupby). Without a pre-filter, source rows whose
    values were excluded by `levels=` still leak into those totals.

    Three failure modes, one fix:
    - grand_row collapses row keys → pulls in filtered rows
    - grand_col (or subtotal_total_col) collapses col keys → pulls in
      filtered cols
    - subtotal_data_cols collapses inner-row dims → pulls in filtered
      inner-row values
    """

    def test_grand_total_respects_row_levels_filter(self):
        """The reviewer's exact reproducer: with only East displayed,
        the Total row should report East's revenue, not the full sum."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": ["East", "West"],
            "revenue": [10.0, 90.0],
        })
        table = lg.tabulate(
            df, rows="region",
            levels={"region": ["East"]},
            values={"revenue": "sum"}, totals=True,
        )
        # Row leaves: East, Total
        assert table.body[0, 0] == 10.0  # East
        assert table.body[1, 0] == 10.0  # Total — was 100 before fix

    def test_total_col_respects_col_levels_filter(self):
        """Filter on col dim should propagate to the Total col, not just
        to the displayed quarter columns."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["E", "E", "E", "E"],
            "quarter": ["Q1", "Q2", "Q3", "Q4"],
            "revenue": [10.0, 20.0, 30.0, 40.0],
        })
        table = lg.tabulate(
            df, rows="region", cols="quarter",
            levels={"quarter": ["Q1"]},
            values={"revenue": "sum"}, totals=True,
        )
        # Layout: row=[E, Total], col=[Q1, Total]; shape (2, 2)
        # Without the fix, the Total col would be 100 (sum of all
        # quarters), not 10 (Q1 only).
        assert table.body[0, 0] == 10.0  # E/Q1
        assert table.body[0, 1] == 10.0  # E/Total
        assert table.body[1, 0] == 10.0  # Total/Q1
        assert table.body[1, 1] == 10.0  # Total/Total

    def test_subtotal_respects_inner_row_levels_filter(self):
        """Subtotal at the outer dim consolidates the inner dim. If
        the inner dim is filtered, the subtotal must respect that
        filter (the subtotal section's groupby doesn't include the
        inner dim, so without the pre-filter it would aggregate
        excluded inner-dim values too)."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["E", "E", "E"],
            "product": ["A", "B", "A"],
            "revenue": [10.0, 20.0, 30.0],
        })
        table = lg.tabulate(
            df, rows=["region", "product"],
            levels={"product": ["A"]},  # B is filtered out
            values={"revenue": "sum"},
            subtotals="region", totals=False,
        )
        # Row leaves: E/A, E Subtotal
        # E/A: 10+30 = 40
        # E Subtotal: 40 (NOT 60 — must not include product B's 20)
        assert table.body[0, 0] == 40.0
        assert table.body[1, 0] == 40.0

    def test_grand_cell_respects_both_filters(self):
        """Most aggressive collapse: grand_cell with no keys at all.
        Must respect both row and col level filters simultaneously."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["E", "E", "W", "W"],
            "quarter": ["Q1", "Q2", "Q1", "Q2"],
            "revenue": [10.0, 20.0, 30.0, 40.0],
        })
        table = lg.tabulate(
            df, rows="region", cols="quarter",
            levels={"region": ["E"], "quarter": ["Q1"]},
            values={"revenue": "sum"}, totals=True,
        )
        # Only E/Q1 displayed = revenue 10
        # All four positions (E/Q1, E/Total, Total/Q1, Total/Total)
        # should equal 10 — the pre-filter excludes W rows and Q2 rows.
        assert table.body[0, 0] == 10.0  # E/Q1
        assert table.body[0, 1] == 10.0  # E/Total
        assert table.body[1, 0] == 10.0  # Total/Q1
        assert table.body[1, 1] == 10.0  # Total/Total — grand_cell


# === Compound: subtotals + cols + totals end-to-end =======================


class TestCompoundCaseEndToEnd:
    """The compound case: 2 rows + 1 col + subtotals + totals — every
    section populated. Verifies the dispatch table works through public."""

    def test_all_section_values_correct(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["W", "W", "E", "E"],
            "product": ["A", "B", "A", "B"],
            "channel": ["x", "y", "x", "y"],
            "revenue": [10.0, 20.0, 30.0, 40.0],
        })
        table = lg.tabulate(
            df, rows=["region", "product"], cols="channel",
            values={"revenue": "sum"},
            subtotals="region", totals=True,
        )
        # Layout (row): E/A, E/B, E Sub, W/A, W/B, W Sub, Grand Total = 7
        # Layout (col): x, y, Total = 3
        assert table.body.shape == (7, 3)
        # E/A: x=30, y=0 (no record), Total=30
        # Wait — the data has E/A with channel=x (revenue=30). E/B has channel=y (40).
        # So E/A cell (channel=x): rev=30; (channel=y): no record → EMPTY
        # Hmm let me re-verify the data:
        # rows: (W,A,x,10), (W,B,y,20), (E,A,x,30), (E,B,y,40)
        # E/A: 1 record with channel=x, rev=30
        # E/A x=30; E/A y is EMPTY (no record)
        # E/B: 1 record with channel=y, rev=40
        # E/B x is EMPTY; E/B y=40
        # E Subtotal x=30, y=40, Total=70
        # W/A x=10, y EMPTY; W/B x EMPTY, y=20
        # W Subtotal x=10, y=20, Total=30
        # Grand Total x=40, y=60, Total=100
        # Row 2 (E Subtotal): x=30, y=40, Total=70
        np.testing.assert_array_equal(table.body[2, :], [30, 40, 70])
        # Row 5 (W Subtotal): x=10, y=20, Total=30
        np.testing.assert_array_equal(table.body[5, :], [10, 20, 30])
        # Row 6 (Grand Total): x=40, y=60, Total=100
        np.testing.assert_array_equal(table.body[6, :], [40, 60, 100])
