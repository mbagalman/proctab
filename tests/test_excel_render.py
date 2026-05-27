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

import pytest

from proctab.render.excel import (
    _FORMAT_TRANSLATIONS,
    _KIND_DEFAULTS,
    _resolve_excel_format,
    _validate_sheet_name,
    render_excel,
)
from proctab.examples import example_1_one_way_freq


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
