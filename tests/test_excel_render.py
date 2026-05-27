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

    def test_no_merged_ranges(self, tmp_path: pathlib.Path):
        # Single-dim col axis — innermost depth, each leaf is one cell.
        ws = _render_and_load(example_1_one_way_freq(), tmp_path)
        assert _merged_ranges(ws) == set()


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
        # Innermost depth → each leaf is one cell; only outer-row merges
        # exist (the 3 from the previous test).
        ws = _render_and_load(example_1b_two_way_freq(), tmp_path)
        _, _, hs = _layout_for(example_1b_two_way_freq())
        for r in _merged_ranges(ws):
            assert f":{hs}" in r or f"{hs}:" in r  # only the outer row

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
        # Title is E4; for now, rows 1 + 2 stay blank.
        assert ws.cell(row=1, column=1).value is None
        assert ws.cell(row=2, column=1).value is None
        # Headers start at row 3.
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
