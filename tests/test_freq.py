"""Smoke tests for the public `freq()` entry point.

These verify that the F1–F5 pipeline composes correctly through the
public API. Comprehensive integration tests (does freq() output match
the hand-built `examples.py` fixtures?) land in F7; deep edge-case
coverage through the public API lands in F8.
"""

from __future__ import annotations

import numpy as np
import pytest

import proctab as pt
from proctab.model import Table, TotalMarker


class TestOneWayThroughPublicAPI:
    def test_returns_table(self, sample_df):
        table = pt.freq(sample_df, "region")
        assert isinstance(table, Table)

    def test_axes_validate(self, sample_df):
        table = pt.freq(sample_df, "region")
        table.row_axis.validate()
        table.col_axis.validate()

    def test_body_shape_matches_axis_leaves(self, sample_df):
        table = pt.freq(sample_df, "region")
        assert table.body.shape == (
            len(table.row_axis.leaves()),
            len(table.col_axis.leaves()),
        )

    def test_row_axis_has_one_data_dim(self, sample_df):
        table = pt.freq(sample_df, "region")
        assert len(table.row_axis.dims) == 1
        assert table.row_axis.dims[0].name == "region"

    def test_col_axis_has_stat_dim(self, sample_df):
        table = pt.freq(sample_df, "region")
        assert len(table.col_axis.dims) == 1
        assert table.col_axis.dims[0].name == "_stat"

    def test_includes_total_row_by_default(self, sample_df):
        table = pt.freq(sample_df, "region")
        leaves = table.row_axis.leaves()
        assert leaves[-1].role == "total"

    def test_totals_false_omits_total_row(self, sample_df):
        table = pt.freq(sample_df, "region", totals=False)
        leaves = table.row_axis.leaves()
        assert all(leaf.role == "data" for leaf in leaves)

    def test_renders_to_text(self, sample_df):
        # Pipeline → Table → renderer round-trip
        table = pt.freq(sample_df, "region")
        text = table.to_text()
        assert "East" in text
        assert "Total" in text


class TestTwoWayThroughPublicAPI:
    def test_returns_table(self, sample_df):
        table = pt.freq(sample_df, "region", "product")
        assert isinstance(table, Table)

    def test_axes_validate(self, sample_df):
        table = pt.freq(sample_df, "region", "product")
        table.row_axis.validate()
        table.col_axis.validate()

    def test_body_shape_matches_axis_leaves(self, sample_df):
        table = pt.freq(sample_df, "region", "product")
        assert table.body.shape == (
            len(table.row_axis.leaves()),
            len(table.col_axis.leaves()),
        )

    def test_col_axis_has_two_dims(self, sample_df):
        table = pt.freq(sample_df, "region", "product")
        assert len(table.col_axis.dims) == 2
        assert table.col_axis.dims[0].name == "product"
        assert table.col_axis.dims[1].name == "_stat"

    def test_includes_marginal_total_col(self, sample_df):
        table = pt.freq(sample_df, "region", "product")
        # Top-level col-axis children: data branches per product + Total branch
        children = table.col_axis.tree.children
        assert children[-1].role == "total"
        assert isinstance(children[-1].path[0], TotalMarker)

    def test_list_keys_form_equivalent_to_positional(self, sample_df):
        table_positional = pt.freq(sample_df, "region", "product")
        table_list = pt.freq(sample_df, ["region", "product"])
        # Same shape and the same numeric body
        assert table_positional.body.shape == table_list.body.shape
        np.testing.assert_array_equal(
            table_positional.body, table_list.body,
        )


class TestErrorsThroughPublicAPI:
    def test_missing_column_raises_keyerror(self, sample_df):
        with pytest.raises(KeyError, match="not found"):
            pt.freq(sample_df, "nonexistent")

    def test_three_keys_raises_valueerror(self, sample_df):
        with pytest.raises(ValueError, match="one- or two-way"):
            pt.freq(sample_df, "region", "product", "units")

    def test_no_keys_raises_valueerror(self, sample_df):
        with pytest.raises(ValueError, match="at least one"):
            pt.freq(sample_df)

    def test_mixed_key_forms_raise_typeerror(self, sample_df):
        with pytest.raises(TypeError, match="mixed positional and list"):
            pt.freq(sample_df, ["region"], "product")

    def test_weight_raises_notimplemented(self, sample_df):
        with pytest.raises(NotImplementedError, match="v0.2"):
            pt.freq(sample_df, "region", weight="units")

    def test_test_raises_notimplemented(self, sample_df):
        with pytest.raises(NotImplementedError, match="v0.2"):
            pt.freq(sample_df, "region", "product", test="chi2")

    def test_non_dataframe_raises_typeerror(self):
        with pytest.raises(TypeError):
            pt.freq([1, 2, 3], "region")


class TestPublicExport:
    def test_freq_importable_from_package(self):
        # Already used in tests above, but make the contract explicit
        assert pt.freq is not None
        assert callable(pt.freq)
