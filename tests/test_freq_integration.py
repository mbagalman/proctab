"""F7 — Integration tests: does pt.freq() reproduce the hand-built
example fixtures from src/proctab/examples.py?

For each freq-shaped example, build a DataFrame whose freq() output
should structurally match the reference Table. `levels=` is used to
match the example's category order (freq() defaults to alphabetical;
the examples chose a different order at construction time).

Both engines (pandas, polars) run via the parametrized `df` fixtures.
"""

from __future__ import annotations

import numpy as np
import pytest

import proctab as pt
from proctab.examples import (
    example_1_one_way_freq,
    example_1b_two_way_freq,
)
from proctab.model import Table


def _leaf_paths(table: Table, axis: str) -> list[tuple]:
    """Extract the path tuple from each leaf on the given axis."""
    target = table.row_axis if axis == "row" else table.col_axis
    return [leaf.path for leaf in target.leaves()]


def _categories(table: Table, axis: str, dim_idx: int) -> list:
    """Extract the category list of a specific dim on the given axis."""
    target = table.row_axis if axis == "row" else table.col_axis
    return list(target.dims[dim_idx].categories)


# === Example 1 — one-way freq ==============================================


class TestExample1OneWay:
    """example_1_one_way_freq:
    region={West=45, East=52, South=28, North=25} → 150 records.
    Stats: N, Pct, CumN, CumPct. Total row included.
    """

    COUNTS = [("West", 45), ("East", 52), ("South", 28), ("North", 25)]

    @pytest.fixture(params=["pandas", "polars"])
    def df(self, request):
        rows = [region for region, n in self.COUNTS for _ in range(n)]
        data = {"region": rows}
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame(data)
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    @pytest.fixture
    def result(self, df):
        # levels= preserves example_1's category order (West, East, South,
        # North) — freq() defaults to alphabetical sort.
        return pt.freq(
            df, "region",
            levels={"region": ["West", "East", "South", "North"]},
        )

    @pytest.fixture
    def reference(self):
        return example_1_one_way_freq()

    def test_dim_names_match(self, result, reference):
        assert [d.name for d in result.row_axis.dims] == \
            [d.name for d in reference.row_axis.dims]
        assert [d.name for d in result.col_axis.dims] == \
            [d.name for d in reference.col_axis.dims]

    def test_dim_kinds_match(self, result, reference):
        assert [d.kind for d in result.row_axis.dims] == \
            [d.kind for d in reference.row_axis.dims]
        assert [d.kind for d in result.col_axis.dims] == \
            [d.kind for d in reference.col_axis.dims]

    def test_row_categories_match(self, result, reference):
        assert _categories(result, "row", 0) == _categories(reference, "row", 0)

    def test_stat_categories_match(self, result, reference):
        assert _categories(result, "col", 0) == _categories(reference, "col", 0)

    def test_leaf_paths_match(self, result, reference):
        assert _leaf_paths(result, "row") == _leaf_paths(reference, "row")
        assert _leaf_paths(result, "col") == _leaf_paths(reference, "col")

    def test_body_shape_matches(self, result, reference):
        assert result.body.shape == reference.body.shape

    def test_body_values_match(self, result, reference):
        np.testing.assert_array_almost_equal(result.body, reference.body)

    def test_missing_matches(self, result, reference):
        np.testing.assert_array_equal(result.missing, reference.missing)

    def test_value_kinds_match(self, result, reference):
        assert result.value_kinds == reference.value_kinds

    def test_formats_match(self, result, reference):
        assert result.formats == reference.formats


# === Example 1b — two-way crosstab =========================================


class TestExample1bTwoWay:
    """example_1b_two_way_freq:
    region={West, East, South} × product_line={Widget A, Widget B}
    Cell counts:
        West/A=20, West/B=25, East/A=30, East/B=22, South/A=15, South/B=18
    → 130 records. Stats: N, Row%, Col%, Tot%. Total row + Total col.
    """

    CELL_COUNTS = [
        ("West",  "Widget A", 20),
        ("West",  "Widget B", 25),
        ("East",  "Widget A", 30),
        ("East",  "Widget B", 22),
        ("South", "Widget A", 15),
        ("South", "Widget B", 18),
    ]

    @pytest.fixture(params=["pandas", "polars"])
    def df(self, request):
        regions, products = [], []
        for region, product, n in self.CELL_COUNTS:
            regions.extend([region] * n)
            products.extend([product] * n)
        data = {"region": regions, "product_line": products}
        if request.param == "pandas":
            pd = pytest.importorskip("pandas")
            return pd.DataFrame(data)
        pl = pytest.importorskip("polars")
        return pl.DataFrame(data)

    @pytest.fixture
    def result(self, df):
        return pt.freq(
            df, "region", "product_line",
            levels={
                "region": ["West", "East", "South"],
                "product_line": ["Widget A", "Widget B"],
            },
        )

    @pytest.fixture
    def reference(self):
        return example_1b_two_way_freq()

    def test_dim_names_match(self, result, reference):
        assert [d.name for d in result.row_axis.dims] == \
            [d.name for d in reference.row_axis.dims]
        assert [d.name for d in result.col_axis.dims] == \
            [d.name for d in reference.col_axis.dims]

    def test_dim_kinds_match(self, result, reference):
        assert [d.kind for d in result.row_axis.dims] == \
            [d.kind for d in reference.row_axis.dims]
        assert [d.kind for d in result.col_axis.dims] == \
            [d.kind for d in reference.col_axis.dims]

    def test_row_categories_match(self, result, reference):
        assert _categories(result, "row", 0) == _categories(reference, "row", 0)

    def test_product_categories_match(self, result, reference):
        assert _categories(result, "col", 0) == _categories(reference, "col", 0)

    def test_stat_categories_match(self, result, reference):
        assert _categories(result, "col", 1) == _categories(reference, "col", 1)

    def test_leaf_paths_match(self, result, reference):
        assert _leaf_paths(result, "row") == _leaf_paths(reference, "row")
        assert _leaf_paths(result, "col") == _leaf_paths(reference, "col")

    def test_body_shape_matches(self, result, reference):
        assert result.body.shape == reference.body.shape  # (4, 12)

    def test_body_values_match(self, result, reference):
        np.testing.assert_array_almost_equal(result.body, reference.body)

    def test_missing_matches(self, result, reference):
        np.testing.assert_array_equal(result.missing, reference.missing)

    def test_value_kinds_match(self, result, reference):
        assert result.value_kinds == reference.value_kinds

    def test_formats_match(self, result, reference):
        assert result.formats == reference.formats


# === Sanity: the existing example tests still pass after the cleanup =======


class TestExamplesStillValid:
    """The redundant Category('N', label='N') → Category('N') cleanup in
    example_1b should not affect existing example_*.validate() coverage
    or rendered text. Captures the cleanup is non-breaking."""

    def test_example_1b_still_validates(self):
        table = example_1b_two_way_freq()
        table.row_axis.validate()
        table.col_axis.validate()

    def test_example_1b_text_render_unchanged_for_n_label(self):
        # "N" should appear in the rendered header (was Category("N", label="N"),
        # now Category("N") — value-driven label resolves to the same string)
        from proctab.render.text import render_text
        text = render_text(example_1b_two_way_freq())
        assert "N" in text
