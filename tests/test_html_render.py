"""Tests for the HTML renderer (H1 + H2 + H3 + H4 + H5 + H6 + H7).

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
    example_5_customized,
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
from proctab.render.html import (
    _build_css,
    _cell_role,
    _inline_styles_for,
    _no_styles,
    _resolve_format,
    _STYLE_BY_CLASS,
    render_html,
)


# ---------------------------------------------------------------------------
# Parsing helpers (will get reused by H4-H8 tests).
# ---------------------------------------------------------------------------


def _parse(html_str: str) -> ET.Element:
    """Parse a rendered fragment, return the root <table>."""
    return ET.fromstring(html_str)


def _thead_rows(table_el: ET.Element) -> list[ET.Element]:
    thead = table_el.find("thead")
    assert thead is not None, "table missing <thead>"
    return list(thead.findall("tr"))


def _tbody_rows(table_el: ET.Element) -> list[ET.Element]:
    tbody = table_el.find("tbody")
    assert tbody is not None, "table missing <tbody>"
    return list(tbody.findall("tr"))


def _row_cells(row_el: ET.Element) -> list[ET.Element]:
    return list(row_el)


def _corner(table_el: ET.Element) -> ET.Element:
    rows = _thead_rows(table_el)
    first = _row_cells(rows[0])
    assert first, "first <thead> row is empty"
    return first[0]


def _row_label_text(row_el: ET.Element) -> str:
    """Return the text of the first <th> in a row (the row label)."""
    th = row_el.find("th")
    assert th is not None, "row missing a row-label <th>"
    return th.text or ""


def _row_class(row_el: ET.Element) -> str:
    return row_el.get("class") or ""


def _td_cells(row_el: ET.Element) -> list[ET.Element]:
    """Return only <td> elements (skips the row-label <th>)."""
    return list(row_el.findall("td"))


def _extract_table_from_standalone(doc: str) -> str:
    """Slice out `<table>…</table>` from a full standalone HTML5 doc.

    `xml.etree.fromstring` can't parse the surrounding doc (HTML5 DOCTYPE,
    void `<meta>` element), but the embedded `<table>` is well-formed XML.
    Tests use this to operate on the inner fragment with the same
    parsing helpers as fragment-mode tests.
    """
    start = doc.index("<table")
    end = doc.rindex("</table>") + len("</table>")
    return doc[start:end]


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


# ---------------------------------------------------------------------------
# H3 — Body rendering.
# ---------------------------------------------------------------------------


class TestCellRoleHelper:
    """Cell role precedence: total > subtotal > data, regardless of axis."""

    @pytest.mark.parametrize(
        "row_role,col_role,expected",
        [
            ("data", "data", "data"),
            ("data", "total", "total"),
            ("total", "data", "total"),
            ("total", "total", "total"),
            ("data", "subtotal", "subtotal"),
            ("subtotal", "data", "subtotal"),
            ("subtotal", "subtotal", "subtotal"),
            ("subtotal", "total", "total"),
            ("total", "subtotal", "total"),
        ],
    )
    def test_precedence(self, row_role, col_role, expected):
        assert _cell_role(row_role, col_role) == expected


class TestTbodyOneWay:
    """example_1_one_way_freq: 4 data leaf rows + 1 Total leaf row, no groups."""

    def setup_method(self):
        self.table = example_1_one_way_freq()
        self.root = _parse(render_html(self.table))
        self.rows = _tbody_rows(self.root)

    def test_row_count_matches_leaves(self):
        n_leaves = len(self.table.row_axis.leaves())
        assert len(self.rows) == n_leaves

    def test_data_rows_have_proctab_data_class(self):
        for row in self.rows[:-1]:
            assert _row_class(row) == "proctab-data"

    def test_total_row_has_proctab_total_class(self):
        assert _row_class(self.rows[-1]) == "proctab-total"

    def test_label_th_has_scope_row(self):
        for row in self.rows:
            th = row.find("th")
            assert th is not None
            assert th.get("scope") == "row"

    def test_label_indent_class_is_zero_for_one_dim_axis(self):
        for row in self.rows:
            th = row.find("th")
            cls = th.get("class") or ""
            assert "proctab-indent-0" in cls
            assert "proctab-row-label" in cls

    def test_each_data_row_has_n_cells_equal_to_col_leaves(self):
        n_col_leaves = len(self.table.col_axis.leaves())
        for row in self.rows:
            assert len(_td_cells(row)) == n_col_leaves

    def test_data_cells_carry_data_role_class(self):
        for row in self.rows[:-1]:
            for td in _td_cells(row):
                cls = td.get("class") or ""
                assert "proctab-cell" in cls
                assert "proctab-data" in cls

    def test_total_row_cells_carry_total_role_class(self):
        for td in _td_cells(self.rows[-1]):
            cls = td.get("class") or ""
            assert "proctab-cell" in cls
            assert "proctab-total" in cls

    def test_present_cells_carry_data_value_attribute(self):
        for row in self.rows:
            for td in _td_cells(row):
                # All cells in example_1 are PRESENT and finite.
                assert td.get("data-value") is not None


class TestTbodyTabulate:
    """example_2_tabulate_v01: 2 group headers + 4 data leaves + 2 subtotals + 1 grand total."""

    def setup_method(self):
        self.table = example_2_tabulate_v01()
        self.root = _parse(render_html(self.table))
        self.rows = _tbody_rows(self.root)

    def test_row_count_is_groups_plus_leaves(self):
        # 2 region groups (E, W) emitted as group-header rows + all leaves.
        n_leaves = len(self.table.row_axis.leaves())
        # The row tree has 2 interior non-root nodes (E, W).
        expected = n_leaves + 2
        assert len(self.rows) == expected

    def test_group_header_rows_have_group_header_class(self):
        group_rows = [r for r in self.rows if _row_class(r) == "proctab-group-header"]
        assert len(group_rows) == 2
        for r in group_rows:
            assert _row_label_text(r) in {"E", "W"}

    def test_group_header_has_th_rowgroup_plus_padding_td(self):
        group_rows = [r for r in self.rows if _row_class(r) == "proctab-group-header"]
        n_col_leaves = len(self.table.col_axis.leaves())
        for r in group_rows:
            ths = r.findall("th")
            assert len(ths) == 1
            assert ths[0].get("scope") == "rowgroup"
            tds = r.findall("td")
            assert len(tds) == 1
            assert tds[0].get("colspan") == str(n_col_leaves)
            assert tds[0].get("class") == "proctab-group-pad"

    def test_group_header_label_indent_is_outer_depth(self):
        # E and W are at row_axis tree depth 1 → proctab-indent-0
        group_rows = [r for r in self.rows if _row_class(r) == "proctab-group-header"]
        for r in group_rows:
            th = r.find("th")
            cls = th.get("class") or ""
            assert "proctab-indent-0" in cls

    def test_data_leaf_rows_have_proctab_data_class(self):
        data_rows = [r for r in self.rows if _row_class(r) == "proctab-data"]
        # 4 data leaves: (E,A), (E,B), (W,A), (W,B)
        assert len(data_rows) == 4

    def test_data_leaf_label_indent_is_inner_depth(self):
        data_rows = [r for r in self.rows if _row_class(r) == "proctab-data"]
        for r in data_rows:
            th = r.find("th")
            cls = th.get("class") or ""
            assert "proctab-indent-1" in cls

    def test_subtotal_rows_have_proctab_subtotal_class(self):
        sub_rows = [r for r in self.rows if _row_class(r) == "proctab-subtotal"]
        assert len(sub_rows) == 2
        for r in sub_rows:
            # Labels were set on examples.py to "E Subtotal" / "W Subtotal".
            assert "Subtotal" in _row_label_text(r)

    def test_grand_total_row_present_and_last(self):
        assert _row_class(self.rows[-1]) == "proctab-total"
        assert _row_label_text(self.rows[-1]) == "Grand Total"

    def test_subtotal_row_cells_in_total_col_are_total_role(self):
        # Cell role precedence: subtotal row × total col → total.
        sub_rows = [r for r in self.rows if _row_class(r) == "proctab-subtotal"]
        col_leaves = self.table.col_axis.leaves()
        total_col_indices = [j for j, leaf in enumerate(col_leaves) if leaf.role == "total"]
        assert total_col_indices, "v01 fixture should have at least one total col leaf"
        for r in sub_rows:
            tds = _td_cells(r)
            for j in total_col_indices:
                cls = tds[j].get("class") or ""
                assert "proctab-total" in cls
                assert "proctab-subtotal" not in cls

    def test_subtotal_row_cells_in_data_col_are_subtotal_role(self):
        sub_rows = [r for r in self.rows if _row_class(r) == "proctab-subtotal"]
        col_leaves = self.table.col_axis.leaves()
        data_col_indices = [j for j, leaf in enumerate(col_leaves) if leaf.role == "data"]
        for r in sub_rows:
            tds = _td_cells(r)
            for j in data_col_indices:
                cls = tds[j].get("class") or ""
                assert "proctab-subtotal" in cls

    def test_grand_total_row_all_cells_total_role(self):
        tds = _td_cells(self.rows[-1])
        for td in tds:
            cls = td.get("class") or ""
            assert "proctab-total" in cls


class TestTotalRowColModifiers:
    """`proctab-in-total-row` and `-col` give a top border to total rows
    and a left divider to total cols, so cells in a regular data row that
    happen to fall under a total column don't pick up a spurious heavy
    top border on every row."""

    # example_1b_two_way_freq has both a Total column AND a Total row:
    # the inner stat-leaf cells under the Total product_line group are
    # marked role=total at the col level; the bottom row is role=total
    # at the row level.

    def setup_method(self):
        self.table = example_1b_two_way_freq()
        self.root = _parse(render_html(self.table))
        self.rows = _tbody_rows(self.root)

    def _col_total_indices(self) -> list[int]:
        leaves = self.table.col_axis.leaves()
        return [j for j, leaf in enumerate(leaves) if leaf.role == "total"]

    def test_data_row_cells_in_total_col_carry_in_total_col(self):
        data_rows = [r for r in self.rows if (r.get("class") or "") == "proctab-data"]
        assert data_rows
        for r in data_rows:
            tds = _td_cells(r)
            for j in self._col_total_indices():
                cls = tds[j].get("class") or ""
                assert "proctab-in-total-col" in cls

    def test_data_row_cells_in_total_col_do_NOT_carry_in_total_row(self):
        # This is the P2 regression: previously these cells were getting
        # border-top: 2px because proctab-total carried both row and col
        # emphasis. They must be marked col-only now.
        data_rows = [r for r in self.rows if (r.get("class") or "") == "proctab-data"]
        for r in data_rows:
            tds = _td_cells(r)
            for j in self._col_total_indices():
                cls = tds[j].get("class") or ""
                assert "proctab-in-total-row" not in cls

    def test_data_row_cells_in_data_col_carry_neither_modifier(self):
        data_rows = [r for r in self.rows if (r.get("class") or "") == "proctab-data"]
        col_total_idx = set(self._col_total_indices())
        for r in data_rows:
            tds = _td_cells(r)
            for j, td in enumerate(tds):
                if j in col_total_idx:
                    continue
                cls = td.get("class") or ""
                assert "proctab-in-total-row" not in cls
                assert "proctab-in-total-col" not in cls

    def test_total_row_data_col_cells_carry_only_in_total_row(self):
        total_rows = [r for r in self.rows if (r.get("class") or "") == "proctab-total"]
        assert total_rows
        col_total_idx = set(self._col_total_indices())
        for r in total_rows:
            tds = _td_cells(r)
            for j, td in enumerate(tds):
                if j in col_total_idx:
                    continue
                cls = td.get("class") or ""
                assert "proctab-in-total-row" in cls
                assert "proctab-in-total-col" not in cls

    def test_grand_total_cell_carries_both_modifiers(self):
        # Intersection of total row and total col → both borders.
        total_rows = [r for r in self.rows if (r.get("class") or "") == "proctab-total"]
        for r in total_rows:
            tds = _td_cells(r)
            for j in self._col_total_indices():
                cls = tds[j].get("class") or ""
                assert "proctab-in-total-row" in cls
                assert "proctab-in-total-col" in cls


class TestTotalRowColStyling:
    """Inline-style output for the new modifier classes (fragment mode)."""

    def setup_method(self):
        self.root = _parse(render_html(example_1b_two_way_freq()))
        self.rows = _tbody_rows(self.root)
        leaves = example_1b_two_way_freq().col_axis.leaves()
        self.col_total_idx = [j for j, leaf in enumerate(leaves) if leaf.role == "total"]

    def test_data_row_cells_in_total_col_get_left_border_not_thick_top(self):
        # The P2 regression check, expressed in CSS terms.
        data_rows = [r for r in self.rows if (r.get("class") or "") == "proctab-data"]
        for r in data_rows:
            tds = _td_cells(r)
            for j in self.col_total_idx:
                style = tds[j].get("style") or ""
                assert "border-left: 2px solid #333" in style
                # No heavy 2px top border — only the 1px row separator
                # from proctab-cell.
                assert "border-top: 2px" not in style

    def test_total_row_cells_get_heavy_top_border(self):
        total_rows = [r for r in self.rows if (r.get("class") or "") == "proctab-total"]
        for r in total_rows:
            for td in _td_cells(r):
                style = td.get("style") or ""
                assert "border-top: 2px solid #333" in style


# ---------------------------------------------------------------------------
# Synthetic-fixture helpers for the trickier H3 cases (missing reasons,
# escaping, non-finite, empty Table).
# ---------------------------------------------------------------------------


def _build_one_row_table(
    *,
    body: list[float],
    missing_codes: list[int],
    col_labels: list[str] | None = None,
    row_label: str = "Region",
    value_kinds: tuple[str, ...] | None = None,
    formats: tuple[str | None, ...] | None = None,
) -> Table:
    """Build a 1-row × N-col Table for missing/escape/finite testing.

    Each col leaf is a top-level data leaf under a single col dim `c`.
    """
    n = len(body)
    if col_labels is None:
        col_labels = [f"c{i}" for i in range(n)]
    if value_kinds is None:
        value_kinds = ("raw",) * n
    if formats is None:
        formats = (None,) * n

    row_dim = Dimension(
        name="region", kind="category", categories=(Category(row_label),)
    )
    col_cats = tuple(Category(lab) for lab in col_labels)
    col_dim = Dimension(name="c", kind="category", categories=col_cats)

    row_leaf = Node(
        path=(Category(row_label),), depth=1, span=1, role="data", label=row_label
    )
    row_tree = Node(path=(), depth=0, span=1, role="data", children=(row_leaf,))
    row_axis = Axis(dims=(row_dim,), tree=row_tree)

    col_leaves = tuple(
        Node(path=(c,), depth=1, span=1, role="data", label=str(c.value))
        for c in col_cats
    )
    col_tree = Node(path=(), depth=0, span=n, role="data", children=col_leaves)
    col_axis = Axis(dims=(col_dim,), tree=col_tree)

    return Table(
        row_axis=row_axis,
        col_axis=col_axis,
        body=np.array([body], dtype=np.float64),
        missing=np.array([missing_codes], dtype=np.uint8),
        value_kinds=value_kinds,
        formats=formats,
    )


class TestMissingReasonRendering:
    """Each MissingReason renders its locked display text + class suffix."""

    @pytest.fixture
    def table(self):
        return _build_one_row_table(
            body=[1.0, 2.0, 3.0, 4.0],
            missing_codes=[
                int(MissingReason.EMPTY),
                int(MissingReason.NOT_APPLICABLE),
                int(MissingReason.SUPPRESSED),
                int(MissingReason.NULL),
            ],
            col_labels=["empty", "na", "supp", "null"],
        )

    def test_empty_cell_text_is_empty_string(self, table):
        tds = _td_cells(_tbody_rows(_parse(render_html(table)))[0])
        assert (tds[0].text or "") == ""

    def test_not_applicable_cell_text_is_em_dash(self, table):
        tds = _td_cells(_tbody_rows(_parse(render_html(table)))[0])
        assert tds[1].text == "—"

    def test_suppressed_cell_text_is_three_stars(self, table):
        tds = _td_cells(_tbody_rows(_parse(render_html(table)))[0])
        assert tds[2].text == "***"

    def test_null_cell_text_is_middle_dot(self, table):
        tds = _td_cells(_tbody_rows(_parse(render_html(table)))[0])
        assert tds[3].text == "·"

    def test_missing_class_suffixes(self, table):
        tds = _td_cells(_tbody_rows(_parse(render_html(table)))[0])
        cls = [td.get("class") or "" for td in tds]
        assert "proctab-missing-empty" in cls[0]
        assert "proctab-missing-not-applicable" in cls[1]
        assert "proctab-missing-suppressed" in cls[2]
        assert "proctab-missing-null" in cls[3]

    def test_missing_cells_carry_role_class_too(self, table):
        # Memo: non-PRESENT cells also get the role class (additive).
        tds = _td_cells(_tbody_rows(_parse(render_html(table)))[0])
        for td in tds:
            cls = td.get("class") or ""
            assert "proctab-cell" in cls
            assert "proctab-data" in cls

    def test_missing_cells_skip_data_value(self, table):
        tds = _td_cells(_tbody_rows(_parse(render_html(table)))[0])
        for td in tds:
            assert td.get("data-value") is None


class TestDataValueAttribute:
    """data-value uses '.17g' for finite-PRESENT; omitted for non-finite/missing."""

    def test_finite_present_emits_data_value(self):
        table = _build_one_row_table(
            body=[42.5],
            missing_codes=[int(MissingReason.PRESENT)],
            col_labels=["x"],
        )
        td = _td_cells(_tbody_rows(_parse(render_html(table)))[0])[0]
        assert td.get("data-value") == "42.5"

    def test_data_value_uses_17g_precision(self):
        # 0.1 is not exactly representable; .17g preserves round-trippability.
        table = _build_one_row_table(
            body=[0.1],
            missing_codes=[int(MissingReason.PRESENT)],
            col_labels=["x"],
        )
        td = _td_cells(_tbody_rows(_parse(render_html(table)))[0])[0]
        raw = td.get("data-value")
        assert raw == format(0.1, ".17g")
        # Round-trip check: parsing the attr back gives the exact same float.
        assert float(raw) == 0.1

    def test_nan_present_omits_data_value(self):
        table = _build_one_row_table(
            body=[float("nan")],
            missing_codes=[int(MissingReason.PRESENT)],
            col_labels=["x"],
        )
        td = _td_cells(_tbody_rows(_parse(render_html(table)))[0])[0]
        assert td.get("data-value") is None

    def test_inf_present_omits_data_value(self):
        table = _build_one_row_table(
            body=[float("inf")],
            missing_codes=[int(MissingReason.PRESENT)],
            col_labels=["x"],
        )
        td = _td_cells(_tbody_rows(_parse(render_html(table)))[0])[0]
        assert td.get("data-value") is None


class TestHtmlEscaping:
    """HTML-sensitive characters in labels and formatted values are escaped."""

    def test_column_label_with_ampersand(self):
        table = _build_one_row_table(
            body=[1.0],
            missing_codes=[int(MissingReason.PRESENT)],
            col_labels=["A&B"],
        )
        out = render_html(table)
        root = _parse(out)
        # Parse-back yields the original character; raw output is escaped.
        col_th = _thead_rows(root)[0].findall("th")[1]
        assert col_th.text == "A&B"
        assert "&amp;" in out

    def test_column_label_with_angle_brackets(self):
        table = _build_one_row_table(
            body=[1.0],
            missing_codes=[int(MissingReason.PRESENT)],
            col_labels=["<x>"],
        )
        out = render_html(table)
        root = _parse(out)
        col_th = _thead_rows(root)[0].findall("th")[1]
        assert col_th.text == "<x>"
        assert "&lt;x&gt;" in out

    def test_row_label_with_special_chars(self):
        table = _build_one_row_table(
            body=[1.0],
            missing_codes=[int(MissingReason.PRESENT)],
            col_labels=["x"],
            row_label="Q1 & Q2",
        )
        out = render_html(table)
        root = _parse(out)
        row_th = _tbody_rows(root)[0].find("th")
        assert row_th.text == "Q1 & Q2"
        assert "&amp;" in out


class TestEmptyTable:
    """Empty Table emits <thead> with just the corner cell and an empty <tbody>."""

    def _empty(self) -> Table:
        empty_dim = Dimension(name="x", kind="category", categories=())
        empty_tree = Node(path=(), depth=0, span=0, role="data", children=())
        empty_axis = Axis(dims=(empty_dim,), tree=empty_tree)
        return Table(
            row_axis=empty_axis,
            col_axis=empty_axis,
            body=np.empty((0, 0), dtype=np.float64),
            missing=np.empty((0, 0), dtype=np.uint8),
            value_kinds=(),
            formats=(),
        )

    def test_parses_as_well_formed(self):
        _parse(render_html(self._empty()))

    def test_has_thead_with_corner_only(self):
        root = _parse(render_html(self._empty()))
        rows = _thead_rows(root)
        # Single header row, single corner cell.
        assert len(rows) == 1
        cells = _row_cells(rows[0])
        assert len(cells) == 1
        assert cells[0].get("class") == "proctab-corner"

    def test_tbody_is_empty(self):
        root = _parse(render_html(self._empty()))
        rows = _tbody_rows(root)
        assert rows == []

    def test_no_caption_when_meta_empty(self):
        root = _parse(render_html(self._empty()))
        assert root.find("caption") is None

    def test_no_tfoot_when_meta_empty(self):
        root = _parse(render_html(self._empty()))
        assert root.find("tfoot") is None


# ---------------------------------------------------------------------------
# H4 — Caption + tfoot.
# ---------------------------------------------------------------------------


def _table_with_meta(meta: dict) -> Table:
    """Tiny 1×1 Table with the supplied meta — for H4 unit tests."""
    base = _build_one_row_table(
        body=[1.0],
        missing_codes=[int(MissingReason.PRESENT)],
        col_labels=["x"],
    )
    return Table(
        row_axis=base.row_axis,
        col_axis=base.col_axis,
        body=base.body,
        missing=base.missing,
        value_kinds=base.value_kinds,
        formats=base.formats,
        meta=meta,
    )


class TestCaption:
    """Title in meta produces a <caption>; absence omits it entirely."""

    def test_title_emits_caption_immediately_inside_table(self):
        table = _table_with_meta({"title": "My Title"})
        root = _parse(render_html(table))
        # caption must be the first child of <table> per HTML spec
        children = list(root)
        assert children[0].tag == "caption"
        assert children[0].text == "My Title"
        assert children[0].get("class") == "proctab-caption"

    def test_no_title_omits_caption(self):
        table = _table_with_meta({})
        root = _parse(render_html(table))
        assert root.find("caption") is None

    def test_empty_string_title_omits_caption(self):
        table = _table_with_meta({"title": ""})
        root = _parse(render_html(table))
        assert root.find("caption") is None

    def test_title_with_html_sensitive_chars_is_escaped(self):
        table = _table_with_meta({"title": "Q1 & Q2 <2026>"})
        out = render_html(table)
        root = _parse(out)
        cap = root.find("caption")
        assert cap is not None
        # parse-back yields original text; raw output is escaped
        assert cap.text == "Q1 & Q2 <2026>"
        assert "&amp;" in out and "&lt;" in out and "&gt;" in out


class TestTfoot:
    """Source and footnotes produce a <tfoot>; absence omits it."""

    def test_no_tfoot_when_no_source_no_footnotes(self):
        table = _table_with_meta({"title": "title only"})
        root = _parse(render_html(table))
        assert root.find("tfoot") is None

    def test_no_tfoot_when_meta_is_empty(self):
        table = _table_with_meta({})
        root = _parse(render_html(table))
        assert root.find("tfoot") is None

    def test_no_tfoot_when_footnotes_is_empty_list(self):
        table = _table_with_meta({"footnotes": []})
        root = _parse(render_html(table))
        assert root.find("tfoot") is None

    def test_source_only_emits_single_source_row(self):
        table = _table_with_meta({"source": "internal CRM"})
        root = _parse(render_html(table))
        tfoot = root.find("tfoot")
        assert tfoot is not None
        rows = list(tfoot.findall("tr"))
        assert len(rows) == 1
        assert rows[0].get("class") == "proctab-source"
        td = rows[0].find("td")
        assert td.text == "Source: internal CRM"

    def test_footnotes_only_emit_footnote_rows(self):
        table = _table_with_meta(
            {"footnotes": ["note one", "note two", "note three"]}
        )
        root = _parse(render_html(table))
        tfoot = root.find("tfoot")
        assert tfoot is not None
        rows = list(tfoot.findall("tr"))
        assert len(rows) == 3
        for r in rows:
            assert r.get("class") == "proctab-footnote"
        texts = [r.find("td").text for r in rows]
        assert texts == ["note one", "note two", "note three"]

    def test_source_renders_before_footnotes(self):
        # Locked schematic order: <tr.proctab-source> then <tr.proctab-footnote>.
        table = _table_with_meta(
            {"source": "src", "footnotes": ["fn1", "fn2"]}
        )
        root = _parse(render_html(table))
        tfoot = root.find("tfoot")
        rows = list(tfoot.findall("tr"))
        assert [r.get("class") for r in rows] == [
            "proctab-source",
            "proctab-footnote",
            "proctab-footnote",
        ]

    def test_tfoot_td_colspan_equals_one_plus_col_leaves(self):
        # 1 row-label column + n col leaves; test with a 4-col fixture.
        table = _build_one_row_table(
            body=[1.0, 2.0, 3.0, 4.0],
            missing_codes=[int(MissingReason.PRESENT)] * 4,
            col_labels=["a", "b", "c", "d"],
        )
        # Substitute in a meta with source + footnote.
        table = Table(
            row_axis=table.row_axis,
            col_axis=table.col_axis,
            body=table.body,
            missing=table.missing,
            value_kinds=table.value_kinds,
            formats=table.formats,
            meta={"source": "s", "footnotes": ["f"]},
        )
        root = _parse(render_html(table))
        tfoot = root.find("tfoot")
        for r in tfoot.findall("tr"):
            td = r.find("td")
            assert td.get("colspan") == "5"  # 1 + 4

    def test_source_text_is_escaped(self):
        table = _table_with_meta({"source": "A & B <c>"})
        out = render_html(table)
        root = _parse(out)
        td = root.find("tfoot").find("tr").find("td")
        assert td.text == "Source: A & B <c>"
        assert "&amp;" in out and "&lt;" in out

    def test_footnote_text_is_escaped(self):
        table = _table_with_meta({"footnotes": ["x < y && z"]})
        out = render_html(table)
        root = _parse(out)
        td = root.find("tfoot").find("tr").find("td")
        assert td.text == "x < y && z"
        assert "&amp;" in out and "&lt;" in out


class TestRenderHtmlMetaIntegration:
    """Integration: example_5_customized exercises caption + source + footnotes."""

    def setup_method(self):
        self.out = render_html(example_5_customized())
        self.root = _parse(self.out)

    def test_caption_text_matches_example_title(self):
        cap = self.root.find("caption")
        assert cap is not None
        assert cap.text == "Net Revenue by Region"

    def test_tfoot_has_source_then_footnote(self):
        tfoot = self.root.find("tfoot")
        assert tfoot is not None
        rows = list(tfoot.findall("tr"))
        assert [r.get("class") for r in rows] == [
            "proctab-source",
            "proctab-footnote",
        ]

    def test_caption_renders_before_thead(self):
        # HTML spec requires <caption> immediately inside <table>, before <thead>.
        children = list(self.root)
        tags = [c.tag for c in children]
        # tags should look like ['caption', 'thead', 'tbody', 'tfoot']
        assert tags.index("caption") < tags.index("thead")

    def test_tfoot_renders_after_tbody(self):
        children = list(self.root)
        tags = [c.tag for c in children]
        assert tags.index("tbody") < tags.index("tfoot")


# ---------------------------------------------------------------------------
# H5 — Default theme: inline-style emission (fragment) vs class-only
# (standalone), with `_build_css()` producing the same declarations both
# modes consume.
# ---------------------------------------------------------------------------


def _all_elements(root: ET.Element) -> list[ET.Element]:
    """Recursively gather every element under (and including) `root`."""
    out = [root]
    for child in root:
        out.extend(_all_elements(child))
    return out


class TestStyleResolvers:
    """Unit tests for the two StyleResolver callables."""

    def test_no_styles_returns_empty_for_any_classes(self):
        assert _no_styles([]) == ""
        assert _no_styles(["proctab-cell"]) == ""
        assert _no_styles(["proctab-total", "proctab-cell"]) == ""

    def test_inline_for_unknown_class_returns_empty(self):
        assert _inline_styles_for(["not-a-real-class"]) == ""

    def test_inline_for_empty_rule_class_returns_empty(self):
        # proctab-data has an empty declaration in v0.1.
        assert _inline_styles_for(["proctab-data"]) == ""

    def test_inline_emits_style_attribute_with_quotes(self):
        out = _inline_styles_for(["proctab-cell"])
        assert out.startswith(' style="')
        assert out.endswith('"')

    def test_inline_uses_attribute_escaping(self):
        # Font stack contains single quotes; they should be attr-escaped.
        out = _inline_styles_for(["proctab"])
        assert "'" not in out
        assert "&#x27;" in out

    def test_inline_concatenates_in_style_by_class_order(self):
        # Order in _STYLE_BY_CLASS is "proctab-cell" before "proctab-total".
        # Caller order ('total' before 'cell') should not change emit order.
        out = _inline_styles_for(["proctab-total", "proctab-cell"])
        cell_pos = out.find("font-variant-numeric")
        total_pos = out.find("font-weight: bold")
        assert 0 < cell_pos < total_pos


class TestFragmentInlineStyles:
    """Fragment mode emits `style="..."` on every classed element with rules."""

    def setup_method(self):
        self.root = _parse(render_html(example_5_customized()))

    def test_table_has_inline_style(self):
        assert "border-collapse: collapse" in (self.root.get("style") or "")

    def test_caption_has_inline_style(self):
        cap = self.root.find("caption")
        assert cap is not None
        assert "caption-side: top" in (cap.get("style") or "")

    def test_col_headers_have_inline_style(self):
        for th in self.root.find("thead").iter("th"):
            cls = th.get("class") or ""
            if "proctab-col-data" in cls or "proctab-col-total" in cls:
                assert th.get("style") is not None, (
                    f"col header {cls!r} missing style"
                )

    def test_corner_has_no_style_when_class_has_empty_rule(self):
        corner = _corner(self.root)
        assert corner.get("style") is None

    def test_body_cells_have_inline_style(self):
        for tr in _tbody_rows(self.root):
            for td in tr.findall("td"):
                cls = td.get("class") or ""
                # proctab-group-pad has no rule → no style; everything else does.
                if "proctab-group-pad" in cls:
                    continue
                assert td.get("style") is not None, (
                    f"<td class={cls!r}> missing style"
                )

    def test_total_row_cells_carry_bold(self):
        # example_1_one_way_freq ends with a Total row.
        root = _parse(render_html(example_1_one_way_freq()))
        total_row = [
            r for r in _tbody_rows(root)
            if (r.get("class") or "") == "proctab-total"
        ]
        assert total_row, "fixture should have a total row"
        for td in total_row[-1].findall("td"):
            style = td.get("style") or ""
            assert "font-weight: bold" in style

    def test_tfoot_td_has_inline_style(self):
        # Style must live on the <td> — CSS padding/border on <tr>
        # is unreliable, so the rendered cell needs the rule directly.
        tfoot = self.root.find("tfoot")
        for tr in tfoot.findall("tr"):
            td = tr.find("td")
            assert td.get("style") is not None
            assert "padding" in td.get("style")

    def test_tfoot_tr_has_no_inline_style(self):
        # The class stays on <tr> for selector targeting, but inline
        # style is moved to <td> where it actually renders.
        tfoot = self.root.find("tfoot")
        for tr in tfoot.findall("tr"):
            assert tr.get("style") is None

    def test_tfoot_td_carries_class_for_selector_targeting(self):
        # Both <tr> and <td> carry the role class so consumer CSS can
        # target whichever selector is more convenient.
        tfoot = self.root.find("tfoot")
        for tr in tfoot.findall("tr"):
            tr_cls = tr.get("class") or ""
            td_cls = tr.find("td").get("class") or ""
            assert tr_cls == td_cls
            assert tr_cls in ("proctab-source", "proctab-footnote")


class TestStandaloneClassOnly:
    """Standalone mode emits classes only — no inline `style="..."`."""

    def setup_method(self):
        doc = render_html(example_5_customized(), standalone=True)
        self.root = _parse(_extract_table_from_standalone(doc))

    def test_no_element_has_style_attribute(self):
        for el in _all_elements(self.root):
            assert el.get("style") is None, (
                f"<{el.tag} class={el.get('class')!r}> has unexpected style"
            )

    def test_classes_still_present(self):
        # Standalone mode keeps the full class hierarchy — H6's <style>
        # block will style by class. Spot-check a few.
        assert self.root.get("class") == "proctab"
        caption = self.root.find("caption")
        assert caption.get("class") == "proctab-caption"

    def test_data_value_still_emitted(self):
        # data-value is a structural data attribute, not styling.
        for tr in _tbody_rows(self.root):
            for td in tr.findall("td"):
                cls = td.get("class") or ""
                if "proctab-group-pad" in cls or "proctab-missing-" in cls:
                    continue
                assert td.get("data-value") is not None


class TestBuildCss:
    """`_build_css()` produces the standalone-mode stylesheet content."""

    def test_starts_with_table_selector(self):
        css = _build_css()
        assert css.splitlines()[0].startswith("table.proctab {")

    def test_contains_one_rule_per_nonempty_class(self):
        css = _build_css()
        expected_rules = sum(1 for v in _STYLE_BY_CLASS.values() if v)
        actual_rules = css.count(" { ")
        assert actual_rules == expected_rules

    def test_uses_prefixed_dotted_selectors(self):
        css = _build_css()
        # Every non-`table.proctab` selector starts with `.proctab-`.
        for line in css.splitlines():
            sel = line.split(" {")[0]
            assert sel == "table.proctab" or sel.startswith(".proctab-")

    def test_contains_expected_role_rules(self):
        css = _build_css()
        # The locked memo requires total emphasis + subtotal italic.
        assert ".proctab-total { font-weight: bold;" in css
        assert ".proctab-subtotal { font-style: italic;" in css

    def test_contains_tabular_nums_on_cells(self):
        # Memo: tabular numerals for cell values.
        css = _build_css()
        assert "font-variant-numeric: tabular-nums" in css

    def test_shares_declarations_with_inline_resolver(self):
        # Pick a class with a non-empty rule and verify the declaration
        # text appears verbatim in both _build_css() and _inline_styles_for.
        cls = "proctab-cell"
        decl = _STYLE_BY_CLASS[cls]
        css = _build_css()
        assert decl in css
        inline = _inline_styles_for([cls])
        assert decl in inline


# ---------------------------------------------------------------------------
# H6 — Standalone document wrapper.
# ---------------------------------------------------------------------------


import re  # for doc-level structure assertions (the full doc isn't XML-clean)


class TestStandaloneDocStructure:
    """Structural assertions on the full HTML5 doc wrapper."""

    def setup_method(self):
        self.doc = render_html(example_5_customized(), standalone=True)

    def test_starts_with_html5_doctype(self):
        assert self.doc.startswith("<!DOCTYPE html>")

    def test_has_html_root(self):
        assert "<html>" in self.doc
        assert self.doc.rstrip().endswith("</html>")

    def test_has_head_block(self):
        assert "<head>" in self.doc
        assert "</head>" in self.doc

    def test_has_meta_charset_utf8(self):
        assert '<meta charset="utf-8">' in self.doc

    def test_has_title_element_in_head(self):
        # Title appears before </head>.
        head_end = self.doc.index("</head>")
        head = self.doc[: head_end]
        m = re.search(r"<title>(.*?)</title>", head)
        assert m is not None

    def test_has_style_block_in_head(self):
        head_end = self.doc.index("</head>")
        head = self.doc[: head_end]
        assert "<style>" in head
        assert "</style>" in head

    def test_has_body_block_containing_table(self):
        body_start = self.doc.index("<body>")
        body_end = self.doc.index("</body>")
        body = self.doc[body_start:body_end]
        assert "<table" in body
        assert 'class="proctab"' in body

    def test_head_precedes_body(self):
        assert self.doc.index("</head>") < self.doc.index("<body>")

    def test_table_is_parseable_xml(self):
        # Extract the inner <table> and confirm it parses cleanly.
        _parse(_extract_table_from_standalone(self.doc))


class TestStandaloneTitle:
    """Title falls back to "proctab table" when meta lacks one."""

    def test_uses_meta_title_when_present(self):
        doc = render_html(example_5_customized(), standalone=True)
        m = re.search(r"<title>(.*?)</title>", doc)
        assert m.group(1) == "Net Revenue by Region"

    def test_falls_back_to_default_when_meta_has_no_title(self):
        table = _table_with_meta({})
        doc = render_html(table, standalone=True)
        m = re.search(r"<title>(.*?)</title>", doc)
        assert m.group(1) == "proctab table"

    def test_falls_back_when_meta_title_is_empty_string(self):
        table = _table_with_meta({"title": ""})
        doc = render_html(table, standalone=True)
        m = re.search(r"<title>(.*?)</title>", doc)
        assert m.group(1) == "proctab table"

    def test_title_escapes_html_sensitive_characters(self):
        table = _table_with_meta({"title": "Q1 & Q2 <2026>"})
        doc = render_html(table, standalone=True)
        # parse-back-style: the raw doc has escapes; the underlying text matches.
        assert "<title>Q1 &amp; Q2 &lt;2026&gt;</title>" in doc


class TestStandaloneStyleBlock:
    """The embedded <style> block carries the same CSS as _build_css()."""

    def setup_method(self):
        self.doc = render_html(example_5_customized(), standalone=True)

    def test_style_block_contains_build_css_output(self):
        css = _build_css()
        assert css in self.doc

    def test_style_block_carries_proctab_total_rule(self):
        # Spot-check: an important role rule is reachable in the doc.
        style_start = self.doc.index("<style>")
        style_end = self.doc.index("</style>")
        style_block = self.doc[style_start:style_end]
        assert ".proctab-total { font-weight: bold;" in style_block

    def test_table_in_body_has_no_inline_styles(self):
        # The whole point of the standalone wrapper: class-only markup,
        # CSS supplied by the <style> block.
        inner = _extract_table_from_standalone(self.doc)
        root = _parse(inner)
        for el in _all_elements(root):
            assert el.get("style") is None, (
                f"<{el.tag} class={el.get('class')!r}> unexpectedly has style"
            )


class TestRenderHtmlModeSeparation:
    """`standalone=False` returns a fragment; `standalone=True` returns a doc."""

    def test_fragment_mode_does_not_start_with_doctype(self):
        out = render_html(example_5_customized(), standalone=False)
        assert not out.startswith("<!DOCTYPE")
        assert "<html" not in out
        assert "<body" not in out

    def test_standalone_mode_starts_with_doctype(self):
        out = render_html(example_5_customized(), standalone=True)
        assert out.startswith("<!DOCTYPE html>")

    def test_fragment_mode_has_inline_styles(self):
        out = render_html(example_5_customized(), standalone=False)
        root = _parse(out)
        assert root.get("style") is not None

    def test_standalone_mode_inner_table_has_no_inline_styles(self):
        out = render_html(example_5_customized(), standalone=True)
        root = _parse(_extract_table_from_standalone(out))
        assert root.get("style") is None

    def test_both_modes_keep_class_hierarchy(self):
        # Classes are structural; both modes carry them.
        fragment = _parse(render_html(example_5_customized()))
        standalone = _parse(
            _extract_table_from_standalone(
                render_html(example_5_customized(), standalone=True)
            )
        )
        assert fragment.get("class") == standalone.get("class") == "proctab"


# ---------------------------------------------------------------------------
# H7 — Table._repr_html_ and Table.to_html method wiring.
# ---------------------------------------------------------------------------


import pathlib


class TestReprHtml:
    """`Table._repr_html_` is the Jupyter hook — always returns a fragment."""

    def test_returns_string(self):
        out = example_5_customized()._repr_html_()
        assert isinstance(out, str)

    def test_matches_render_html_fragment_output(self):
        table = example_5_customized()
        assert table._repr_html_() == render_html(table, standalone=False)

    def test_no_doctype_or_html_wrapper(self):
        out = example_5_customized()._repr_html_()
        assert "<!DOCTYPE" not in out
        assert "<html" not in out
        assert "<body" not in out

    def test_has_inline_styles_for_notebook_isolation(self):
        # The whole reason notebooks need fragments with inline styles.
        out = example_1_one_way_freq()._repr_html_()
        root = _parse(out)
        assert root.get("style") is not None


class TestToHtmlReturnsString:
    """`Table.to_html(path=None)` returns the standalone HTML string."""

    def test_returns_string_when_no_path(self):
        out = example_5_customized().to_html()
        assert isinstance(out, str)

    def test_matches_render_html_standalone_output(self):
        table = example_5_customized()
        assert table.to_html() == render_html(table, standalone=True)

    def test_starts_with_doctype(self):
        out = example_5_customized().to_html()
        assert out.startswith("<!DOCTYPE html>")

    def test_inner_table_is_class_only(self):
        out = example_5_customized().to_html()
        root = _parse(_extract_table_from_standalone(out))
        assert root.get("style") is None


class TestToHtmlWritesFile:
    """`Table.to_html(path=...)` writes to file and returns None."""

    def test_returns_none_when_path_given(self, tmp_path: pathlib.Path):
        out = example_5_customized().to_html(tmp_path / "out.html")
        assert out is None

    def test_writes_standalone_document_to_path(self, tmp_path: pathlib.Path):
        path = tmp_path / "out.html"
        example_5_customized().to_html(path)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")

    def test_file_content_matches_no_path_return(self, tmp_path: pathlib.Path):
        table = example_5_customized()
        path = tmp_path / "out.html"
        table.to_html(path)
        assert path.read_text(encoding="utf-8") == table.to_html()

    def test_accepts_string_path(self, tmp_path: pathlib.Path):
        # path: str | os.PathLike[str] — both supported.
        path = tmp_path / "out_str.html"
        rv = example_5_customized().to_html(str(path))
        assert rv is None
        assert path.exists()

    def test_accepts_pathlib_path(self, tmp_path: pathlib.Path):
        path = tmp_path / "out_pl.html"
        rv = example_5_customized().to_html(path)
        assert rv is None
        assert path.exists()

    def test_writes_utf8_encoded(self, tmp_path: pathlib.Path):
        # Test with a title containing non-ASCII characters.
        from proctab.model import Table
        base = _build_one_row_table(
            body=[1.0],
            missing_codes=[int(MissingReason.PRESENT)],
            col_labels=["x"],
        )
        table = Table(
            row_axis=base.row_axis,
            col_axis=base.col_axis,
            body=base.body,
            missing=base.missing,
            value_kinds=base.value_kinds,
            formats=base.formats,
            meta={"title": "Café — résumé"},
        )
        path = tmp_path / "utf8.html"
        table.to_html(path)
        raw_bytes = path.read_bytes()
        # UTF-8 encoding of the title should round-trip through bytes.
        assert "Café — résumé".encode("utf-8") in raw_bytes
        # And the file should decode cleanly as utf-8.
        text = path.read_text(encoding="utf-8")
        assert "Café — résumé" in text
