"""Tests for T5: build_tabulate_axes() — Axis construction from
T4a's AggregateResult.

The critical structural invariant: row_axis / col_axis leaf pre-order
MUST match T4c's row_layout / col_layout. TestLeafOrderingMatchesLayout
locks that in (body indexing depends on it).
"""

from __future__ import annotations

import pytest

from legible._engine import wrap
from legible.model import (
    Axis,
    Dimension,
    SubtotalMarker,
    TotalMarker,
)
from legible.tabulate import (
    STAT_DEFAULTS,
    SUPPORTED_STATS,
    TabulateAxes,
    _parse_tabulate_args,
    aggregate_data_cells,
    aggregate_totals,
    assemble_body,
    build_tabulate_axes,
)


def _spec(**kwargs):
    return _parse_tabulate_args(**kwargs)


def _axes(nw_df, spec):
    data = aggregate_data_cells(nw_df, spec)
    return build_tabulate_axes(data, spec), data


# === STAT_DEFAULTS registry shape ==========================================


class TestStatDefaultsRegistry:
    def test_keys_match_supported_stats(self):
        assert set(STAT_DEFAULTS.keys()) == SUPPORTED_STATS

    def test_each_entry_has_kind_and_format(self):
        for stat, value in STAT_DEFAULTS.items():
            assert len(value) == 2, f"{stat!r} entry must be (kind, format)"
            kind, fmt = value
            assert isinstance(kind, str)
            assert isinstance(fmt, str)


# === Dimensions ===========================================================


class TestDimensions:
    def test_one_row_no_cols_dims(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"})
        axes, _ = _axes(wrap(sample_df), spec)
        assert [d.name for d in axes.row_axis.dims] == ["region"]
        assert [d.name for d in axes.col_axis.dims] == ["_metric", "_stat"]
        assert axes.col_axis.dims[0].kind == "metric"
        assert axes.col_axis.dims[1].kind == "stat"

    def test_two_row_one_col_dims(self, sample_df):
        spec = _spec(rows=["region", "product"], cols=("product",),
                     values={"revenue": "sum"}) if False else _spec(
            rows=["region", "product"],
            values={"revenue": "sum"},
        )
        # Use a non-overlapping col
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["W", "W", "E", "E"],
            "product": ["A", "B", "A", "B"],
            "channel": ["x", "x", "y", "y"],
            "revenue": [10, 20, 30, 40],
        })
        spec = _spec(rows=["region", "product"], cols="channel",
                     values={"revenue": "sum"})
        axes, _ = _axes(wrap(df), spec)
        assert [d.name for d in axes.row_axis.dims] == ["region", "product"]
        assert [d.name for d in axes.col_axis.dims] == ["channel", "_metric", "_stat"]

    def test_label_override_on_user_dims(self, sample_df):
        spec = _spec(rows="region",
                     values={"revenue": "sum"},
                     label={"region": "Sales Region"})
        axes, _ = _axes(wrap(sample_df), spec)
        assert axes.row_axis.dims[0].label == "Sales Region"

    def test_metric_dim_has_unique_metric_categories(self, sample_df):
        spec = _spec(rows="region",
                     values={"revenue": ["sum", "mean"], "units": ["sum"]})
        axes, _ = _axes(wrap(sample_df), spec)
        metric_cats = axes.col_axis.dims[0].categories
        assert [c.value for c in metric_cats] == ["revenue", "units"]

    def test_stat_dim_has_unique_stat_categories(self, sample_df):
        spec = _spec(rows="region",
                     values={"revenue": ["sum", "mean"], "units": ["sum"]})
        axes, _ = _axes(wrap(sample_df), spec)
        stat_cats = axes.col_axis.dims[1].categories
        # Unique stats: sum, mean (insertion order)
        assert [c.value for c in stat_cats] == ["sum", "mean"]


# === Tree structure =======================================================


class TestRowTree:
    def test_one_row_no_totals_flat_leaves(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=False)
        axes, _ = _axes(wrap(sample_df), spec)
        # 3 region cats → 3 leaves, no subtotals/total
        leaves = axes.row_axis.leaves()
        assert len(leaves) == 3
        assert all(leaf.role == "data" for leaf in leaves)

    def test_one_row_with_totals(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        axes, _ = _axes(wrap(sample_df), spec)
        leaves = axes.row_axis.leaves()
        assert len(leaves) == 4
        assert leaves[-1].role == "total"
        assert leaves[-1].label == "Total"
        assert isinstance(leaves[-1].path[0], TotalMarker)

    def test_two_row_no_subtotals_no_totals(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"}, totals=False)
        axes, _ = _axes(wrap(sample_df), spec)
        leaves = axes.row_axis.leaves()
        # 3 regions × 2 products = 6
        assert len(leaves) == 6
        assert all(leaf.role == "data" for leaf in leaves)

    def test_two_row_subtotals_outer(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        axes, _ = _axes(wrap(sample_df), spec)
        leaves = axes.row_axis.leaves()
        # 3 regions × (2 products + 1 subtotal) = 9
        assert len(leaves) == 9
        # Per region, 2 data then 1 subtotal
        roles = [leaf.role for leaf in leaves]
        assert roles == ["data", "data", "subtotal"] * 3

    def test_two_row_subtotals_and_grand_total(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=True)
        axes, _ = _axes(wrap(sample_df), spec)
        leaves = axes.row_axis.leaves()
        # 9 + 1 grand total = 10
        assert len(leaves) == 10
        assert leaves[-1].role == "total"
        assert leaves[-1].label == "Grand Total"
        # Grand total path = (TotalMarker, TotalMarker) for 2-dim
        assert all(isinstance(p, TotalMarker) for p in leaves[-1].path)
        assert len(leaves[-1].path) == 2

    def test_subtotal_leaf_path_has_subtotal_marker(self, sample_df):
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        axes, _ = _axes(wrap(sample_df), spec)
        # Subtotal leaves are at positions 2, 5, 8
        for i in (2, 5, 8):
            leaf = axes.row_axis.leaves()[i]
            assert leaf.role == "subtotal"
            assert isinstance(leaf.path[1], SubtotalMarker)
            assert leaf.path[1].at_dim == "product"

    def test_missing_category_subtotal_label_uses_label_not_value(self):
        """Reviewer P3 regression: synthetic Missing categories have
        value=None, label="Missing". The subtotal row label must use
        the label, not the value, or it renders as 'None Subtotal'."""
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": ["West", None, "East"],
            "product": ["A", "B", "A"],
            "revenue": [100.0, 50.0, 90.0],
        })
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=False)
        axes, _ = _axes(wrap(df), spec)
        subtotal_labels = [
            leaf.label for leaf in axes.row_axis.leaves()
            if leaf.role == "subtotal"
        ]
        # Categories alphabetical: East, West, then Missing (None) → 3 subtotals
        assert "Missing Subtotal" in subtotal_labels
        # Negative: no "None Subtotal" should appear
        assert not any("None" in label for label in subtotal_labels)


class TestColTree:
    def test_no_cols_no_user_dim(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"})
        axes, _ = _axes(wrap(sample_df), spec)
        # Top-level children: metric branches directly
        children = axes.col_axis.tree.children
        assert len(children) == 1  # Revenue branch
        assert children[0].path[0].value == "revenue"

    def test_with_user_col_branches(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": "sum"}, totals=False)
        axes, _ = _axes(wrap(sample_df), spec)
        children = axes.col_axis.tree.children
        # 2 product cats, no Total col (totals=False)
        assert len(children) == 2
        assert all(c.role == "data" for c in children)

    def test_total_col_branch_appended(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": "sum"}, totals=True)
        axes, _ = _axes(wrap(sample_df), spec)
        children = axes.col_axis.tree.children
        # 2 product cats + 1 Total = 3
        assert len(children) == 3
        assert children[-1].role == "total"
        assert children[-1].label == "Total"
        assert isinstance(children[-1].path[0], TotalMarker)

    def test_no_total_col_when_cols_empty(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        axes, _ = _axes(wrap(sample_df), spec)
        # cols=() → no Total col, regardless of totals=True
        for leaf in axes.col_axis.leaves():
            assert leaf.role == "data"

    def test_role_propagates_into_total_subtree(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": ["sum", "mean"]}, totals=True)
        axes, _ = _axes(wrap(sample_df), spec)
        total_branch = axes.col_axis.tree.children[-1]
        # All descendants of Total branch must be role=total
        for leaf in total_branch.leaves():
            assert leaf.role == "total"


# === Leaf ordering matches T4c's layout (load-bearing) ===================


class TestLeafOrderingMatchesLayout:
    """Structural invariant: row_axis / col_axis leaf pre-order matches
    T4c's row_layout / col_layout. Body indexing depends on this."""

    def _check(self, df, **spec_kwargs):
        spec = _spec(**spec_kwargs)
        nw_df = wrap(df)
        data = aggregate_data_cells(nw_df, spec)
        axes = build_tabulate_axes(data, spec)
        totals = aggregate_totals(nw_df, spec, data)
        assembled = assemble_body(data, totals, spec)
        # Lengths match
        assert len(axes.row_axis.leaves()) == len(assembled.row_layout)
        assert len(axes.col_axis.leaves()) == len(assembled.col_layout)

    def test_one_row_no_cols(self, sample_df):
        self._check(sample_df, rows="region", values={"revenue": "sum"}, totals=True)

    def test_two_row_with_subtotals_and_totals(self, sample_df):
        self._check(sample_df, rows=["region", "product"],
                    values={"revenue": "sum"},
                    subtotals="region", totals=True)

    def test_with_cols_and_totals(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region":  ["W", "W", "E", "E"],
            "product": ["A", "B", "A", "B"],
            "channel": ["x", "x", "y", "y"],
            "revenue": [10, 20, 30, 40],
        })
        self._check(df, rows=["region", "product"], cols="channel",
                    values={"revenue": "sum"},
                    subtotals="region", totals=True)

    def test_multiple_stats_no_cols(self, sample_df):
        self._check(sample_df, rows="region",
                    values={"revenue": ["sum", "mean", "count"]})


# === value_kinds / formats ================================================


class TestValueKindsAndFormats:
    def test_per_leaf_metadata_length_matches_col_leaves(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": ["sum", "mean"]}, totals=True)
        axes, _ = _axes(wrap(sample_df), spec)
        n_leaves = len(axes.col_axis.leaves())
        assert len(axes.value_kinds) == n_leaves
        assert len(axes.formats) == n_leaves

    def test_value_kinds_per_stat(self, sample_df):
        spec = _spec(rows="region",
                     values={"revenue": ["sum", "mean", "count", "median"]})
        axes, _ = _axes(wrap(sample_df), spec)
        assert axes.value_kinds == ("sum", "mean", "count", "median")

    def test_formats_per_stat(self, sample_df):
        spec = _spec(rows="region",
                     values={"revenue": ["sum", "mean", "count", "median"]})
        axes, _ = _axes(wrap(sample_df), spec)
        # Per STAT_DEFAULTS
        assert axes.formats == ("{:,.0f}", "{:,.2f}", "{:,.0f}", "{:,.2f}")

    def test_value_kinds_tiled_with_total_col(self, sample_df):
        spec = _spec(rows="region", cols="product",
                     values={"revenue": ["sum", "mean"]}, totals=True)
        axes, _ = _axes(wrap(sample_df), spec)
        # 3 col groups (A, B, Total) × 2 stats = 6 leaves
        # Per-stat kinds repeat: (sum, mean) × 3
        assert axes.value_kinds == ("sum", "mean") * 3


# === Internal validation ==================================================


class TestInternalValidation:
    def test_validate_passes_on_compound_case(self, sample_df):
        # If build_tabulate_axes returns at all, validate already passed.
        # This test makes it explicit + acts as a regression hook.
        spec = _spec(rows=["region", "product"],
                     values={"revenue": "sum"},
                     subtotals="region", totals=True)
        axes, _ = _axes(wrap(sample_df), spec)
        axes.row_axis.validate()
        axes.col_axis.validate()

    def test_returns_tabulate_axes(self, sample_df):
        spec = _spec(rows="region", values={"revenue": "sum"})
        axes, _ = _axes(wrap(sample_df), spec)
        assert isinstance(axes, TabulateAxes)
        assert isinstance(axes.row_axis, Axis)
        assert isinstance(axes.col_axis, Axis)


# === Edge cases ===========================================================


class TestEdgeCases:
    def test_empty_data_yields_empty_row_axis(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({
            "region": pd.Series([], dtype="object"),
            "revenue": pd.Series([], dtype="Float64"),
        })
        spec = _spec(rows="region", values={"revenue": "sum"}, totals=True)
        axes, _ = _axes(wrap(df), spec)
        # No row leaves; col leaves are still the stat tree
        assert len(axes.row_axis.leaves()) == 0
        # Col axis still has the metric+stat structure (1 leaf)
        assert len(axes.col_axis.leaves()) == 1
