"""F8 — Edge-case integration tests through the public pt.freq() API.

Belt-and-braces coverage. Some scenarios are tested at lower layers
(F2 parser, F4a aggregation, F3 engine adapter); F8 verifies they
behave correctly all the way through the full pipeline and that
the resulting Table validates and renders.

Out of scope here — already covered exhaustively at the engine layer:
LazyFrame / Series rejection (test_engine.py); freq() inherits those
checks via wrap() automatically.
"""

from __future__ import annotations

import numpy as np
import pytest

import proctab as pt
from proctab.model import MissingReason


# === Empty DataFrame =======================================================


class TestEmptyDataFrame:
    @pytest.fixture(params=["pandas", "polars"])
    def empty_df(self, request):
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame({"region": pd.Series([], dtype="object")})
        pl = pytest.importorskip("polars")
        return pl.DataFrame(schema={"region": pl.String})

    def test_one_way_empty_yields_zero_row_leaves(self, empty_df):
        table = pt.freq(empty_df, "region")
        assert len(table.row_axis.leaves()) == 0

    def test_one_way_empty_keeps_stat_leaves(self, empty_df):
        # Col axis has the stat dim regardless of row data.
        table = pt.freq(empty_df, "region")
        assert len(table.col_axis.leaves()) == 4

    def test_one_way_empty_body_shape(self, empty_df):
        table = pt.freq(empty_df, "region")
        assert table.body.shape == (0, 4)

    def test_one_way_empty_axes_validate(self, empty_df):
        table = pt.freq(empty_df, "region")
        table.row_axis.validate()
        table.col_axis.validate()

    def test_one_way_empty_renders_to_text(self, empty_df):
        # No body rows, but headers still emit. Should not raise.
        text = pt.freq(empty_df, "region").to_text()
        assert "N" in text


# === Null handling end-to-end ==============================================


class TestNullHandlingPublic:
    @pytest.fixture(params=["pandas", "polars"])
    def df_partial_nulls(self, request):
        data = {"region": ["West", "West", None, "East"]}
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame(data)
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    def test_dropna_false_appends_missing(self, df_partial_nulls):
        table = pt.freq(df_partial_nulls, "region")
        leaves = table.row_axis.leaves()
        # Alphabetical East, West, then Missing, then Total
        data_leaves = [leaf for leaf in leaves if leaf.role == "data"]
        assert [leaf.path[0].value for leaf in data_leaves] == ["East", "West", None]
        # Last data leaf is the synthetic Missing
        assert data_leaves[-1].path[0].label == "Missing"
        # N values: East=1, West=2, Missing=1, Total=4
        np.testing.assert_array_equal(table.body[:, 0], [1, 2, 1, 4])

    def test_dropna_true_drops_nulls(self, df_partial_nulls):
        table = pt.freq(df_partial_nulls, "region", dropna=True)
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        values = [leaf.path[0].value for leaf in data_leaves]
        assert None not in values
        # 3 records remain: East=1, West=2, Total=3
        np.testing.assert_array_equal(table.body[:, 0], [1, 2, 3])

    @pytest.fixture(params=["pandas", "polars"])
    def df_all_null(self, request):
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame({"region": pd.Series([None, None, None], dtype="object")})
        pl = pytest.importorskip("polars")
        return pl.DataFrame({"region": pl.Series([None, None, None], dtype=pl.String)})

    def test_all_null_dropna_false_yields_missing_only(self, df_all_null):
        table = pt.freq(df_all_null, "region")
        # Only the Missing category + Total
        leaves = table.row_axis.leaves()
        assert len(leaves) == 2
        # All 3 records counted under Missing
        np.testing.assert_array_equal(table.body[:, 0], [3, 3])

    def test_all_null_dropna_true_yields_empty(self, df_all_null):
        table = pt.freq(df_all_null, "region", dropna=True)
        assert len(table.row_axis.leaves()) == 0
        assert table.body.shape == (0, 4)


# === observed=False through the public API =================================


class TestObservedFalsePublic:
    def test_with_levels_includes_unobserved_categories(self, sample_df):
        # sample_df has region={East, South, West}; add "North" via levels=
        table = pt.freq(
            sample_df, "region", observed=False,
            levels={"region": ["West", "East", "South", "North"]},
        )
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        assert [leaf.path[0].value for leaf in data_leaves] == \
            ["West", "East", "South", "North"]

    def test_unobserved_row_has_empty_n_and_pct_cells(self, sample_df):
        table = pt.freq(
            sample_df, "region", observed=False,
            levels={"region": ["West", "East", "South", "North"]},
        )
        # North is row 3. N (col 0) = 0 → EMPTY; Pct (col 1) numer=0 → EMPTY
        assert table.body[3, 0] == 0
        assert table.missing[3, 0] == MissingReason.EMPTY
        assert table.missing[3, 1] == MissingReason.EMPTY

    def test_observed_false_without_levels_raises(self, sample_df):
        with pytest.raises(ValueError, match="observed=False"):
            pt.freq(sample_df, "region", observed=False)


# === levels= behavior ======================================================


class TestLevelsBehaviorPublic:
    def test_subset_filters_to_listed_categories(self, sample_df):
        table = pt.freq(sample_df, "region", levels={"region": ["East"]})
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        assert len(data_leaves) == 1
        assert data_leaves[0].path[0].value == "East"
        # sample_df has 2 East rows
        assert table.body[0, 0] == 2

    def test_extra_unobserved_category_yields_zero_count(self, sample_df):
        table = pt.freq(
            sample_df, "region",
            levels={"region": ["West", "East", "Mars"]},
        )
        # Mars row: count=0, EMPTY
        assert table.body[2, 0] == 0
        assert table.missing[2, 0] == MissingReason.EMPTY

    def test_levels_preserves_user_order(self, sample_df):
        table = pt.freq(
            sample_df, "region",
            levels={"region": ["South", "West", "East"]},
        )
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        # User order preserved (not alphabetical)
        assert [leaf.path[0].value for leaf in data_leaves] == \
            ["South", "West", "East"]


# === Exotic column types ===================================================


class TestExoticColumnTypes:
    def test_numeric_grouping_column(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"year": [2020, 2020, 2021, 2022, 2021]})
        table = pt.freq(df, "year")
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        assert [leaf.path[0].value for leaf in data_leaves] == [2020, 2021, 2022]
        # Counts: 2020=2, 2021=2, 2022=1, Total=5
        np.testing.assert_array_equal(table.body[:, 0], [2, 2, 1, 5])

    def test_boolean_grouping_column(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"flag": [True, False, True, True]})
        table = pt.freq(df, "flag")
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        # Sorted: False (0), True (1)
        assert [leaf.path[0].value for leaf in data_leaves] == [False, True]
        np.testing.assert_array_equal(table.body[:, 0], [1, 3, 4])


# === Single-row + extra-column edge cases =================================


class TestMinimalAndIgnoredColumns:
    def test_single_row_dataframe_works(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"region": ["West"]})
        table = pt.freq(df, "region")
        data_leaves = [leaf for leaf in table.row_axis.leaves()
                       if leaf.role == "data"]
        assert len(data_leaves) == 1
        assert table.body[0, 0] == 1  # N
        assert table.body[0, 1] == 100.0  # Pct
        # Total row
        assert table.body[1, 0] == 1
        assert table.body[1, 1] == 100.0

    def test_extra_columns_ignored(self, sample_df):
        # sample_df has region, product, revenue, units. freq(df, "region")
        # must produce the same counts as if only region existed.
        table = pt.freq(sample_df, "region")
        # 3 data categories + Total
        assert len(table.row_axis.leaves()) == 4
        # Counts: East=2, South=3, West=2, Total=7
        np.testing.assert_array_equal(table.body[:, 0], [2, 3, 2, 7])


# === Two-way edges =========================================================


class TestTwoWayEdges:
    def test_two_way_one_dim_has_single_value(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": ["W", "W", "E", "E"],
            "product": ["A", "A", "A", "A"],  # only one value
        })
        table = pt.freq(df, "region", "product")
        # 1 product cat + Total col = 2 col groups × 4 stats = 8 col leaves
        # 2 regions + Total row = 3 row leaves
        assert table.body.shape == (3, 8)
        # Validates
        table.row_axis.validate()
        table.col_axis.validate()

    def test_two_way_with_dropna_drops_null_rows(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": ["W", "W", None, "E"],
            "product": ["A", "B", "A", "B"],
        })
        # dropna=True drops the null-region row; 3 records remain
        table = pt.freq(df, "region", "product", dropna=True)
        data_row_leaves = [leaf for leaf in table.row_axis.leaves()
                           if leaf.role == "data"]
        cats = [leaf.path[0].value for leaf in data_row_leaves]
        assert None not in cats
        assert set(cats) == {"E", "W"}

    def test_two_way_empty_yields_empty_axes(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": pd.Series([], dtype="object"),
            "product": pd.Series([], dtype="object"),
        })
        table = pt.freq(df, "region", "product")
        assert len(table.row_axis.leaves()) == 0
        assert len(table.col_axis.leaves()) == 0
        assert table.body.shape == (0, 0)


# === CR-02 regression: null-like values in levels= =========================


class TestNullInLevels:
    """CR-02: when a user puts `np.nan` or `pd.NA` in `levels=`, it
    should collapse to the same Missing bucket as actual nulls in the
    data. Without normalization, the resulting `Category(np.nan)` never
    matches null rows (which the engine surfaces as `None`), so the
    "Missing" slot ends up with a 0/EMPTY count even though the data
    has nulls.
    """

    @pytest.fixture
    def df_with_nulls(self):
        pd = pytest.importorskip("pandas")
        return pd.DataFrame({
            "region": ["W", "E", None, "W", None, "E", None],
        })

    def test_np_nan_in_levels_routes_null_rows(self, df_with_nulls):
        # 3 None values in the data — np.nan in levels should grab them.
        table = pt.freq(
            df_with_nulls, "region",
            observed=False, levels={"region": [np.nan, "W", "E"]},
        )
        df = table.to_pandas()
        null_n = df[
            df["region"].isna()
            & (df["_stat"] == "N")
            & (df["_row_role"] == "data")
        ]["_value"]
        assert list(null_n) == [3.0]

    def test_pd_na_in_levels_routes_null_rows(self, df_with_nulls):
        pd = pytest.importorskip("pandas")
        # pd.NA is a separate sentinel from np.nan; both should normalize.
        table = pt.freq(
            df_with_nulls, "region",
            observed=False, levels={"region": [pd.NA, "W", "E"]},
        )
        df = table.to_pandas()
        null_n = df[
            df["region"].isna()
            & (df["_stat"] == "N")
            & (df["_row_role"] == "data")
        ]["_value"]
        assert list(null_n) == [3.0]

    def test_none_in_levels_still_works(self, df_with_nulls):
        # Pre-existing behavior — explicit `None` in levels has always
        # routed nulls correctly; check it still does after the
        # normalization change.
        table = pt.freq(
            df_with_nulls, "region",
            observed=False, levels={"region": [None, "W", "E"]},
        )
        df = table.to_pandas()
        null_n = df[
            df["region"].isna()
            & (df["_stat"] == "N")
            & (df["_row_role"] == "data")
        ]["_value"]
        assert list(null_n) == [3.0]

    def test_no_extra_missing_appended_when_user_supplies_nan(
        self, df_with_nulls,
    ):
        # If the user includes a null-like value in levels=, the
        # auto-append of `Category(None, label="Missing")` MUST NOT
        # also fire — otherwise we'd get TWO null rows.
        table = pt.freq(
            df_with_nulls, "region",
            observed=False, levels={"region": [np.nan, "W", "E"]},
        )
        # Exactly 3 row leaves (np.nan, W, E) + 1 total — no duplicate
        # null bucket.
        n_leaves = len(table.row_axis.leaves())
        assert n_leaves == 4  # 3 categories + Total
