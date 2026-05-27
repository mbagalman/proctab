"""Tests for `Table.to_pandas()` / `Table.to_polars()` long-format export.

Schema source: docs/TABLE_MODEL.md#dataframe-export.

Both engines build the same columnar dict via `_export._build_long_format_columns`,
so per-cell content tests run primarily on the pandas path; the polars
path is verified for parity (shape, column names, dtype-tolerant values).
"""

from __future__ import annotations

import numpy as np
import pytest

from proctab.examples import (
    example_1_one_way_freq,
    example_1b_two_way_freq,
    example_2_tabulate_v01,
)
from proctab.model import (
    Axis,
    Category,
    Dimension,
    MissingReason,
    Node,
    SubtotalMarker,
    Table,
    TotalMarker,
)
from proctab._export import _build_long_format_columns


# ---------------------------------------------------------------------------
# Schema (column names and order) — engine-independent.
# ---------------------------------------------------------------------------


class TestSchema:
    def test_expected_columns_in_order_for_one_way_freq(self):
        cols = _build_long_format_columns(example_1_one_way_freq())
        assert list(cols.keys()) == [
            "region", "_stat",
            "_value", "_missing_reason",
            "_row_role", "_col_role",
            "_row_leaf_id", "_col_leaf_id",
        ]

    def test_expected_columns_for_two_way_freq(self):
        cols = _build_long_format_columns(example_1b_two_way_freq())
        # row dim (region) + col dims (product_line, _stat) + 6 fixed
        assert list(cols.keys()) == [
            "region", "product_line", "_stat",
            "_value", "_missing_reason",
            "_row_role", "_col_role",
            "_row_leaf_id", "_col_leaf_id",
        ]

    def test_expected_columns_for_tabulate(self):
        cols = _build_long_format_columns(example_2_tabulate_v01())
        # row dims (region, product) + col dims (quarter, _metric, _stat) + 6
        assert list(cols.keys()) == [
            "region", "product", "quarter", "_metric", "_stat",
            "_value", "_missing_reason",
            "_row_role", "_col_role",
            "_row_leaf_id", "_col_leaf_id",
        ]


class TestRowCount:
    def test_one_row_per_cell(self):
        table = example_2_tabulate_v01()
        n_cells = len(table.row_axis.leaves()) * len(table.col_axis.leaves())
        cols = _build_long_format_columns(table)
        for name, values in cols.items():
            assert len(values) == n_cells, f"column {name!r} has {len(values)} rows"


# ---------------------------------------------------------------------------
# Per-cell content.
# ---------------------------------------------------------------------------


class TestRowMajorOrder:
    def test_leaf_ids_iterate_row_major(self):
        # For an R×C table, expect (_row_leaf_id, _col_leaf_id) to enumerate
        # (0,0), (0,1), ..., (0,C-1), (1,0), ...
        table = example_1_one_way_freq()
        n_rows = len(table.row_axis.leaves())
        n_cols = len(table.col_axis.leaves())
        cols = _build_long_format_columns(table)
        expected = [
            (i, j) for i in range(n_rows) for j in range(n_cols)
        ]
        actual = list(
            zip(cols["_row_leaf_id"], cols["_col_leaf_id"])
        )
        assert actual == expected


class TestDimColumnsCarryCategoryValues:
    def test_data_row_carries_region_value(self):
        cols = _build_long_format_columns(example_1_one_way_freq())
        # First 4 rows (4 stats for West) all have region=="West"
        assert all(r == "West" for r in cols["region"][:4])

    def test_total_row_has_null_in_row_dim(self):
        cols = _build_long_format_columns(example_1_one_way_freq())
        # Last 4 rows are the Total row × 4 stats; region must be None
        assert all(r is None for r in cols["region"][-4:])

    def test_total_row_has_total_role(self):
        cols = _build_long_format_columns(example_1_one_way_freq())
        assert all(r == "total" for r in cols["_row_role"][-4:])


class TestSubtotalAndTotalDistinction:
    """Marker positions are null in dim columns; role columns disambiguate."""

    def test_subtotal_row_dim_null_and_role_is_subtotal(self):
        table = example_2_tabulate_v01()
        cols = _build_long_format_columns(table)
        # Find the rows where _row_role == "subtotal"
        sub_indices = [
            i for i, r in enumerate(cols["_row_role"]) if r == "subtotal"
        ]
        assert sub_indices
        for i in sub_indices:
            # region is the outer dim; product is the inner dim being subtotaled
            # The subtotal collapses product, so product should be None,
            # while region carries the outer category.
            assert cols["product"][i] is None
            assert cols["region"][i] is not None

    def test_grand_total_row_both_dims_null(self):
        table = example_2_tabulate_v01()
        cols = _build_long_format_columns(table)
        grand_indices = [
            i for i, r in enumerate(cols["_row_role"]) if r == "total"
        ]
        assert grand_indices
        for i in grand_indices:
            assert cols["region"][i] is None
            assert cols["product"][i] is None


class TestValueAndMissingReason:
    """PRESENT cells emit the body value + None reason; missing cells null."""

    def _present_table_with_missing(self) -> Table:
        # 1-row × 4-col Table, one cell per MissingReason variant + 1 PRESENT.
        row_dim = Dimension(
            name="region", kind="category", categories=(Category("W"),)
        )
        col_cats = tuple(Category(c) for c in ("ok", "e", "na", "supp"))
        col_dim = Dimension(name="c", kind="category", categories=col_cats)
        row_leaf = Node(path=(Category("W"),), depth=1, span=1, role="data")
        row_tree = Node(path=(), depth=0, span=1, role="data", children=(row_leaf,))
        col_leaves = tuple(
            Node(path=(c,), depth=1, span=1, role="data") for c in col_cats
        )
        col_tree = Node(path=(), depth=0, span=4, role="data", children=col_leaves)
        return Table(
            row_axis=Axis(dims=(row_dim,), tree=row_tree),
            col_axis=Axis(dims=(col_dim,), tree=col_tree),
            body=np.array([[42.0, 0.0, 0.0, 0.0]], dtype=np.float64),
            missing=np.array(
                [[
                    int(MissingReason.PRESENT),
                    int(MissingReason.EMPTY),
                    int(MissingReason.NOT_APPLICABLE),
                    int(MissingReason.SUPPRESSED),
                ]],
                dtype=np.uint8,
            ),
            value_kinds=("raw",) * 4,
            formats=(None,) * 4,
        )

    def test_present_cell_emits_value_and_null_reason(self):
        cols = _build_long_format_columns(self._present_table_with_missing())
        assert cols["_value"][0] == 42.0
        assert cols["_missing_reason"][0] is None

    def test_empty_cell_emits_null_value_and_empty_reason(self):
        cols = _build_long_format_columns(self._present_table_with_missing())
        assert cols["_value"][1] is None
        assert cols["_missing_reason"][1] == "empty"

    def test_not_applicable_reason_uses_underscored_spelling(self):
        cols = _build_long_format_columns(self._present_table_with_missing())
        assert cols["_missing_reason"][2] == "not_applicable"

    def test_suppressed_reason(self):
        cols = _build_long_format_columns(self._present_table_with_missing())
        assert cols["_missing_reason"][3] == "suppressed"

    def test_null_reason(self):
        # The fixture's missing array doesn't cover NULL; build a variant
        # by reusing its axes with an all-NULL missing array.
        base = self._present_table_with_missing()
        table = Table(
            row_axis=base.row_axis,
            col_axis=base.col_axis,
            body=base.body,
            missing=np.array(
                [[int(MissingReason.NULL)] * 4], dtype=np.uint8
            ),
            value_kinds=base.value_kinds,
            formats=base.formats,
        )
        cols = _build_long_format_columns(table)
        for r in cols["_missing_reason"]:
            assert r == "null"


class TestLeafIds:
    def test_leaf_ids_are_zero_based_dense(self):
        table = example_1b_two_way_freq()
        cols = _build_long_format_columns(table)
        n_rows = len(table.row_axis.leaves())
        n_cols = len(table.col_axis.leaves())
        assert set(cols["_row_leaf_id"]) == set(range(n_rows))
        assert set(cols["_col_leaf_id"]) == set(range(n_cols))


# ---------------------------------------------------------------------------
# Reserved-column collision guard.
# ---------------------------------------------------------------------------


def _table_with_row_dim_named(name: str) -> Table:
    """Tiny 1-row × 1-col Table whose row dim has the given name."""
    row_dim = Dimension(name=name, kind="category", categories=(Category("x"),))
    col_dim = Dimension(name="c", kind="category", categories=(Category("a"),))
    row_leaf = Node(path=(Category("x"),), depth=1, span=1, role="data")
    row_tree = Node(path=(), depth=0, span=1, role="data", children=(row_leaf,))
    col_leaf = Node(path=(Category("a"),), depth=1, span=1, role="data")
    col_tree = Node(path=(), depth=0, span=1, role="data", children=(col_leaf,))
    return Table(
        row_axis=Axis(dims=(row_dim,), tree=row_tree),
        col_axis=Axis(dims=(col_dim,), tree=col_tree),
        body=np.array([[1.0]], dtype=np.float64),
        missing=np.array([[int(MissingReason.PRESENT)]], dtype=np.uint8),
        value_kinds=("raw",),
        formats=(None,),
    )


class TestReservedColumnCollision:
    """A dim whose name collides with a reserved column raises ValueError.

    Reserved names are the fixed underscore-prefixed export columns:
    `_value`, `_missing_reason`, `_row_role`, `_col_role`,
    `_row_leaf_id`, `_col_leaf_id`.
    """

    @pytest.mark.parametrize(
        "reserved",
        [
            "_value",
            "_missing_reason",
            "_row_role",
            "_col_role",
            "_row_leaf_id",
            "_col_leaf_id",
        ],
    )
    def test_row_dim_with_reserved_name_raises(self, reserved):
        table = _table_with_row_dim_named(reserved)
        with pytest.raises(ValueError, match="reserved"):
            _build_long_format_columns(table)

    def test_error_lists_offending_name(self):
        table = _table_with_row_dim_named("_value")
        with pytest.raises(ValueError, match=r"\['_value'\]"):
            _build_long_format_columns(table)

    def test_error_suggests_rename(self):
        table = _table_with_row_dim_named("_value")
        with pytest.raises(ValueError, match="Rename"):
            _build_long_format_columns(table)

    def test_to_pandas_surfaces_the_error(self):
        pytest.importorskip("pandas")
        table = _table_with_row_dim_named("_value")
        with pytest.raises(ValueError, match="reserved"):
            table.to_pandas()


class TestReservedNamesDontCollideWithCommonUserColumns:
    """The leading-underscore convention means common user column names
    like `value`, `missing_reason`, `id` etc. can be used freely."""

    def test_dim_named_value_does_not_collide(self):
        # Reviewer's P1 regression case: a user column literally
        # named "value" used to crash because it shared a list with
        # the fixed `value` column. After the rename to `_value`, the
        # user dim is safe.
        pytest.importorskip("pandas")
        table = _table_with_row_dim_named("value")
        df = table.to_pandas()
        # Two distinct columns coexist: user dim "value" + fixed "_value".
        assert "value" in df.columns
        assert "_value" in df.columns
        # And the export ran to completion (the crash was at
        # DataFrame construction with unequal-length columns).
        assert len(df) == 1

    @pytest.mark.parametrize(
        "name",
        ["value", "missing_reason", "row_role", "col_role", "id", "data"],
    )
    def test_common_user_dim_names_are_safe(self, name):
        # None of these (no leading underscore) should trip the guard.
        table = _table_with_row_dim_named(name)
        cols = _build_long_format_columns(table)
        assert name in cols
        assert "_value" in cols


# ---------------------------------------------------------------------------
# Engine integration — Table.to_pandas() / Table.to_polars().
# ---------------------------------------------------------------------------


class TestToPandas:
    """`Table.to_pandas()` returns a long-format pandas.DataFrame."""

    def test_returns_pandas_dataframe(self):
        pd = pytest.importorskip("pandas")
        df = example_1_one_way_freq().to_pandas()
        assert isinstance(df, pd.DataFrame)

    def test_row_count_matches_cells(self):
        pytest.importorskip("pandas")
        table = example_2_tabulate_v01()
        n_cells = len(table.row_axis.leaves()) * len(table.col_axis.leaves())
        assert len(table.to_pandas()) == n_cells

    def test_columns_match_schema(self):
        pytest.importorskip("pandas")
        df = example_1b_two_way_freq().to_pandas()
        assert list(df.columns) == [
            "region", "product_line", "_stat",
            "_value", "_missing_reason",
            "_row_role", "_col_role",
            "_row_leaf_id", "_col_leaf_id",
        ]

    def test_total_row_value_present(self):
        pytest.importorskip("pandas")
        df = example_1_one_way_freq().to_pandas()
        total = df[df["_row_role"] == "total"]
        # Total row × 4 stat columns = 4 rows; all have numeric value.
        assert len(total) == 4
        for v in total["_value"]:
            assert v == v  # not NaN (would be NaN if missing was emitted as None)

    def test_subtotal_in_dim_column_is_null(self):
        pd = pytest.importorskip("pandas")
        df = example_2_tabulate_v01().to_pandas()
        sub = df[df["_row_role"] == "subtotal"]
        # In the subtotal rows, product (inner row dim) is null.
        assert sub["product"].isna().all()
        # And region (outer dim) is NOT null.
        assert sub["region"].notna().all()


class TestToPolars:
    """`Table.to_polars()` returns a long-format polars.DataFrame."""

    def test_returns_polars_dataframe(self):
        pl = pytest.importorskip("polars")
        df = example_1_one_way_freq().to_polars()
        assert isinstance(df, pl.DataFrame)

    def test_shape_matches_pandas_path(self):
        pd = pytest.importorskip("pandas")
        pl = pytest.importorskip("polars")
        table = example_2_tabulate_v01()
        df_pd = table.to_pandas()
        df_pl = table.to_polars()
        assert (df_pl.height, df_pl.width) == df_pd.shape

    def test_columns_match_pandas_path(self):
        pytest.importorskip("pandas")
        pytest.importorskip("polars")
        table = example_2_tabulate_v01()
        assert table.to_polars().columns == list(table.to_pandas().columns)

    def test_value_column_matches_pandas(self):
        pd = pytest.importorskip("pandas")
        pl = pytest.importorskip("polars")
        table = example_1_one_way_freq()
        df_pd = table.to_pandas()
        df_pl = table.to_polars()
        # PRESENT cells should have the same float value in both engines.
        pd_values = df_pd["_value"].to_list()
        pl_values = df_pl["_value"].to_list()
        for a, b in zip(pd_values, pl_values):
            if a is None or a != a:  # NaN
                assert b is None or (b != b)
            else:
                assert a == b
