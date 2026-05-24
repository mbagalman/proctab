"""Tests for the four hand-built VISION example Tables + plain-text renderer."""

from __future__ import annotations

import pytest

from legible.examples import (
    example_1_one_way_freq,
    example_1b_two_way_freq,
    example_2_tabulate,
    example_5_customized,
)
from legible.render.text import render_text


ALL_EXAMPLES = [
    ("ex1",  example_1_one_way_freq),
    ("ex1b", example_1b_two_way_freq),
    ("ex2",  example_2_tabulate),
    ("ex5",  example_5_customized),
]


@pytest.fixture(params=ALL_EXAMPLES, ids=[name for name, _ in ALL_EXAMPLES])
def example(request):
    name, builder = request.param
    return name, builder()


def test_body_shape_matches_axes(example):
    _name, table = example
    assert table.body.shape == (
        len(table.row_axis.leaves()),
        len(table.col_axis.leaves()),
    )


def test_axes_validate(example):
    _name, table = example
    table.row_axis.validate()
    table.col_axis.validate()


def test_render_text_is_non_empty(example):
    _name, table = example
    output = render_text(table)
    assert output
    assert "\n" in output


def test_ex1_contains_region_labels_and_total():
    out = render_text(example_1_one_way_freq())
    for label in ("West", "East", "South", "North", "Total"):
        assert label in out


def test_ex1_renders_percent_formatting():
    out = render_text(example_1_one_way_freq())
    assert "%" in out


def test_ex1b_contains_marginals():
    out = render_text(example_1b_two_way_freq())
    assert "Widget A" in out
    assert "Widget B" in out
    assert "Total" in out


def test_ex2_subtotals_and_grand_total():
    out = render_text(example_2_tabulate())
    assert "West Subtotal" in out
    assert "East Subtotal" in out
    assert "Grand Total" in out


def test_ex2_multi_level_col_headers():
    out = render_text(example_2_tabulate())
    for q in ("Q1", "Q2", "Q3", "Q4"):
        assert q in out
    assert "Revenue" in out
    assert "Margin" in out
    assert "Sum" in out
    assert "Mean" in out
    assert "W.Mean" in out


def test_ex2_renders_na_marker():
    out = render_text(example_2_tabulate())
    assert "—" in out


def test_ex5_includes_meta_and_currency():
    out = render_text(example_5_customized())
    assert "Net Revenue by Region" in out
    assert "internal CRM" in out
    assert "$" in out
    assert "All figures USD" in out


def test_table_to_text_convenience_method():
    table = example_1_one_way_freq()
    assert table.to_text() == render_text(table)
