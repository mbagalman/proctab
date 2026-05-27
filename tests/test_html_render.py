"""Tests for the HTML renderer (H1 + H2).

Contract source: docs/HTML_RENDERER.md.

Output is parsed with `xml.etree.ElementTree` rather than substring-matched,
per the locked test approach in the memo's H8 ticket — structural errors
(malformed row, bad span, missing escape, duplicate header) surface
immediately at parse time or at the first assertion against the tree.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np
import pytest

from proctab.examples import (
    example_1_one_way_freq,
    example_1b_two_way_freq,
    example_2_tabulate_v01,
)
from proctab.render.html import _resolve_format, render_html


# ---------------------------------------------------------------------------
# Parsing helpers (will get reused by H3-H8 tests).
# ---------------------------------------------------------------------------


def _parse(html_str: str) -> ET.Element:
    """Parse a rendered fragment, return the root <table>."""
    return ET.fromstring(html_str)


def _thead_rows(table_el: ET.Element) -> list[ET.Element]:
    thead = table_el.find("thead")
    assert thead is not None, "table missing <thead>"
    return list(thead.findall("tr"))


def _row_cells(row_el: ET.Element) -> list[ET.Element]:
    return list(row_el)


def _corner(table_el: ET.Element) -> ET.Element:
    rows = _thead_rows(table_el)
    first = _row_cells(rows[0])
    assert first, "first <thead> row is empty"
    return first[0]


# ---------------------------------------------------------------------------
# H1 — Format resolver.
# ---------------------------------------------------------------------------


class TestResolveFormatExplicit:
    """Explicit `formats[j]` always wins (priority 1)."""

    def test_explicit_wins_over_kind_default(self):
        assert _resolve_format(42.0, "{:.0f}", "currency") == "42"

    def test_explicit_percent_format(self):
        assert _resolve_format(0.42, "{:.2%}", "raw") == "42.00%"

    def test_explicit_overrides_count_default(self):
        assert _resolve_format(1234.0, "{:.0f}", "count") == "1234"


class TestResolveFormatKindDefaults:
    """Each ValueKind has a renderer-local default (priority 2)."""

    def test_count_with_float_value_uses_comma_zero_f(self):
        assert _resolve_format(1234.0, None, "count") == "1,234"

    def test_count_with_python_int_uses_d_spec(self):
        assert _resolve_format(1234, None, "count") == "1,234"

    def test_count_with_numpy_int(self):
        assert _resolve_format(np.int64(1234), None, "count") == "1,234"

    def test_count_with_numpy_float(self):
        assert _resolve_format(np.float64(1234.0), None, "count") == "1,234"

    def test_currency_default(self):
        assert _resolve_format(1234.5, None, "currency") == "$1,234.50"

    def test_percent_default_assumes_0_to_1_scale(self):
        assert _resolve_format(0.42, None, "percent") == "42.0%"

    def test_percent_default_at_one(self):
        assert _resolve_format(1.0, None, "percent") == "100.0%"

    def test_ratio_default(self):
        assert _resolve_format(0.12345, None, "ratio") == "0.123"

    def test_sum_default(self):
        assert _resolve_format(1234567.89, None, "sum") == "1,234,568"

    def test_mean_default(self):
        assert _resolve_format(42.567, None, "mean") == "42.57"

    def test_weighted_mean_default(self):
        assert _resolve_format(42.567, None, "weighted_mean") == "42.57"

    def test_median_default(self):
        assert _resolve_format(42.567, None, "median") == "42.57"

    def test_raw_default_uses_g_format(self):
        assert _resolve_format(42.5, None, "raw") == "42.5"


class TestResolveFormatFallback:
    """Unknown / unexpected value_kind values fall back to '{:g}' (priority 3)."""

    def test_unknown_kind_falls_back_to_g(self):
        result = _resolve_format(42.5, None, "totally_made_up_kind")  # type: ignore[arg-type]
        assert result == "42.5"

    def test_unknown_kind_with_integer(self):
        result = _resolve_format(42, None, "totally_made_up_kind")  # type: ignore[arg-type]
        assert result == "42"


# ---------------------------------------------------------------------------
# H1/H2 — render_html return contract.
# ---------------------------------------------------------------------------


class TestRenderHtmlEnvelope:
    def test_returns_string(self):
        out = render_html(example_1_one_way_freq())
        assert isinstance(out, str)

    def test_contains_proctab_root_class(self):
        out = render_html(example_1_one_way_freq())
        assert 'class="proctab"' in out

    def test_fragment_mode_default_has_no_doctype(self):
        out = render_html(example_1_one_way_freq())
        assert "<!DOCTYPE" not in out
        assert "<html" not in out

    def test_standalone_param_accepted_without_error(self):
        # Standalone wrapping is H6; for now it just must not raise.
        render_html(example_1_one_way_freq(), standalone=True)
        render_html(example_1_one_way_freq(), standalone=False)

    def test_render_html_importable_from_proctab_render(self):
        from proctab.render import render_html as r
        assert r is render_html

    def test_render_html_importable_from_top_level(self):
        import proctab
        assert hasattr(proctab, "render_html")

    def test_output_is_well_formed_xml(self):
        # We rely on this for parse-based testing throughout H2-H8.
        for fn in (
            example_1_one_way_freq,
            example_1b_two_way_freq,
            example_2_tabulate_v01,
        ):
            _parse(render_html(fn()))


# ---------------------------------------------------------------------------
# H2 — Column header rendering.
# ---------------------------------------------------------------------------


class TestTheadOneDim:
    """example_1_one_way_freq: col_axis dims = (_stat,) — single header row."""

    def setup_method(self):
        self.root = _parse(render_html(example_1_one_way_freq()))
        self.rows = _thead_rows(self.root)

    def test_single_tr(self):
        assert len(self.rows) == 1

    def test_first_cell_is_corner(self):
        corner = _corner(self.root)
        assert corner.get("class") == "proctab-corner"
        assert corner.get("aria-hidden") == "true"
        assert corner.get("scope") is None  # corner gets no scope per memo
        assert corner.text in (None, "")

    def test_corner_has_no_rowspan_when_single_header_row(self):
        # rowspan="1" is the implicit default; we omit the attribute.
        corner = _corner(self.root)
        assert corner.get("rowspan") is None

    def test_innermost_leaves_have_scope_col(self):
        cells = _row_cells(self.rows[0])[1:]  # skip corner
        assert len(cells) == 4
        for cell in cells:
            assert cell.get("scope") == "col"
            assert cell.get("class") == "proctab-col-data"

    def test_labels_match_freq_stat_set(self):
        labels = [c.text for c in _row_cells(self.rows[0])[1:]]
        assert labels == ["N", "Pct", "CumN", "Cum%"]

    def test_no_colspan_on_singleton_leaves(self):
        for cell in _row_cells(self.rows[0])[1:]:
            assert cell.get("colspan") is None


class TestTheadTwoDim:
    """example_1b_two_way_freq: col_axis dims = (product_line, _stat) — two rows."""

    def setup_method(self):
        self.root = _parse(render_html(example_1b_two_way_freq()))
        self.rows = _thead_rows(self.root)

    def test_two_tr(self):
        assert len(self.rows) == 2

    def test_corner_spans_two_header_rows(self):
        corner = _corner(self.root)
        assert corner.get("rowspan") == "2"
        assert corner.get("class") == "proctab-corner"
        assert corner.get("aria-hidden") == "true"

    def test_outer_groups_have_scope_colgroup(self):
        outer = _row_cells(self.rows[0])[1:]  # skip corner
        assert len(outer) == 3  # Widget A, Widget B, Total
        for cell in outer:
            assert cell.get("scope") == "colgroup"
            assert cell.get("colspan") == "4"

    def test_outer_total_carries_total_class(self):
        outer = _row_cells(self.rows[0])[1:]
        assert outer[-1].get("class") == "proctab-col-total"
        assert outer[-1].text == "Total"

    def test_outer_data_groups_carry_data_class(self):
        outer = _row_cells(self.rows[0])[1:-1]
        for cell in outer:
            assert cell.get("class") == "proctab-col-data"

    def test_inner_row_has_scope_col(self):
        inner = _row_cells(self.rows[1])
        assert len(inner) == 12  # 4 stats × 3 groups
        for cell in inner:
            assert cell.get("scope") == "col"

    def test_inner_under_total_carry_total_class(self):
        # last 4 inner cells are under the Total outer group
        inner = _row_cells(self.rows[1])
        for cell in inner[-4:]:
            assert cell.get("class") == "proctab-col-total"

    def test_inner_labels_repeat_per_outer_group(self):
        inner = [c.text for c in _row_cells(self.rows[1])]
        assert inner == ["N", "Row%", "Col%", "Tot%"] * 3


class TestTheadThreeDim:
    """example_2_tabulate_v01: col_axis dims = (quarter, _metric, _stat) — three rows."""

    def setup_method(self):
        self.root = _parse(render_html(example_2_tabulate_v01()))
        self.rows = _thead_rows(self.root)

    def test_three_tr(self):
        assert len(self.rows) == 3

    def test_corner_spans_three_header_rows(self):
        corner = _corner(self.root)
        assert corner.get("rowspan") == "3"

    def test_quarter_row_marks_total_group(self):
        outer = _row_cells(self.rows[0])[1:]
        # Q1, Q2, Total — each spans 3 leaves (revenue.sum, revenue.mean, margin.mean).
        assert [c.text for c in outer] == ["Q1", "Q2", "Total"]
        assert all(c.get("colspan") == "3" for c in outer)
        assert outer[-1].get("class") == "proctab-col-total"

    def test_metric_row_uses_colspan_per_metric(self):
        # revenue has 2 stats (sum, mean) → colspan=2; margin has 1 (mean) → no colspan.
        metric_row = _row_cells(self.rows[1])
        assert len(metric_row) == 6  # (revenue, margin) × 3 quarter groups
        for i in range(0, 6, 2):
            assert metric_row[i].text == "revenue"
            assert metric_row[i].get("colspan") == "2"
            assert metric_row[i + 1].text == "margin"
            assert metric_row[i + 1].get("colspan") is None  # singleton, no colspan
        # innermost-of-three-dims has scope="colgroup" (not "col") because
        # it's not the deepest dim
        for cell in metric_row:
            assert cell.get("scope") == "colgroup"

    def test_stat_row_is_innermost_with_scope_col(self):
        stat_row = _row_cells(self.rows[2])
        assert len(stat_row) == 9  # 3 leaves × 3 quarter groups
        for cell in stat_row:
            assert cell.get("scope") == "col"
            assert cell.get("colspan") is None

    def test_stat_row_under_total_carries_total_class(self):
        stat_row = _row_cells(self.rows[2])
        for cell in stat_row[-3:]:
            assert cell.get("class") == "proctab-col-total"
        for cell in stat_row[:-3]:
            assert cell.get("class") == "proctab-col-data"


class TestColspanContract:
    """Each `<th>` colspan in a header row sums to the total leaf count."""

    @pytest.mark.parametrize(
        "fn",
        [example_1_one_way_freq, example_1b_two_way_freq, example_2_tabulate_v01],
    )
    def test_per_row_colspan_sum_matches_leaf_count(self, fn):
        table = fn()
        n_leaves = len(table.col_axis.leaves())
        root = _parse(render_html(table))
        rows = _thead_rows(root)
        for i, row in enumerate(rows):
            non_corner_cells = _row_cells(row)
            if i == 0:
                non_corner_cells = non_corner_cells[1:]  # skip corner
            total_span = sum(int(c.get("colspan", "1")) for c in non_corner_cells)
            assert total_span == n_leaves, (
                f"row {i}: spans sum to {total_span}, expected {n_leaves}"
            )
