"""Tests for the Excel renderer skeleton (E1).

Covers the format resolver (priorities + every known translation),
sheet-name validator (length + reserved chars), the render_excel stub
(produces a valid .xlsx that reopens via openpyxl), and the
ImportError path when openpyxl is unavailable.

Tests requiring openpyxl use `pytest.importorskip("openpyxl")` so they
skip cleanly in environments without the optional extra. Tests for
the pure-Python helpers (_resolve_excel_format, _validate_sheet_name)
need no engine and run everywhere.
"""

from __future__ import annotations

import builtins
import pathlib
import sys

import numpy as np
import pytest

from proctab.render.excel import (
    _FORMAT_TRANSLATIONS,
    _KIND_DEFAULTS,
    _resolve_excel_format,
    _validate_sheet_name,
    render_excel,
)
from proctab.examples import (
    example_1_one_way_freq,
    example_1b_two_way_freq,
    example_2_tabulate_v01,
    example_5_customized,
)


# ---------------------------------------------------------------------------
# Format resolver — priority chain.
# ---------------------------------------------------------------------------


class TestResolveExcelFormatPriority:
    def test_explicit_known_format_wins_over_kind_default(self):
        # currency default is "$#,##0.00"; known explicit "{:,.0f}" wins.
        assert _resolve_excel_format("{:,.0f}", "currency") == "#,##0"

    def test_none_fmt_falls_back_to_kind_default(self):
        assert _resolve_excel_format(None, "currency") == "$#,##0.00"

    def test_unknown_fmt_falls_through_to_kind_default(self):
        # Format not in the translation table → kind default wins.
        assert (
            _resolve_excel_format("{:08.3e}", "currency") == "$#,##0.00"
        )

    def test_unknown_kind_with_no_fmt_returns_general(self):
        assert (
            _resolve_excel_format(None, "totally_made_up_kind")  # type: ignore[arg-type]
            == "General"
        )

    def test_unknown_kind_with_unknown_fmt_returns_general(self):
        assert (
            _resolve_excel_format(
                "{:08.3e}", "totally_made_up_kind"  # type: ignore[arg-type]
            )
            == "General"
        )


class TestResolveExcelFormatKindDefaults:
    """Each ValueKind has a fixed Excel code per the memo."""

    @pytest.mark.parametrize(
        "kind,expected",
        [
            ("count",         "#,##0"),
            ("currency",      "$#,##0.00"),
            ("percent",       "0.0%"),
            ("ratio",         "0.000"),
            ("sum",           "#,##0"),
            ("mean",          "#,##0.00"),
            ("weighted_mean", "#,##0.00"),
            ("median",        "#,##0.00"),
            ("raw",           "General"),
        ],
    )
    def test_kind_default(self, kind, expected):
        assert _resolve_excel_format(None, kind) == expected


class TestResolveExcelFormatTranslations:
    """Every known Python format in the translation table produces the
    documented Excel code. value_kind is irrelevant when the fmt is
    recognized."""

    @pytest.mark.parametrize(
        "fmt,expected",
        [
            ("{:,d}",    "#,##0"),
            ("{:,.0f}",  "#,##0"),
            ("{:,.1f}",  "#,##0.0"),
            ("{:,.2f}",  "#,##0.00"),
            ("{:,.4f}",  "#,##0.0000"),
            ("${:,.0f}", "$#,##0"),
            ("${:,.2f}", "$#,##0.00"),
            ("{:.1%}",   "0.0%"),
            ("{:.2%}",   "0.00%"),
            ("{:.1f}%",  '0.0"%"'),     # 0-100 percent — literal %
            ("{:.2f}%",  '0.00"%"'),
            ("{:.0f}",   "0"),
            ("{:.1f}",   "0.0"),
            ("{:.2f}",   "0.00"),
            ("{:.3f}",   "0.000"),
            ("{:g}",     "General"),
        ],
    )
    def test_translation(self, fmt, expected):
        assert _resolve_excel_format(fmt, "raw") == expected

    def test_freq_percent_format_translates_to_literal_percent_code(self):
        # P1 regression from the EXCEL_RENDERER memo's reviewer round 2:
        # freq() stores percents on a 0-100 scale and supplies
        # "{:.1f}%". Without translation, the percent kind default
        # "0.0%" would render 66.7 as "6670.0%".
        assert _resolve_excel_format("{:.1f}%", "percent") == '0.0"%"'


class TestResolveExcelFormatTableInvariants:
    """Sanity checks on the constant tables themselves."""

    def test_every_value_kind_listed(self):
        expected = {
            "count", "currency", "percent", "ratio", "sum",
            "mean", "weighted_mean", "median", "raw",
        }
        assert set(_KIND_DEFAULTS.keys()) == expected

    def test_no_translation_table_entry_is_empty(self):
        for fmt, code in _FORMAT_TRANSLATIONS.items():
            assert code, f"format {fmt!r} maps to empty code"


# ---------------------------------------------------------------------------
# Sheet-name validator.
# ---------------------------------------------------------------------------


class TestValidateSheetName:
    def test_simple_name_passes(self):
        _validate_sheet_name("Sheet1")
        _validate_sheet_name("Q1 Report")
        _validate_sheet_name("A")  # single char OK

    def test_31_char_name_passes(self):
        _validate_sheet_name("A" * 31)

    def test_32_char_name_raises(self):
        with pytest.raises(ValueError, match="at most 31"):
            _validate_sheet_name("A" * 32)

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="at least 1"):
            _validate_sheet_name("")

    @pytest.mark.parametrize("ch", list("\\/?*[]:"))
    def test_each_reserved_char_raises(self, ch):
        with pytest.raises(ValueError, match="reserved"):
            _validate_sheet_name(f"My{ch}Sheet")

    def test_error_lists_offending_chars(self):
        # Multiple reserved chars are all listed.
        with pytest.raises(ValueError, match=r"\['/', ':'\]"):
            _validate_sheet_name("A/B:C")

    def test_non_string_raises_typeerror(self):
        with pytest.raises(TypeError, match="must be a string"):
            _validate_sheet_name(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# render_excel stub.
# ---------------------------------------------------------------------------


class TestRenderExcelStub:
    """E1 stub: opens a workbook, sets the sheet name, saves. Body
    content lands in E2-E6."""

    def test_returns_none(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        out = render_excel(example_1_one_way_freq(), tmp_path / "stub.xlsx")
        assert out is None

    def test_writes_file_at_path(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        path = tmp_path / "stub.xlsx"
        render_excel(example_1_one_way_freq(), path)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_default_sheet_name(self, tmp_path: pathlib.Path):
        openpyxl = pytest.importorskip("openpyxl")
        path = tmp_path / "stub.xlsx"
        render_excel(example_1_one_way_freq(), path)
        wb = openpyxl.load_workbook(path)
        assert wb.sheetnames == ["Sheet1"]

    def test_sheet_kwarg_overrides_default(self, tmp_path: pathlib.Path):
        openpyxl = pytest.importorskip("openpyxl")
        path = tmp_path / "stub.xlsx"
        render_excel(
            example_1_one_way_freq(), path, sheet="Q1 Report"
        )
        wb = openpyxl.load_workbook(path)
        assert wb.sheetnames == ["Q1 Report"]

    def test_invalid_sheet_kwarg_raises_before_writing(
        self, tmp_path: pathlib.Path
    ):
        pytest.importorskip("openpyxl")
        path = tmp_path / "should_not_exist.xlsx"
        with pytest.raises(ValueError, match="reserved"):
            render_excel(
                example_1_one_way_freq(), path, sheet="bad/name"
            )
        assert not path.exists()  # validation happens before file creation

    def test_accepts_string_path(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        path = str(tmp_path / "stub_str.xlsx")
        render_excel(example_1_one_way_freq(), path)
        assert pathlib.Path(path).exists()

    def test_accepts_pathlib_path(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        path = tmp_path / "stub_pl.xlsx"
        render_excel(example_1_one_way_freq(), path)
        assert path.exists()


# ---------------------------------------------------------------------------
# Module-level export wiring.
# ---------------------------------------------------------------------------


class TestRenderExcelExported:
    def test_importable_from_proctab_render(self):
        from proctab.render import render_excel as r
        assert r is render_excel

    def test_importable_from_top_level(self):
        import proctab
        assert hasattr(proctab, "render_excel")
        assert proctab.render_excel is render_excel


# ---------------------------------------------------------------------------
# Missing-openpyxl path.
# ---------------------------------------------------------------------------


class TestMissingOpenpyxlError:
    """When openpyxl is not installed, render_excel raises a friendly
    ImportError with the install command. Simulated via monkeypatching
    sys.modules so the test runs whether or not openpyxl is actually
    installed in the dev env."""

    def test_friendly_import_error(self, tmp_path: pathlib.Path, monkeypatch):
        # Save and remove any cached openpyxl reference; make a fresh
        # import attempt fail.
        for name in list(sys.modules):
            if name == "openpyxl" or name.startswith("openpyxl."):
                monkeypatch.setitem(sys.modules, name, None)

        original_import = builtins.__import__

        def _no_openpyxl(name, *args, **kwargs):
            if name == "openpyxl" or name.startswith("openpyxl."):
                raise ImportError(f"simulated absent: {name}")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_openpyxl)

        with pytest.raises(ImportError, match=r"proctab\[excel\]"):
            render_excel(
                example_1_one_way_freq(), tmp_path / "should_not_create.xlsx"
            )

    def test_error_message_mentions_openpyxl(self, tmp_path, monkeypatch):
        for name in list(sys.modules):
            if name == "openpyxl" or name.startswith("openpyxl."):
                monkeypatch.setitem(sys.modules, name, None)

        original_import = builtins.__import__

        def _no_openpyxl(name, *args, **kwargs):
            if name == "openpyxl" or name.startswith("openpyxl."):
                raise ImportError(f"simulated absent: {name}")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_openpyxl)

        with pytest.raises(ImportError, match="openpyxl"):
            render_excel(
                example_1_one_way_freq(), tmp_path / "should_not_create.xlsx"
            )

    def test_invalid_sheet_raises_value_error_even_without_openpyxl(
        self, tmp_path, monkeypatch,
    ):
        # P3 regression: an invalid sheet= must raise the documented
        # ValueError deterministically, not the ImportError that would
        # otherwise mask it when openpyxl is absent.
        for name in list(sys.modules):
            if name == "openpyxl" or name.startswith("openpyxl."):
                monkeypatch.setitem(sys.modules, name, None)

        original_import = builtins.__import__

        def _no_openpyxl(name, *args, **kwargs):
            if name == "openpyxl" or name.startswith("openpyxl."):
                raise ImportError(f"simulated absent: {name}")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_openpyxl)

        with pytest.raises(ValueError, match="reserved"):
            render_excel(
                example_1_one_way_freq(),
                tmp_path / "should_not_create.xlsx",
                sheet="bad/name",
            )


# ---------------------------------------------------------------------------
# E2 — column header rendering. Reopen the rendered file and walk cells.
# ---------------------------------------------------------------------------


def _render_and_load(table, tmp_path):
    """Render `table` to `tmp_path/out.xlsx` and return the active worksheet."""
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "out.xlsx"
    render_excel(table, path)
    return openpyxl.load_workbook(path).active


def _merged_ranges(ws) -> set[str]:
    """Set of merged-range strings like {'B3:E3', 'F3:I3', ...}."""
    return {str(rng) for rng in ws.merged_cells.ranges}


def _layout_for(table) -> tuple[bool, int, int]:
    """(title_present, H, header_start) — derived the same way the
    renderer derives them, for assertion convenience."""
    title_present = bool(table.meta.get("title"))
    H = len(table.col_axis.dims)
    header_start = 3 if title_present else 1
    return title_present, H, header_start


class TestTheadOneDim:
    """example_1_one_way_freq: col_axis dims = (_stat,), 4 stat leaves,
    title present → header_start=3, single header row, no merging."""

    def test_header_row_label_values(self, tmp_path: pathlib.Path):
        ws = _render_and_load(example_1_one_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1_one_way_freq())
        assert ws.cell(row=hs, column=2).value == "N"
        assert ws.cell(row=hs, column=3).value == "Pct"
        assert ws.cell(row=hs, column=4).value == "CumN"
        assert ws.cell(row=hs, column=5).value == "Cum%"

    def test_corner_cell_blank(self, tmp_path: pathlib.Path):
        ws = _render_and_load(example_1_one_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1_one_way_freq())
        assert ws.cell(row=hs, column=1).value is None

    def test_no_header_row_merged_ranges(self, tmp_path: pathlib.Path):
        # Single-dim col axis → innermost depth, each leaf is one cell.
        # The only merge in this fixture is the title row (E4).
        ws = _render_and_load(example_1_one_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1_one_way_freq())
        header_merges = [
            str(r) for r in ws.merged_cells.ranges
            if f":{hs}" in str(r) or f"{hs}:" in str(r)
        ]
        assert header_merges == []


class TestTheadTwoDim:
    """example_1b_two_way_freq: col_axis dims = (product_line, _stat),
    12 leaves (3 groups × 4 stats), title present → header_start=3,
    two header rows; row 3 has 3 merged groups, row 4 has 12 single cells."""

    def test_outer_group_labels(self, tmp_path: pathlib.Path):
        ws = _render_and_load(example_1b_two_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1b_two_way_freq())
        # Outer header row at hs (=3 here). Labels at the start of each
        # merged range — every 4th column starting at B.
        assert ws.cell(row=hs, column=2).value == "Widget A"
        assert ws.cell(row=hs, column=6).value == "Widget B"
        assert ws.cell(row=hs, column=10).value == "Total"

    def test_outer_groups_merged_across_four_cells_each(
        self, tmp_path: pathlib.Path
    ):
        ws = _render_and_load(example_1b_two_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1b_two_way_freq())
        ranges = _merged_ranges(ws)
        # 3 outer groups × span 4 = ranges starting at B, F, J.
        assert f"B{hs}:E{hs}" in ranges
        assert f"F{hs}:I{hs}" in ranges
        assert f"J{hs}:M{hs}" in ranges

    def test_inner_stat_labels_repeat_per_group(
        self, tmp_path: pathlib.Path
    ):
        ws = _render_and_load(example_1b_two_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1b_two_way_freq())
        inner_row = hs + 1
        inner_labels = [
            ws.cell(row=inner_row, column=c).value for c in range(2, 14)
        ]
        assert inner_labels == ["N", "Row%", "Col%", "Tot%"] * 3

    def test_inner_row_has_no_merges(self, tmp_path: pathlib.Path):
        # Innermost depth → each leaf is one cell. Allowed merges:
        # the title row (row 1) and the 3 outer-header-row merges.
        ws = _render_and_load(example_1b_two_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1b_two_way_freq())
        inner_row = hs + 1
        for r in _merged_ranges(ws):
            assert not (f":{inner_row}" in r or f"{inner_row}:" in r), (
                f"inner header row should have no merges, found {r}"
            )

    def test_corner_cells_blank(self, tmp_path: pathlib.Path):
        ws = _render_and_load(example_1b_two_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1b_two_way_freq())
        # A on every header row stays blank.
        assert ws.cell(row=hs, column=1).value is None
        assert ws.cell(row=hs + 1, column=1).value is None


class TestTheadThreeDim:
    """example_2_tabulate_v01: col_axis dims = (quarter, _metric, _stat),
    9 leaves, no title → header_start=1, three header rows."""

    def test_no_title_means_header_starts_at_row_one(
        self, tmp_path: pathlib.Path
    ):
        title_present, _, _ = _layout_for(example_2_tabulate_v01())
        # Sanity: the fixture truly has no title.
        assert title_present is False
        ws = _render_and_load(example_2_tabulate_v01(), tmp_path)
        # First header row's first label cell is at B1.
        assert ws.cell(row=1, column=2).value == "Q1"

    def test_quarter_row_groups(self, tmp_path: pathlib.Path):
        ws = _render_and_load(example_2_tabulate_v01(), tmp_path)
        assert ws.cell(row=1, column=2).value == "Q1"
        assert ws.cell(row=1, column=5).value == "Q2"
        assert ws.cell(row=1, column=8).value == "Total"
        ranges = _merged_ranges(ws)
        assert "B1:D1" in ranges
        assert "E1:G1" in ranges
        assert "H1:J1" in ranges

    def test_metric_row_revenue_spans_two_margin_single(
        self, tmp_path: pathlib.Path
    ):
        # Per-quarter: revenue (sum, mean → span 2) + margin (mean → 1).
        ws = _render_and_load(example_2_tabulate_v01(), tmp_path)
        # B2 starts the first quarter's revenue (spans B2:C2);
        # D2 is its margin single cell.
        assert ws.cell(row=2, column=2).value == "revenue"
        assert ws.cell(row=2, column=4).value == "margin"
        ranges = _merged_ranges(ws)
        assert "B2:C2" in ranges
        assert "E2:F2" in ranges
        assert "H2:I2" in ranges
        # margin singletons → no merges
        for r in ranges:
            assert not r.startswith("D2:")
            assert not r.startswith("G2:")
            assert not r.startswith("J2:")

    def test_stat_row_individual_leaves(self, tmp_path: pathlib.Path):
        ws = _render_and_load(example_2_tabulate_v01(), tmp_path)
        labels = [ws.cell(row=3, column=c).value for c in range(2, 11)]
        assert labels == ["sum", "mean", "mean"] * 3


class TestTheadWithTitle:
    """title in meta shifts header_start to row 3 (rows 1+2 reserved
    for title + spacer, even though title writing is E4's job)."""

    def test_header_starts_at_row_3_when_title_present(
        self, tmp_path: pathlib.Path
    ):
        title_present, _, hs = _layout_for(example_5_customized())
        assert title_present is True
        assert hs == 3
        ws = _render_and_load(example_5_customized(), tmp_path)
        # Title now occupies row 1; row 2 stays blank (spacer); headers
        # start at row 3.
        assert ws.cell(row=1, column=1).value == "Net Revenue by Region"
        assert ws.cell(row=2, column=1).value is None
        assert ws.cell(row=3, column=2).value == "Q1"


class TestTheadEmptyAxis:
    """An empty col axis emits no header rows; the file still saves."""

    def _empty_axis_table(self):
        # 1-row × 0-col table.
        from proctab.model import Axis, Category, Dimension, Node, Table
        row_dim = Dimension(
            name="region", kind="category", categories=(Category("W"),)
        )
        row_leaf = Node(path=(Category("W"),), depth=1, span=1, role="data")
        row_tree = Node(path=(), depth=0, span=1, role="data", children=(row_leaf,))
        empty_col_dim = Dimension(
            name="c", kind="category", categories=()
        )
        empty_col_tree = Node(
            path=(), depth=0, span=0, role="data", children=()
        )
        return Table(
            row_axis=Axis(dims=(row_dim,), tree=row_tree),
            col_axis=Axis(dims=(empty_col_dim,), tree=empty_col_tree),
            body=np.empty((1, 0), dtype=np.float64),
            missing=np.empty((1, 0), dtype=np.uint8),
            value_kinds=(),
            formats=(),
        )

    def test_renders_without_error(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        render_excel(self._empty_axis_table(), tmp_path / "empty.xlsx")
        assert (tmp_path / "empty.xlsx").exists()

    def test_no_header_cells_written(self, tmp_path: pathlib.Path):
        openpyxl = pytest.importorskip("openpyxl")
        path = tmp_path / "empty.xlsx"
        render_excel(self._empty_axis_table(), path)
        ws = openpyxl.load_workbook(path).active
        # No header content of any kind. (Empty workbooks have a single
        # empty sheet by openpyxl default.)
        assert ws.cell(row=1, column=1).value is None
        assert ws.cell(row=1, column=2).value is None

    def test_no_body_row_labels_written(self, tmp_path: pathlib.Path):
        # P2 regression: even though the row axis has a leaf ("W"),
        # zero col leaves means the memo says no body rows at all.
        # Previously the renderer wrote 'W' at A2; the fix is an
        # early return in _write_tbody.
        openpyxl = pytest.importorskip("openpyxl")
        path = tmp_path / "empty.xlsx"
        render_excel(self._empty_axis_table(), path)
        ws = openpyxl.load_workbook(path).active
        # Walk down the first few rows of column A; all should be blank.
        for r in range(1, 6):
            assert ws.cell(row=r, column=1).value is None, (
                f"A{r} should be blank for an empty-col-axis table"
            )


class TestTheadCornerCellAlwaysBlank:
    """Cross-cutting: column A on every header row stays blank,
    across all example fixtures."""

    @pytest.mark.parametrize(
        "fixture",
        [
            example_1_one_way_freq,
            example_1b_two_way_freq,
            example_2_tabulate_v01,
            example_5_customized,
        ],
    )
    def test_corner_blank(self, fixture, tmp_path: pathlib.Path):
        ws = _render_and_load(fixture(), tmp_path)
        _, H, hs = _layout_for(fixture())
        for r in range(hs, hs + H):
            assert ws.cell(row=r, column=1).value is None, (
                f"corner A{r} should be blank in {fixture.__name__}"
            )


# ---------------------------------------------------------------------------
# E3 — body rendering. Reopen the rendered file and walk body cells.
# ---------------------------------------------------------------------------


def _body_start(table) -> int:
    """Match the renderer's body_start = header_start + H."""
    title_present, H, header_start = _layout_for(table)
    return header_start + H


class TestTbodyOneWay:
    """example_1_one_way_freq: 5 leaf rows (4 data + 1 total), no group
    headers. Each leaf row: row label at A + 4 numeric cells at B..E."""

    def test_row_count_matches_leaves(self, tmp_path: pathlib.Path):
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        body_start = _body_start(table)
        n_leaves = len(table.row_axis.leaves())  # 5
        # First non-leaf row after body should be empty (no spacer yet in E3).
        for i in range(n_leaves):
            assert ws.cell(row=body_start + i, column=1).value is not None
        assert ws.cell(row=body_start + n_leaves, column=1).value is None

    def test_row_labels(self, tmp_path: pathlib.Path):
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        labels = [ws.cell(row=bs + i, column=1).value for i in range(5)]
        assert labels == ["West", "East", "South", "North", "Total"]

    def test_data_cells_numeric(self, tmp_path: pathlib.Path):
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # West row: N=45, Pct=30.0, CumN=45, CumPct=30.0
        assert ws.cell(row=bs, column=2).value == 45
        assert ws.cell(row=bs, column=3).value == 30.0
        assert ws.cell(row=bs, column=4).value == 45
        assert ws.cell(row=bs, column=5).value == 30.0

    def test_total_row_cells_numeric(self, tmp_path: pathlib.Path):
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # Total row (last): N=150, Pct=100.0, CumN=150, CumPct=100.0
        total_row = bs + 4
        assert ws.cell(row=total_row, column=2).value == 150
        assert ws.cell(row=total_row, column=3).value == 100.0

    def test_count_columns_use_count_format(self, tmp_path: pathlib.Path):
        # value_kind=count, formats[j]="{:.0f}" → resolver returns "0".
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        for r in range(bs, bs + 5):
            assert ws.cell(row=r, column=2).number_format == "0"
            assert ws.cell(row=r, column=4).number_format == "0"

    def test_percent_columns_use_literal_percent_format(
        self, tmp_path: pathlib.Path
    ):
        # value_kind=percent, formats[j]="{:.1f}%" — 0-100 storage —
        # resolver returns '0.0"%"'. Key P1 regression: WITHOUT this,
        # raw 30.0 would render as "3000.0%" via the "0.0%" default.
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        for r in range(bs, bs + 5):
            assert ws.cell(row=r, column=3).number_format == '0.0"%"'
            assert ws.cell(row=r, column=5).number_format == '0.0"%"'


class TestTbodyTabulate:
    """example_2_tabulate_v01: 2 group headers (E, W) + 4 data leaves +
    2 subtotals + 1 grand total = 9 body rows. Group rows have only the
    row label; leaf rows carry numeric body cells."""

    def test_row_count_groups_plus_leaves(self, tmp_path: pathlib.Path):
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # 9 body rows total; row 10 should be the first blank.
        for i in range(9):
            assert ws.cell(row=bs + i, column=1).value is not None
        assert ws.cell(row=bs + 9, column=1).value is None

    def test_row_labels_in_order(self, tmp_path: pathlib.Path):
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        labels = [ws.cell(row=bs + i, column=1).value for i in range(9)]
        assert labels == [
            "E", "A", "B", "E Subtotal",
            "W", "A", "B", "W Subtotal",
            "Grand Total",
        ]

    def test_group_header_rows_have_blank_body_cells(
        self, tmp_path: pathlib.Path
    ):
        # E (row bs) and W (row bs+4) are interior nodes — column A only.
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        for row in (bs, bs + 4):
            for col in range(2, 11):  # 9 body cols (B..J)
                assert ws.cell(row=row, column=col).value is None

    def test_leaf_rows_have_numeric_body_cells(
        self, tmp_path: pathlib.Path
    ):
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # E.A leaf is bs+1; check it has 9 numeric cells.
        for col in range(2, 11):
            v = ws.cell(row=bs + 1, column=col).value
            assert v is not None
            assert isinstance(v, (int, float))

    def test_grand_total_row_has_data(self, tmp_path: pathlib.Path):
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        grand_total_row = bs + 8
        # Grand Total should sum sums and average means. First cell:
        # revenue.sum at Q1 = 10+30+50+70 = 160.
        assert ws.cell(row=grand_total_row, column=2).value == 160


def _one_row_table_with_missing(body, missing_codes, formats=None, kinds=None):
    """Tiny 1-row × N-col table for MissingReason dispatch tests."""
    from proctab.model import Axis, Category, Dimension, Node, Table

    n = len(body)
    if formats is None:
        formats = (None,) * n
    if kinds is None:
        kinds = ("raw",) * n

    row_dim = Dimension(
        name="region", kind="category", categories=(Category("W"),)
    )
    col_cats = tuple(Category(f"c{i}") for i in range(n))
    col_dim = Dimension(name="c", kind="category", categories=col_cats)
    row_leaf = Node(path=(Category("W"),), depth=1, span=1, role="data")
    row_tree = Node(path=(), depth=0, span=1, role="data", children=(row_leaf,))
    col_leaves = tuple(
        Node(path=(c,), depth=1, span=1, role="data") for c in col_cats
    )
    col_tree = Node(path=(), depth=0, span=n, role="data", children=col_leaves)
    return Table(
        row_axis=Axis(dims=(row_dim,), tree=row_tree),
        col_axis=Axis(dims=(col_dim,), tree=col_tree),
        body=np.array([body], dtype=np.float64),
        missing=np.array([missing_codes], dtype=np.uint8),
        value_kinds=kinds,
        formats=formats,
    )


class TestMissingReasonDispatch:
    """Per-cell dispatch on MissingReason matches the memo's table:
    PRESENT → numeric, EMPTY → blank, others → text markers."""

    def _render(self, table, tmp_path):
        openpyxl = pytest.importorskip("openpyxl")
        path = tmp_path / "missing.xlsx"
        render_excel(table, path)
        return openpyxl.load_workbook(path).active

    def test_present_cell_writes_numeric_value(self, tmp_path: pathlib.Path):
        from proctab.model import MissingReason
        table = _one_row_table_with_missing(
            [42.5], [int(MissingReason.PRESENT)]
        )
        ws = self._render(table, tmp_path)
        bs = _body_start(table)
        cell = ws.cell(row=bs, column=2)
        assert cell.value == 42.5
        assert isinstance(cell.value, float)

    def test_empty_cell_writes_no_value(self, tmp_path: pathlib.Path):
        from proctab.model import MissingReason
        table = _one_row_table_with_missing(
            [0.0], [int(MissingReason.EMPTY)]
        )
        ws = self._render(table, tmp_path)
        bs = _body_start(table)
        assert ws.cell(row=bs, column=2).value is None

    def test_not_applicable_writes_em_dash(self, tmp_path: pathlib.Path):
        from proctab.model import MissingReason
        table = _one_row_table_with_missing(
            [0.0], [int(MissingReason.NOT_APPLICABLE)]
        )
        ws = self._render(table, tmp_path)
        bs = _body_start(table)
        assert ws.cell(row=bs, column=2).value == "—"

    def test_suppressed_writes_three_stars(self, tmp_path: pathlib.Path):
        from proctab.model import MissingReason
        table = _one_row_table_with_missing(
            [0.0], [int(MissingReason.SUPPRESSED)]
        )
        ws = self._render(table, tmp_path)
        bs = _body_start(table)
        assert ws.cell(row=bs, column=2).value == "***"

    def test_null_writes_middle_dot(self, tmp_path: pathlib.Path):
        from proctab.model import MissingReason
        table = _one_row_table_with_missing(
            [0.0], [int(MissingReason.NULL)]
        )
        ws = self._render(table, tmp_path)
        bs = _body_start(table)
        assert ws.cell(row=bs, column=2).value == "·"

    def test_each_cell_carries_number_format(self, tmp_path: pathlib.Path):
        # Even text-markers and blanks carry number_format so the
        # column's format is consistent if a user types a value in.
        from proctab.model import MissingReason
        table = _one_row_table_with_missing(
            [1.0, 0.0, 0.0, 0.0, 0.0],
            [
                int(MissingReason.PRESENT),
                int(MissingReason.EMPTY),
                int(MissingReason.NOT_APPLICABLE),
                int(MissingReason.SUPPRESSED),
                int(MissingReason.NULL),
            ],
            formats=("{:,.2f}",) * 5,
            kinds=("mean",) * 5,
        )
        ws = self._render(table, tmp_path)
        bs = _body_start(table)
        for col in range(2, 7):
            assert ws.cell(row=bs, column=col).number_format == "#,##0.00"


class TestTbodyValueKindFormats:
    """Numeric format resolution for each `value_kind` reaches the cell
    via `_resolve_excel_format`. Spot-check with example_5_customized
    (currency revenue column, `{:.0f}` style format)."""

    def test_currency_column_uses_currency_code(self, tmp_path: pathlib.Path):
        # example_5_customized: 4 currency cols with formats="${:,.0f}" →
        # resolver returns "$#,##0".
        table = example_5_customized()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # First body row's first body cell carries the currency format.
        assert ws.cell(row=bs, column=2).number_format == "$#,##0"

    def test_currency_values_are_numeric(self, tmp_path: pathlib.Path):
        table = example_5_customized()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # First currency cell should be numeric (not text-formatted).
        v = ws.cell(row=bs, column=2).value
        assert isinstance(v, (int, float))


# ---------------------------------------------------------------------------
# E4 — title + source + footnotes.
# ---------------------------------------------------------------------------


def _body_end(table) -> int:
    """Last body row number that `_write_tbody` would write to.

    Empty col-axis tables return body_start - 1 (no body rows).
    """
    from proctab.render.excel import _walk_nonroot
    bs = _body_start(table)
    if len(table.col_axis.leaves()) == 0:
        return bs - 1
    n_body_rows = sum(1 for _ in _walk_nonroot(table.row_axis.tree))
    return bs + n_body_rows - 1


def _table_with_meta_at_top(base_meta: dict, base_table=None):
    """Tiny 1-row × 1-col Table with the given meta dict."""
    from proctab.model import Axis, Category, Dimension, Node, Table

    base_row_dim = Dimension(
        name="region", kind="category", categories=(Category("W"),)
    )
    row_leaf = Node(path=(Category("W"),), depth=1, span=1, role="data")
    row_tree = Node(
        path=(), depth=0, span=1, role="data", children=(row_leaf,)
    )
    base_col_dim = Dimension(
        name="c", kind="category", categories=(Category("x"),)
    )
    col_leaf = Node(path=(Category("x"),), depth=1, span=1, role="data")
    col_tree = Node(
        path=(), depth=0, span=1, role="data", children=(col_leaf,)
    )
    return Table(
        row_axis=Axis(dims=(base_row_dim,), tree=row_tree),
        col_axis=Axis(dims=(base_col_dim,), tree=col_tree),
        body=np.array([[1.0]], dtype=np.float64),
        missing=np.array([[0]], dtype=np.uint8),
        value_kinds=("raw",),
        formats=(None,),
        meta=base_meta,
    )


class TestTitleRendering:
    """meta.title → bold +2pt cell at A1 merged across body columns."""

    def test_no_title_means_row_1_blank(self, tmp_path: pathlib.Path):
        ws = _render_and_load(
            _table_with_meta_at_top({}), tmp_path
        )
        assert ws.cell(row=1, column=1).value is None

    def test_title_text_at_a1(self, tmp_path: pathlib.Path):
        ws = _render_and_load(
            _table_with_meta_at_top({"title": "My Report"}), tmp_path
        )
        assert ws.cell(row=1, column=1).value == "My Report"

    def test_title_bold_and_size_13(self, tmp_path: pathlib.Path):
        ws = _render_and_load(
            _table_with_meta_at_top({"title": "X"}), tmp_path
        )
        cell = ws.cell(row=1, column=1)
        assert cell.font.bold is True
        assert cell.font.size == 13

    def test_title_left_aligned(self, tmp_path: pathlib.Path):
        ws = _render_and_load(
            _table_with_meta_at_top({"title": "X"}), tmp_path
        )
        assert ws.cell(row=1, column=1).alignment.horizontal == "left"

    def test_title_merged_across_body_columns(self, tmp_path: pathlib.Path):
        # Use example_5_customized: 4 col leaves → merge A1:E1.
        ws = _render_and_load(example_5_customized(), tmp_path)
        ranges = {str(r) for r in ws.merged_cells.ranges}
        assert "A1:E1" in ranges

    def test_title_not_merged_when_empty_col_axis(
        self, tmp_path: pathlib.Path
    ):
        # 0-col-leaf table → end_col == 1 → no merge applied (would be
        # an A1:A1 no-op merge, which we explicitly guard against).
        from proctab.model import Axis, Category, Dimension, Node, Table

        row_dim = Dimension(
            name="region", kind="category", categories=(Category("W"),)
        )
        row_leaf = Node(path=(Category("W"),), depth=1, span=1, role="data")
        row_tree = Node(
            path=(), depth=0, span=1, role="data", children=(row_leaf,)
        )
        empty_col_dim = Dimension(
            name="c", kind="category", categories=()
        )
        empty_col_tree = Node(
            path=(), depth=0, span=0, role="data", children=()
        )
        table = Table(
            row_axis=Axis(dims=(row_dim,), tree=row_tree),
            col_axis=Axis(dims=(empty_col_dim,), tree=empty_col_tree),
            body=np.empty((1, 0), dtype=np.float64),
            missing=np.empty((1, 0), dtype=np.uint8),
            value_kinds=(),
            formats=(),
            meta={"title": "X"},
        )
        ws = _render_and_load(table, tmp_path)
        # Title text still appears at A1.
        assert ws.cell(row=1, column=1).value == "X"
        # But no merge spans A1.
        title_merges = [
            str(r) for r in ws.merged_cells.ranges
            if str(r).startswith("A1:")
        ]
        assert title_merges == []

    def test_empty_meta_means_no_title(self, tmp_path: pathlib.Path):
        ws = _render_and_load(
            _table_with_meta_at_top({}), tmp_path
        )
        assert ws.cell(row=1, column=1).value is None

    def test_empty_string_title_skipped(self, tmp_path: pathlib.Path):
        ws = _render_and_load(
            _table_with_meta_at_top({"title": ""}), tmp_path
        )
        assert ws.cell(row=1, column=1).value is None


class TestTfootSource:
    """meta.source → 'Source: ...' row at body_end + 2, merged, wrap,
    italic, smaller font, thin top border."""

    def test_no_meta_means_no_tfoot(self, tmp_path: pathlib.Path):
        table = _table_with_meta_at_top({})
        ws = _render_and_load(table, tmp_path)
        for r in range(_body_end(table) + 1, _body_end(table) + 5):
            assert ws.cell(row=r, column=1).value is None

    def test_source_text_with_prefix(self, tmp_path: pathlib.Path):
        table = _table_with_meta_at_top({"source": "Internal CRM"})
        ws = _render_and_load(table, tmp_path)
        row = _body_end(table) + 2
        assert ws.cell(row=row, column=1).value == "Source: Internal CRM"

    def test_source_styling(self, tmp_path: pathlib.Path):
        table = _table_with_meta_at_top({"source": "S"})
        ws = _render_and_load(table, tmp_path)
        cell = ws.cell(row=_body_end(table) + 2, column=1)
        assert cell.font.italic is True
        assert cell.font.size == 10
        assert cell.alignment.wrap_text is True
        assert cell.alignment.horizontal == "left"
        assert cell.border.top.style == "thin"

    def test_source_merged_across_body_columns(
        self, tmp_path: pathlib.Path
    ):
        # example_5_customized has source + 4 col leaves → merge A..E
        ws = _render_and_load(example_5_customized(), tmp_path)
        bs = _body_start(example_5_customized())
        be = _body_end(example_5_customized())
        ranges = {str(r) for r in ws.merged_cells.ranges}
        assert f"A{be + 2}:E{be + 2}" in ranges

    def test_source_blank_spacer_row_between_body_and_source(
        self, tmp_path: pathlib.Path
    ):
        table = _table_with_meta_at_top({"source": "S"})
        ws = _render_and_load(table, tmp_path)
        be = _body_end(table)
        # body_end + 1 is the blank spacer.
        assert ws.cell(row=be + 1, column=1).value is None


class TestTfootFootnotes:
    """meta.footnotes → one row each from body_end + 3 onwards, merged,
    wrap, italic + smaller. Only the first tfoot row carries the top
    border; when source is present that's source, else the first footnote."""

    def test_one_footnote_only_at_body_end_plus_2(
        self, tmp_path: pathlib.Path
    ):
        # No source: first footnote starts at body_end + 2 and gets
        # the top border.
        table = _table_with_meta_at_top({"footnotes": ["note"]})
        ws = _render_and_load(table, tmp_path)
        be = _body_end(table)
        cell = ws.cell(row=be + 2, column=1)
        assert cell.value == "note"
        assert cell.border.top.style == "thin"
        assert cell.font.italic is True
        assert cell.font.size == 10

    def test_multiple_footnotes_in_order(self, tmp_path: pathlib.Path):
        table = _table_with_meta_at_top(
            {"footnotes": ["fn1", "fn2", "fn3"]}
        )
        ws = _render_and_load(table, tmp_path)
        be = _body_end(table)
        assert ws.cell(row=be + 2, column=1).value == "fn1"
        assert ws.cell(row=be + 3, column=1).value == "fn2"
        assert ws.cell(row=be + 4, column=1).value == "fn3"

    def test_only_first_footnote_has_top_border_when_no_source(
        self, tmp_path: pathlib.Path
    ):
        table = _table_with_meta_at_top(
            {"footnotes": ["fn1", "fn2", "fn3"]}
        )
        ws = _render_and_load(table, tmp_path)
        be = _body_end(table)
        assert ws.cell(row=be + 2, column=1).border.top.style == "thin"
        assert ws.cell(row=be + 3, column=1).border.top.style is None
        assert ws.cell(row=be + 4, column=1).border.top.style is None


class TestTfootSourceAndFootnotes:
    """Both present: source first (with top border), then footnotes
    (no top border on any)."""

    def setup_method(self):
        self.table = _table_with_meta_at_top(
            {"source": "src", "footnotes": ["fn1", "fn2"]}
        )

    def test_order_source_then_footnotes(self, tmp_path: pathlib.Path):
        ws = _render_and_load(self.table, tmp_path)
        be = _body_end(self.table)
        assert ws.cell(row=be + 2, column=1).value == "Source: src"
        assert ws.cell(row=be + 3, column=1).value == "fn1"
        assert ws.cell(row=be + 4, column=1).value == "fn2"

    def test_only_source_row_has_top_border(self, tmp_path: pathlib.Path):
        ws = _render_and_load(self.table, tmp_path)
        be = _body_end(self.table)
        assert ws.cell(row=be + 2, column=1).border.top.style == "thin"
        assert ws.cell(row=be + 3, column=1).border.top.style is None
        assert ws.cell(row=be + 4, column=1).border.top.style is None

    def test_all_footer_rows_share_italic_and_size(
        self, tmp_path: pathlib.Path
    ):
        ws = _render_and_load(self.table, tmp_path)
        be = _body_end(self.table)
        for r in (be + 2, be + 3, be + 4):
            cell = ws.cell(row=r, column=1)
            assert cell.font.italic is True
            assert cell.font.size == 10
            assert cell.alignment.wrap_text is True


class TestTfootIntegrationExample5:
    """End-to-end: example_5_customized has title + source + one footnote."""

    def test_full_layout_resolves(self, tmp_path: pathlib.Path):
        table = example_5_customized()
        ws = _render_and_load(table, tmp_path)

        # Title at row 1.
        assert ws.cell(row=1, column=1).value == "Net Revenue by Region"

        # Source + footnote at expected positions.
        be = _body_end(table)
        assert ws.cell(row=be + 2, column=1).value == \
            "Source: internal CRM, 2026-Q1"
        assert ws.cell(row=be + 3, column=1).value == \
            "All figures USD. Excludes returns."

        # Source carries the top border; footnote does not.
        assert ws.cell(row=be + 2, column=1).border.top.style == "thin"
        assert ws.cell(row=be + 3, column=1).border.top.style is None


# ---------------------------------------------------------------------------
# E5 — default theme: Font / Border / Alignment per role + modifiers.
#
# openpyxl returns None for borders that were never explicitly set on a
# cell (vs. a Side(style=None) that was). _border_style normalizes both
# to None so test assertions stay readable.
# ---------------------------------------------------------------------------


def _border_style(side) -> str | None:
    return side.style if side is not None else None


class TestColHeaderStyling:
    """Column header cells: bold + centered + thin bottom border."""

    @pytest.mark.parametrize(
        "fixture",
        [
            example_1_one_way_freq,
            example_1b_two_way_freq,
            example_2_tabulate_v01,
            example_5_customized,
        ],
    )
    def test_all_header_cells_bold_centered_bottom_thin(
        self, fixture, tmp_path: pathlib.Path
    ):
        table = fixture()
        ws = _render_and_load(table, tmp_path)
        _, H, hs = _layout_for(table)
        n_col_leaves = len(table.col_axis.leaves())
        for r in range(hs, hs + H):
            for c in range(2, 2 + n_col_leaves):
                cell = ws.cell(row=r, column=c)
                if cell.value is None:
                    continue  # merged-in cell with no top-left value
                assert cell.font.bold is True, f"{cell.coordinate} not bold"
                assert cell.alignment.horizontal == "center", (
                    f"{cell.coordinate} not centered"
                )
                assert _border_style(cell.border.bottom) == "thin", (
                    f"{cell.coordinate} missing thin bottom border"
                )


class TestTotalColLeftEdge:
    """Cells in the LEFT EDGE column of a Total col group get medium left
    border; other cells in the same group do not."""

    def test_outer_total_header_gets_left_border(
        self, tmp_path: pathlib.Path
    ):
        # example_1b_two_way_freq: 3 product_line groups × 4 stats = 12 leaves.
        # Total group starts at col J (column index 10). Outer header row.
        table = example_1b_two_way_freq()
        ws = _render_and_load(table, tmp_path)
        _, _, hs = _layout_for(table)
        cell = ws.cell(row=hs, column=10)
        assert cell.value == "Total"
        assert _border_style(cell.border.left) == "medium"

    def test_inner_header_leftmost_within_total_gets_left_border(
        self, tmp_path: pathlib.Path
    ):
        table = example_1b_two_way_freq()
        ws = _render_and_load(table, tmp_path)
        _, _, hs = _layout_for(table)
        # Inner header row (hs + 1). Leftmost stat within Total: col J.
        leftmost = ws.cell(row=hs + 1, column=10)
        assert _border_style(leftmost.border.left) == "medium"

    def test_inner_headers_not_leftmost_within_total_have_no_left_border(
        self, tmp_path: pathlib.Path
    ):
        table = example_1b_two_way_freq()
        ws = _render_and_load(table, tmp_path)
        _, _, hs = _layout_for(table)
        # Inner row, K/L/M (cols 11/12/13) inside Total group — no border.
        for c in (11, 12, 13):
            inner = ws.cell(row=hs + 1, column=c)
            assert _border_style(inner.border.left) is None, (
                f"col {c} should NOT have a left border"
            )

    def test_body_leftmost_total_col_cells_get_left_border(
        self, tmp_path: pathlib.Path
    ):
        # Every body row's col J (leftmost of Total group) gets medium left.
        table = example_1b_two_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        for r in range(bs, bs + len(table.row_axis.leaves())):
            cell = ws.cell(row=r, column=10)
            assert _border_style(cell.border.left) == "medium", (
                f"row {r} col J should have left border"
            )

    def test_body_non_leftmost_total_col_cells_have_no_left_border(
        self, tmp_path: pathlib.Path
    ):
        table = example_1b_two_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        for r in range(bs, bs + len(table.row_axis.leaves())):
            for c in (11, 12, 13):
                cell = ws.cell(row=r, column=c)
                assert _border_style(cell.border.left) is None, (
                    f"row {r} col {c} should NOT have left border"
                )


class TestTotalRowStyling:
    """Total ROW cells: bold + medium top border. Subtotal row: italic."""

    def test_total_row_cells_bold_with_medium_top_border(
        self, tmp_path: pathlib.Path
    ):
        # example_1_one_way_freq: last leaf is Total row.
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        total_row = bs + 4  # 4 data leaves before total
        for c in range(2, 6):
            cell = ws.cell(row=total_row, column=c)
            assert cell.font.bold is True, f"col {c} not bold in total row"
            assert _border_style(cell.border.top) == "medium", (
                f"col {c} missing medium top border in total row"
            )

    def test_data_row_cells_not_bold_no_thick_top_border(
        self, tmp_path: pathlib.Path
    ):
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # First data row (West) at body_start.
        for c in range(2, 6):
            cell = ws.cell(row=bs, column=c)
            assert cell.font.bold is False
            # No medium top border (might have a None or another style,
            # but explicitly not "medium").
            assert _border_style(cell.border.top) != "medium"

    def test_subtotal_row_cells_italic(self, tmp_path: pathlib.Path):
        # example_2_tabulate_v01: row labels include "E Subtotal", "W Subtotal".
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # "E Subtotal" is at index 3 in the leaf-and-group sequence:
        # E (group), A, B, E Subtotal → rows bs..bs+3.
        sub_row = bs + 3
        assert ws.cell(row=sub_row, column=1).value == "E Subtotal"
        for c in range(1, 11):
            cell = ws.cell(row=sub_row, column=c)
            if cell.value is None:
                continue
            assert cell.font.italic is True, f"col {c} not italic in subtotal row"

    def test_grand_total_cell_gets_bold_top_and_left_borders(
        self, tmp_path: pathlib.Path
    ):
        # example_2_tabulate_v01 grand total row × Total col (col H=8).
        # The grand-total intersection cell stacks ALL three modifiers:
        # in_total_row (bold + top) + in_total_col (left).
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        grand_total_row = bs + 8  # 2 groups + 4 leaves + 2 subtotals + 1 GT
        assert ws.cell(row=grand_total_row, column=1).value == "Grand Total"
        # Leftmost of Total quarter group is col H (column index 8).
        gt_cell = ws.cell(row=grand_total_row, column=8)
        assert gt_cell.font.bold is True
        assert _border_style(gt_cell.border.top) == "medium"
        assert _border_style(gt_cell.border.left) == "medium"


class TestRowLabelStyling:
    """Row labels (column A): left-aligned + indent per depth. Total
    rows bold, subtotal rows italic."""

    def test_row_label_left_aligned(self, tmp_path: pathlib.Path):
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        for r in range(bs, bs + 5):
            assert ws.cell(row=r, column=1).alignment.horizontal == "left"

    def test_row_label_indent_for_depth_2(self, tmp_path: pathlib.Path):
        # example_2_tabulate_v01 row tree: depth 1 (region E/W groups),
        # depth 2 (product A/B leaves + subtotals + grand total). Leaves
        # at depth 2 should get indent=1.
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # E (depth 1) → indent 0
        assert ws.cell(row=bs, column=1).alignment.indent == 0
        # E's A leaf (depth 2) → indent 1
        assert ws.cell(row=bs + 1, column=1).alignment.indent == 1
        # E Subtotal (depth 2) → indent 1
        assert ws.cell(row=bs + 3, column=1).alignment.indent == 1

    def test_total_row_label_bold(self, tmp_path: pathlib.Path):
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        total_label = ws.cell(row=bs + 4, column=1)
        assert total_label.value == "Total"
        assert total_label.font.bold is True

    def test_subtotal_row_label_italic(self, tmp_path: pathlib.Path):
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        sub_label = ws.cell(row=bs + 3, column=1)
        assert sub_label.value == "E Subtotal"
        assert sub_label.font.italic is True

    def test_data_row_label_neither_bold_nor_italic(
        self, tmp_path: pathlib.Path
    ):
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # West row label
        cell = ws.cell(row=bs, column=1)
        assert cell.font.bold is False
        assert cell.font.italic is False


class TestStyleRegistry:
    """Sanity checks on the source-of-truth dict + composer."""

    def test_registry_has_expected_keys(self):
        from proctab.render.excel import _STYLE_REGISTRY
        expected = {
            "col_header", "row_label", "body_cell",
            "in_subtotal_row", "in_total_row", "in_total_col",
        }
        assert set(_STYLE_REGISTRY.keys()) == expected

    def test_compose_stacks_subtotal_and_total_col_modifiers(
        self, tmp_path: pathlib.Path
    ):
        # A cell that's BOTH in a subtotal row AND in the total col gets
        # italic (subtotal) AND left medium border (total-col).
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        bs = _body_start(table)
        # E Subtotal row × Total col leftmost (col H=8).
        sub_row = bs + 3
        cell = ws.cell(row=sub_row, column=8)
        assert cell.font.italic is True
        assert _border_style(cell.border.left) == "medium"
        # Not bold (subtotal, not total).
        assert cell.font.bold is False


class TestTotalColLeftEdgesHelper:
    """Unit test for the helper that computes total-col left-edge columns."""

    def test_no_total_in_col_axis_returns_empty(self):
        from proctab.render.excel import _total_col_left_edges
        # example_1_one_way_freq: col axis has only _stat dim with 4 data
        # leaves; no total at col level.
        assert _total_col_left_edges(
            example_1_one_way_freq().col_axis
        ) == set()

    def test_one_total_group_marks_first_leaf_col(self):
        from proctab.render.excel import _total_col_left_edges
        # example_1b_two_way_freq: 3 product groups × 4 stats; Total at
        # position J = col 10.
        assert _total_col_left_edges(
            example_1b_two_way_freq().col_axis
        ) == {10}

    def test_empty_col_axis_returns_empty(self):
        from proctab.model import Axis, Dimension, Node
        from proctab.render.excel import _total_col_left_edges
        empty_dim = Dimension(name="c", kind="category", categories=())
        empty_tree = Node(path=(), depth=0, span=0, role="data", children=())
        empty_axis = Axis(dims=(empty_dim,), tree=empty_tree)
        assert _total_col_left_edges(empty_axis) == set()


# ---------------------------------------------------------------------------
# E6 — frozen pane + column widths.
# ---------------------------------------------------------------------------


def _freeze_pane(ws):
    """Normalize openpyxl's freeze_panes accessor (may be Cell or str)."""
    fp = ws.freeze_panes
    if fp is None:
        return None
    return str(fp)


class TestFreezePane:
    """`ws.freeze_panes = f"B{body_start}"` — freezes title + headers
    + the row-label column."""

    @pytest.mark.parametrize(
        "fixture,expected_anchor",
        [
            # title present (header_start=3), H=1 → body_start=4
            (example_1_one_way_freq, "B4"),
            # title present, H=2 → body_start=5
            (example_1b_two_way_freq, "B5"),
            # no title (header_start=1), H=3 → body_start=4
            (example_2_tabulate_v01, "B4"),
            # title present, H=1 → body_start=4
            (example_5_customized, "B4"),
        ],
    )
    def test_freeze_anchor_matches_body_start(
        self, fixture, expected_anchor, tmp_path: pathlib.Path
    ):
        ws = _render_and_load(fixture(), tmp_path)
        assert _freeze_pane(ws) == expected_anchor


class TestColumnAWidth:
    """Column A width: longest row label (+indent contribution +padding),
    floored at 8, capped at 40."""

    def test_minimum_width_for_short_labels(
        self, tmp_path: pathlib.Path
    ):
        # example_1_one_way_freq: labels are short ("West", "Total", etc.)
        # → falls to minimum 8.
        table = example_1_one_way_freq()
        ws = _render_and_load(table, tmp_path)
        assert ws.column_dimensions["A"].width == 8.0

    def test_width_scales_with_indented_labels(
        self, tmp_path: pathlib.Path
    ):
        # example_2_tabulate_v01: longest indented label is
        # "Grand Total" (11 chars) at depth 2 → indent 1 ×3 = 3 visual
        # → +2 padding → 16.
        table = example_2_tabulate_v01()
        ws = _render_and_load(table, tmp_path)
        assert ws.column_dimensions["A"].width == 16.0

    def test_width_capped_at_40(self, tmp_path: pathlib.Path):
        # Build a Table with a very long row label.
        from proctab.model import Axis, Category, Dimension, Node, Table
        long_label = "x" * 80
        cat = Category(long_label)
        row_dim = Dimension(name="r", kind="category", categories=(cat,))
        row_leaf = Node(path=(cat,), depth=1, span=1, role="data")
        row_tree = Node(
            path=(), depth=0, span=1, role="data", children=(row_leaf,)
        )
        col_cat = Category("x")
        col_dim = Dimension(name="c", kind="category", categories=(col_cat,))
        col_leaf = Node(path=(col_cat,), depth=1, span=1, role="data")
        col_tree = Node(
            path=(), depth=0, span=1, role="data", children=(col_leaf,)
        )
        table = Table(
            row_axis=Axis(dims=(row_dim,), tree=row_tree),
            col_axis=Axis(dims=(col_dim,), tree=col_tree),
            body=np.array([[1.0]], dtype=np.float64),
            missing=np.array([[0]], dtype=np.uint8),
            value_kinds=("raw",),
            formats=(None,),
        )
        ws = _render_and_load(table, tmp_path)
        assert ws.column_dimensions["A"].width == 40.0

    def test_width_for_empty_row_axis_uses_default(
        self, tmp_path: pathlib.Path
    ):
        # Synthesize a 0-row Table (no row leaves) — _col_a_width
        # falls back to _BODY_COL_DEFAULT_WIDTH (12).
        from proctab.model import Axis, Category, Dimension, Node, Table
        empty_row_dim = Dimension(
            name="r", kind="category", categories=()
        )
        empty_row_tree = Node(
            path=(), depth=0, span=0, role="data", children=()
        )
        col_cat = Category("x")
        col_dim = Dimension(
            name="c", kind="category", categories=(col_cat,)
        )
        col_leaf = Node(path=(col_cat,), depth=1, span=1, role="data")
        col_tree = Node(
            path=(), depth=0, span=1, role="data", children=(col_leaf,)
        )
        table = Table(
            row_axis=Axis(dims=(empty_row_dim,), tree=empty_row_tree),
            col_axis=Axis(dims=(col_dim,), tree=col_tree),
            body=np.empty((0, 1), dtype=np.float64),
            missing=np.empty((0, 1), dtype=np.uint8),
            value_kinds=("raw",),
            formats=(None,),
        )
        ws = _render_and_load(table, tmp_path)
        assert ws.column_dimensions["A"].width == 12.0


class TestBodyColumnWidths:
    """All body columns (B through last_body_col) get the fixed
    default width."""

    @pytest.mark.parametrize(
        "fixture",
        [
            example_1_one_way_freq,
            example_1b_two_way_freq,
            example_2_tabulate_v01,
            example_5_customized,
        ],
    )
    def test_every_body_col_width_is_12(
        self, fixture, tmp_path: pathlib.Path
    ):
        openpyxl = pytest.importorskip("openpyxl")
        table = fixture()
        ws = _render_and_load(table, tmp_path)
        n_col_leaves = len(table.col_axis.leaves())
        for j in range(n_col_leaves):
            letter = openpyxl.utils.get_column_letter(2 + j)
            assert ws.column_dimensions[letter].width == 12.0


class TestEmptyTableE6:
    """E6 helpers don't crash on empty Tables."""

    def _empty_axis_table(self):
        from proctab.model import Axis, Category, Dimension, Node, Table
        row_dim = Dimension(
            name="region", kind="category", categories=(Category("W"),)
        )
        row_leaf = Node(
            path=(Category("W"),), depth=1, span=1, role="data"
        )
        row_tree = Node(
            path=(), depth=0, span=1, role="data", children=(row_leaf,)
        )
        empty_col_dim = Dimension(
            name="c", kind="category", categories=()
        )
        empty_col_tree = Node(
            path=(), depth=0, span=0, role="data", children=()
        )
        return Table(
            row_axis=Axis(dims=(row_dim,), tree=row_tree),
            col_axis=Axis(dims=(empty_col_dim,), tree=empty_col_tree),
            body=np.empty((1, 0), dtype=np.float64),
            missing=np.empty((1, 0), dtype=np.uint8),
            value_kinds=(),
            formats=(),
        )

    def test_freeze_pane_set_even_when_empty(
        self, tmp_path: pathlib.Path
    ):
        ws = _render_and_load(self._empty_axis_table(), tmp_path)
        # With H=1 and no title: body_start = 1 + 1 = 2
        assert _freeze_pane(ws) == "B2"

    def test_column_a_still_sized_when_body_empty(
        self, tmp_path: pathlib.Path
    ):
        ws = _render_and_load(self._empty_axis_table(), tmp_path)
        # Row "W" exists in the row axis even though col axis is empty;
        # _col_a_width still computes from it. Min floor of 8 applies.
        assert ws.column_dimensions["A"].width == 8.0


# ---------------------------------------------------------------------------
# E7 — Table.to_excel method wiring.
#
# The render_excel function-level path is exhaustively tested above;
# these tests focus on the method binding: that to_excel delegates
# correctly and that the method preserves render_excel's documented
# error contracts (ValueError for bad sheet names; friendly ImportError
# when openpyxl is missing).
# ---------------------------------------------------------------------------


class TestTableToExcel:
    def test_returns_none(self, tmp_path: pathlib.Path):
        openpyxl = pytest.importorskip("openpyxl")
        out = example_5_customized().to_excel(tmp_path / "out.xlsx")
        assert out is None

    def test_writes_file_at_path(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        path = tmp_path / "out.xlsx"
        example_5_customized().to_excel(path)
        assert path.exists() and path.stat().st_size > 0

    def test_matches_render_excel_output(self, tmp_path: pathlib.Path):
        # Both paths should produce the same file. The method is a
        # one-line delegate, so byte-identical output is a fair check.
        pytest.importorskip("openpyxl")
        a = tmp_path / "method.xlsx"
        b = tmp_path / "function.xlsx"
        example_5_customized().to_excel(a)
        render_excel(example_5_customized(), b)
        assert a.read_bytes() == b.read_bytes()

    def test_default_sheet_name(self, tmp_path: pathlib.Path):
        openpyxl = pytest.importorskip("openpyxl")
        path = tmp_path / "out.xlsx"
        example_5_customized().to_excel(path)
        wb = openpyxl.load_workbook(path)
        assert wb.sheetnames == ["Sheet1"]

    def test_sheet_kwarg_passes_through(self, tmp_path: pathlib.Path):
        openpyxl = pytest.importorskip("openpyxl")
        path = tmp_path / "out.xlsx"
        example_5_customized().to_excel(path, sheet="Q1 Report")
        wb = openpyxl.load_workbook(path)
        assert wb.sheetnames == ["Q1 Report"]

    def test_accepts_string_path(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        path = str(tmp_path / "out_str.xlsx")
        example_5_customized().to_excel(path)
        assert pathlib.Path(path).exists()

    def test_accepts_pathlib_path(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        path = tmp_path / "out_pl.xlsx"
        example_5_customized().to_excel(path)
        assert path.exists()

    def test_invalid_sheet_raises_value_error(self, tmp_path: pathlib.Path):
        pytest.importorskip("openpyxl")
        path = tmp_path / "should_not_exist.xlsx"
        with pytest.raises(ValueError, match="reserved"):
            example_5_customized().to_excel(path, sheet="bad/name")
        assert not path.exists()

    def test_missing_openpyxl_gives_friendly_error(
        self, tmp_path: pathlib.Path, monkeypatch
    ):
        # Mirror the function-level monkeypatch from TestMissingOpenpyxlError.
        for name in list(sys.modules):
            if name == "openpyxl" or name.startswith("openpyxl."):
                monkeypatch.setitem(sys.modules, name, None)

        original_import = builtins.__import__

        def _no_openpyxl(name, *args, **kwargs):
            if name == "openpyxl" or name.startswith("openpyxl."):
                raise ImportError(f"simulated absent: {name}")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_openpyxl)

        with pytest.raises(ImportError, match=r"proctab\[excel\]"):
            example_5_customized().to_excel(tmp_path / "missing.xlsx")
