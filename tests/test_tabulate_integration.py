"""T7 — Integration tests: does lg.tabulate() reproduce the v0.1-clean
reference fixture from examples.py?

The fixture `example_2_tabulate_v01` computes every body cell directly
in numpy (no lg.tabulate involvement), so this is an end-to-end check
that the implementation agrees with an independent reference.

Both pandas and polars input.
"""

from __future__ import annotations

import numpy as np
import pytest

import legible as lg
from legible.examples import (
    example_2_tabulate_v01,
    example_2_tabulate_v01_source,
)
from legible.model import Table


def _leaf_paths(table: Table, axis: str) -> list[tuple]:
    target = table.row_axis if axis == "row" else table.col_axis
    return [leaf.path for leaf in target.leaves()]


def _categories(table: Table, axis: str, dim_idx: int) -> list:
    target = table.row_axis if axis == "row" else table.col_axis
    return list(target.dims[dim_idx].categories)


def _leaf_roles(table: Table, axis: str) -> list[str]:
    target = table.row_axis if axis == "row" else table.col_axis
    return [leaf.role for leaf in target.leaves()]


class TestExample2TabulateV01:
    """example_2_tabulate_v01: 2 regions × 2 products × 2 quarters,
    revenue + margin metrics, subtotals at region, totals=True.

    Reference Table comes from independent numpy aggregation; tests
    assert lg.tabulate produces the same Table structure and values."""

    @pytest.fixture(params=["pandas", "polars"])
    def df(self, request):
        src = example_2_tabulate_v01_source()
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame(src)
        pl = pytest.importorskip("polars")
        return pl.DataFrame(src)

    @pytest.fixture
    def result(self, df):
        return lg.tabulate(
            df,
            rows=["region", "product"],
            cols="quarter",
            values={"revenue": ["sum", "mean"], "margin": "mean"},
            subtotals="region",
            totals=True,
        )

    @pytest.fixture
    def reference(self):
        return example_2_tabulate_v01()

    # === Dimensions ====================================================

    def test_row_dim_names_match(self, result, reference):
        assert [d.name for d in result.row_axis.dims] == \
            [d.name for d in reference.row_axis.dims]

    def test_col_dim_names_match(self, result, reference):
        assert [d.name for d in result.col_axis.dims] == \
            [d.name for d in reference.col_axis.dims]

    def test_dim_kinds_match(self, result, reference):
        assert [d.kind for d in result.row_axis.dims] == \
            [d.kind for d in reference.row_axis.dims]
        assert [d.kind for d in result.col_axis.dims] == \
            [d.kind for d in reference.col_axis.dims]

    def test_row_dim_categories_match(self, result, reference):
        for d_idx in range(len(reference.row_axis.dims)):
            assert _categories(result, "row", d_idx) == \
                _categories(reference, "row", d_idx)

    def test_col_dim_categories_match(self, result, reference):
        for d_idx in range(len(reference.col_axis.dims)):
            assert _categories(result, "col", d_idx) == \
                _categories(reference, "col", d_idx)

    # === Leaf structure =================================================

    def test_row_leaf_paths_match(self, result, reference):
        assert _leaf_paths(result, "row") == _leaf_paths(reference, "row")

    def test_col_leaf_paths_match(self, result, reference):
        assert _leaf_paths(result, "col") == _leaf_paths(reference, "col")

    def test_row_leaf_roles_match(self, result, reference):
        assert _leaf_roles(result, "row") == _leaf_roles(reference, "row")

    def test_col_leaf_roles_match(self, result, reference):
        assert _leaf_roles(result, "col") == _leaf_roles(reference, "col")

    # === Body ==========================================================

    def test_body_shape_matches(self, result, reference):
        assert result.body.shape == reference.body.shape  # (7, 9)

    def test_body_values_match(self, result, reference):
        np.testing.assert_array_almost_equal(result.body, reference.body)

    def test_missing_matches(self, result, reference):
        np.testing.assert_array_equal(result.missing, reference.missing)

    # === Per-col-leaf metadata =========================================

    def test_value_kinds_match(self, result, reference):
        assert result.value_kinds == reference.value_kinds

    def test_formats_match(self, result, reference):
        assert result.formats == reference.formats

    # === Both axes validate (regression hook) ===========================

    def test_result_axes_validate(self, result):
        result.row_axis.validate()
        result.col_axis.validate()


class TestExample2V01ReferenceItself:
    """Sanity: the reference fixture itself validates and has expected
    shape. If this fails, the integration tests can't be trusted."""

    def test_reference_validates(self):
        table = example_2_tabulate_v01()
        table.row_axis.validate()
        table.col_axis.validate()

    def test_reference_shape(self):
        table = example_2_tabulate_v01()
        assert table.body.shape == (7, 9)

    def test_reference_has_expected_row_count(self):
        table = example_2_tabulate_v01()
        # 4 data leaves + 2 subtotal + 1 grand total
        assert len(table.row_axis.leaves()) == 7

    def test_reference_has_expected_col_count(self):
        table = example_2_tabulate_v01()
        # 2 quarters × 3 stat leaves + 1 Total × 3 = 9
        assert len(table.col_axis.leaves()) == 9

    def test_source_has_eight_rows(self):
        src = example_2_tabulate_v01_source()
        for k in ("region", "product", "quarter", "revenue", "margin"):
            assert len(src[k]) == 8
