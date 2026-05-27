"""Excel (.xlsx) renderer for proctab Tables.

v0.1: single default theme, single sheet, written to a path on disk via
openpyxl. See docs/EXCEL_RENDERER.md for the locked design memo.

Current state: E1 (module skeleton + format-resolution helper +
sheet-name validator). E2-E7 add column headers, body, caption/source/
footnote, default styling, frozen pane / widths, and the Table method
wiring. openpyxl is an optional extra — install via
`pip install proctab[excel]`. The function-level entry point and the
Table method both lazy-import openpyxl, so `import proctab` works in
environments without it.
"""

from __future__ import annotations

import os

from proctab.model import Table, ValueKind


# ---------------------------------------------------------------------------
# Format resolution (per docs/EXCEL_RENDERER.md#number-format-resolution).
# ---------------------------------------------------------------------------


_FORMAT_TRANSLATIONS: dict[str, str] = {
    # Integer-like (thousands separator)
    "{:,d}":    "#,##0",
    "{:,.0f}":  "#,##0",
    "{:,.1f}":  "#,##0.0",
    "{:,.2f}":  "#,##0.00",
    "{:,.4f}":  "#,##0.0000",
    # Currency
    "${:,.0f}": "$#,##0",
    "${:,.2f}": "$#,##0.00",
    # Percent — 0-1 scale
    "{:.1%}":   "0.0%",
    "{:.2%}":   "0.00%",
    # Percent — 0-100 scale (literal "%" suffix; freq() flow)
    "{:.1f}%":  '0.0"%"',
    "{:.2f}%":  '0.00"%"',
    # Plain decimals
    "{:.0f}":   "0",
    "{:.1f}":   "0.0",
    "{:.2f}":   "0.00",
    "{:.3f}":   "0.000",
    # General
    "{:g}":     "General",
}
"""Known Python format string → Excel format code translations. Covers
every format `freq()` and `tabulate()` emit today plus the common
hand-written patterns from `examples.py`. Unknown formats fall through
to the per-`value_kind` default."""


_KIND_DEFAULTS: dict[str, str] = {
    "count":         "#,##0",
    "currency":      "$#,##0.00",
    "percent":       "0.0%",            # assumes 0-1 scale
    "ratio":         "0.000",
    "sum":           "#,##0",
    "mean":          "#,##0.00",
    "weighted_mean": "#,##0.00",
    "median":        "#,##0.00",
    "raw":           "General",
}
"""Fallback Excel format codes keyed by `value_kind` (parallel to the
HTML renderer's `_KIND_DEFAULTS`). Used when `formats[j]` is None or
not in the translation table above."""


_GENERAL = "General"


def _resolve_excel_format(fmt: str | None, value_kind: ValueKind) -> str:
    """Resolve the Excel number format code for a single cell.

    Priority (locked in docs/EXCEL_RENDERER.md#number-format-resolution):
      1. Explicit `fmt` translates via `_FORMAT_TRANSLATIONS` when known.
      2. Per-`value_kind` default from `_KIND_DEFAULTS`.
      3. `"General"` final fallback for unknown kinds.
    """
    if fmt is not None and fmt in _FORMAT_TRANSLATIONS:
        return _FORMAT_TRANSLATIONS[fmt]
    return _KIND_DEFAULTS.get(value_kind, _GENERAL)


# ---------------------------------------------------------------------------
# Sheet-name validation (per docs/EXCEL_RENDERER.md, "Frozen pane, column
# widths, sheet name" section).
# ---------------------------------------------------------------------------


_INVALID_SHEET_CHARS = frozenset("\\/?*[]:")
_MAX_SHEET_NAME_LENGTH = 31


def _validate_sheet_name(name: str) -> None:
    """Raise `ValueError` if `name` violates Excel's sheet-name rules.

    Rules: 1-31 characters; must not contain any of `\\ / ? * [ ] :`.
    No silent sanitization — a loud failure beats writing a workbook
    with a corrupted sheet name.
    """
    if not isinstance(name, str):
        raise TypeError(
            f"sheet name must be a string; got {type(name).__name__}."
        )
    if len(name) < 1:
        raise ValueError("sheet name must be at least 1 character.")
    if len(name) > _MAX_SHEET_NAME_LENGTH:
        raise ValueError(
            f"sheet name must be at most {_MAX_SHEET_NAME_LENGTH} "
            f"characters; got {len(name)} ({name!r})."
        )
    bad = sorted(set(name) & _INVALID_SHEET_CHARS)
    if bad:
        raise ValueError(
            f"sheet name contains characters reserved by Excel: {bad}. "
            f"Reserved set: {sorted(_INVALID_SHEET_CHARS)}. "
            f"Rename the sheet or pre-sanitize the string before "
            f"passing it to to_excel()."
        )


# ---------------------------------------------------------------------------
# Top-level entry point.
# ---------------------------------------------------------------------------


def render_excel(
    table: Table,
    path: str | os.PathLike[str],
    *,
    sheet: str = "Sheet1",
) -> None:
    """Render a `Table` to an `.xlsx` file at `path`.

    Current state: E1 stub — opens a workbook, sets the sheet name,
    and saves. E2-E6 add column headers, body, caption/source/footnote,
    default styling, frozen pane, and column widths.

    `sheet` becomes the worksheet name; must satisfy Excel's rules
    (1-31 characters, no `\\ / ? * [ ] :`). Violations raise
    `ValueError` with a clear message — no silent sanitization.

    Raises `ImportError` with an actionable message if openpyxl is
    not installed (install via `pip install proctab[excel]`).
    """
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise ImportError(
            "Excel export requires openpyxl. Install with "
            "`pip install proctab[excel]`."
        ) from exc

    _validate_sheet_name(sheet)
    _ = table  # E2-E6 will consume the table to fill in cell content.

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    wb.save(path)
