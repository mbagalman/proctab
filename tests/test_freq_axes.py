"""Tests for F5: build_axes() — Axis construction from PercentResult.

build_axes() calls Axis.validate() internally, so the constructions also
exercise the validator. Body-shape-matches-leaves sanity checks link F5
back to F4b.
"""

from __future__ import annotations

import numpy as np

from proctab.freq import (
    AxisBuildResult,
    CountResult,
    FreqSpec,
    build_axes,
    derive_percentages,
)
from proctab.model import (
    Axis,
    Category,
    TotalMarker,
)


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


# === one-way ================================================================


class TestOneWayRowAxis:
    def test_returns_axis_build_result(self):
        percents = derive_percentages(_counts_1d([2, 3, 2]), _spec(("region",)))
        result = build_axes(percents, _spec(("region",)))
        assert isinstance(result, AxisBuildResult)
        assert isinstance(result.row_axis, Axis)

    def test_row_dim_uses_first_key(self):
        percents = derive_percentages(_counts_1d([2, 3, 2]), _spec(("region",)))
        result = build_axes(percents, _spec(("region",)))
        assert len(result.row_axis.dims) == 1
        assert result.row_axis.dims[0].name == "region"
        assert result.row_axis.dims[0].kind == "category"

    def test_row_dim_categories_match_input(self):
        cats = (Category("West"), Category("East"))
        counts = CountResult(
            row_categories=cats, col_categories=None,
            counts=np.array([2.0, 3.0]),
        )
        percents = derive_percentages(counts, _spec(("region",)))
        result = build_axes(percents, _spec(("region",)))
        assert result.row_axis.dims[0].categories == cats

    def test_row_label_override(self):
        percents = derive_percentages(_counts_1d([2, 3]), _spec(("region",)))
        result = build_axes(
            percents, _spec(("region",), label={"region": "Sales Region"})
        )
        assert result.row_axis.dims[0].label == "Sales Region"

    def test_row_tree_has_data_leaves_per_category(self):
        percents = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=False))
        result = build_axes(percents, _spec(("region",), totals=False))
        leaves = result.row_axis.leaves()
        assert len(leaves) == 3
        assert all(leaf.role == "data" for leaf in leaves)

    def test_row_tree_includes_total_when_totals_true(self):
        percents = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=True))
        result = build_axes(percents, _spec(("region",), totals=True))
        leaves = result.row_axis.leaves()
        assert len(leaves) == 4
        assert leaves[-1].role == "total"
        assert isinstance(leaves[-1].path[-1], TotalMarker)
        assert leaves[-1].label == "Total"

    def test_row_tree_no_total_when_totals_false(self):
        percents = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("region",), totals=False))
        result = build_axes(percents, _spec(("region",), totals=False))
        leaves = result.row_axis.leaves()
        assert not any(leaf.role == "total" for leaf in leaves)


class TestOneWayColAxis:
    def test_col_axis_has_stat_dim_only(self):
        percents = derive_percentages(_counts_1d([2, 3]), _spec(("x",)))
        result = build_axes(percents, _spec(("x",)))
        assert len(result.col_axis.dims) == 1
        assert result.col_axis.dims[0].name == "_stat"
        assert result.col_axis.dims[0].kind == "stat"

    def test_col_axis_leaves_are_the_four_stats(self):
        percents = derive_percentages(_counts_1d([2, 3]), _spec(("x",)))
        result = build_axes(percents, _spec(("x",)))
        leaves = result.col_axis.leaves()
        assert [leaf.path[0].value for leaf in leaves] == ["N", "Pct", "CumN", "CumPct"]

    def test_col_axis_leaves_are_data_role(self):
        percents = derive_percentages(_counts_1d([2, 3]), _spec(("x",)))
        result = build_axes(percents, _spec(("x",)))
        assert all(leaf.role == "data" for leaf in result.col_axis.leaves())


class TestOneWayMetadata:
    def test_value_kinds_match_stats(self):
        percents = derive_percentages(_counts_1d([2, 3]), _spec(("x",)))
        result = build_axes(percents, _spec(("x",)))
        assert result.value_kinds == ("count", "percent", "count", "percent")

    def test_formats_match_stats(self):
        percents = derive_percentages(_counts_1d([2, 3]), _spec(("x",)))
        result = build_axes(percents, _spec(("x",)))
        assert result.formats == ("{:.0f}", "{:.1f}%", "{:.0f}", "{:.1f}%")


class TestOneWayBodyShapeMatchesLeaves:
    def test_with_totals(self):
        percents = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("x",), totals=True))
        result = build_axes(percents, _spec(("x",), totals=True))
        assert percents.body.shape == (
            len(result.row_axis.leaves()),
            len(result.col_axis.leaves()),
        )

    def test_without_totals(self):
        percents = derive_percentages(
            _counts_1d([2, 3, 2]), _spec(("x",), totals=False))
        result = build_axes(percents, _spec(("x",), totals=False))
        assert percents.body.shape == (
            len(result.row_axis.leaves()),
            len(result.col_axis.leaves()),
        )


# === two-way ================================================================


class TestTwoWayColAxis:
    def test_col_axis_has_two_dims(self):
        percents = derive_percentages(
            _counts_2d([[1, 1], [2, 1]]), _spec(("r", "c")))
        result = build_axes(percents, _spec(("r", "c")))
        assert len(result.col_axis.dims) == 2
        assert result.col_axis.dims[0].name == "c"
        assert result.col_axis.dims[1].name == "_stat"

    def test_col_label_override(self):
        percents = derive_percentages(
            _counts_2d([[1, 1]]), _spec(("r", "c")))
        result = build_axes(
            percents, _spec(("r", "c"), label={"c": "Channel"}),
        )
        assert result.col_axis.dims[0].label == "Channel"

    def test_col_tree_with_totals_has_total_branch(self):
        percents = derive_percentages(
            _counts_2d([[1, 1], [2, 1]]), _spec(("r", "c"), totals=True))
        result = build_axes(percents, _spec(("r", "c"), totals=True))
        # Top-level children: data branches per col cat + Total branch
        children = result.col_axis.tree.children
        assert len(children) == 3  # 2 data cats + 1 Total
        assert children[-1].role == "total"
        assert isinstance(children[-1].path[0], TotalMarker)
        assert children[-1].label == "Total"

    def test_total_branch_stat_leaves_are_total_role(self):
        percents = derive_percentages(
            _counts_2d([[1, 1]]), _spec(("r", "c"), totals=True))
        result = build_axes(percents, _spec(("r", "c"), totals=True))
        total_branch = result.col_axis.tree.children[-1]
        # All stat leaves under Total branch must be role=total
        for leaf in total_branch.children:
            assert leaf.role == "total"
            assert isinstance(leaf.path[0], TotalMarker)

    def test_data_branch_stat_leaves_are_data_role(self):
        percents = derive_percentages(
            _counts_2d([[1, 1]]), _spec(("r", "c"), totals=True))
        result = build_axes(percents, _spec(("r", "c"), totals=True))
        data_branch = result.col_axis.tree.children[0]
        for leaf in data_branch.children:
            assert leaf.role == "data"

    def test_col_tree_without_totals_has_no_total_branch(self):
        percents = derive_percentages(
            _counts_2d([[1, 1], [2, 1]]), _spec(("r", "c"), totals=False))
        result = build_axes(percents, _spec(("r", "c"), totals=False))
        children = result.col_axis.tree.children
        assert len(children) == 2
        assert all(c.role == "data" for c in children)


class TestTwoWayMetadata:
    def test_value_kinds_tiled_across_col_groups_with_totals(self):
        percents = derive_percentages(
            _counts_2d([[1, 1], [2, 1]]), _spec(("r", "c"), totals=True))
        result = build_axes(percents, _spec(("r", "c"), totals=True))
        # 4 stats per col group × (2 data cols + 1 Total col) = 12 leaves
        expected = ("count", "percent", "percent", "percent") * 3
        assert result.value_kinds == expected

    def test_value_kinds_tiled_without_totals(self):
        percents = derive_percentages(
            _counts_2d([[1, 1], [2, 1]]), _spec(("r", "c"), totals=False))
        result = build_axes(percents, _spec(("r", "c"), totals=False))
        expected = ("count", "percent", "percent", "percent") * 2
        assert result.value_kinds == expected


class TestTwoWayBodyShapeMatchesLeaves:
    def test_with_totals(self):
        percents = derive_percentages(
            _counts_2d([[1, 1], [2, 1]]), _spec(("r", "c"), totals=True))
        result = build_axes(percents, _spec(("r", "c"), totals=True))
        assert percents.body.shape == (
            len(result.row_axis.leaves()),
            len(result.col_axis.leaves()),
        )

    def test_without_totals(self):
        percents = derive_percentages(
            _counts_2d([[1, 1], [2, 1]]), _spec(("r", "c"), totals=False))
        result = build_axes(percents, _spec(("r", "c"), totals=False))
        assert percents.body.shape == (
            len(result.row_axis.leaves()),
            len(result.col_axis.leaves()),
        )


# === edge cases =============================================================


class TestEdgeCases:
    def test_empty_one_way(self):
        percents = derive_percentages(_counts_1d([]), _spec(("x",), totals=True))
        result = build_axes(percents, _spec(("x",), totals=True))
        assert result.row_axis.leaves() == []
        # 4 stat leaves still present (col_axis isn't affected by empty rows)
        assert len(result.col_axis.leaves()) == 4
        # body shape (0, 4) matches
        assert percents.body.shape == (0, 4)

    def test_empty_two_way(self):
        empty = CountResult(
            row_categories=(), col_categories=(),
            counts=np.zeros((0, 0), dtype=np.float64),
        )
        percents = derive_percentages(empty, _spec(("r", "c"), totals=True))
        result = build_axes(percents, _spec(("r", "c"), totals=True))
        assert result.row_axis.leaves() == []
        assert result.col_axis.leaves() == []

    def test_validate_passes_on_complex_two_way_axes(self):
        # If build_axes returns at all, validate() already passed -- but make
        # the call explicit here as a regression hook.
        percents = derive_percentages(
            _counts_2d([[1, 1], [2, 1], [1, 1]]),
            _spec(("region", "product"), totals=True),
        )
        result = build_axes(percents, _spec(("region", "product"), totals=True))
        result.row_axis.validate()
        result.col_axis.validate()
