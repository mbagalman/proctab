"""HTML renderer for proctab Tables.

v0.1: single default theme, two output modes (fragment / standalone).
See docs/HTML_RENDERER.md for the locked design memo.

H1 (this module's current state): skeleton + format-resolution helper.
H2-H7 will add column headers, body rendering, caption/tfoot, default
styling, the standalone wrapper, and the `Table._repr_html_` /
`Table.to_html` method wiring.
"""

from __future__ import annotations

import numpy as np

from proctab.model import Table, ValueKind


_KIND_DEFAULTS: dict[str, str] = {
    "currency": "${:,.2f}",
    "percent": "{:.1%}",
    "ratio": "{:.3f}",
    "sum": "{:,.0f}",
    "mean": "{:,.2f}",
    "weighted_mean": "{:,.2f}",
    "median": "{:,.2f}",
    "raw": "{:g}",
}


def _count_default_spec(value: object) -> str:
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return "{:,d}"
    return "{:,.0f}"


def _resolve_format(value: object, fmt: str | None, value_kind: ValueKind) -> str:
    """Resolve display text for a single PRESENT cell.

    Priority (locked in docs/HTML_RENDERER.md#format-resolution):
      1. Explicit `fmt` wins when non-None.
      2. Per-`value_kind` renderer default.
      3. `"{:g}"` final fallback for unknown kinds.

    Percent default assumes 0-1 scale (so 0.42 renders as "42.0%"); see
    the memo's "Percent storage convention" for hand-built producers
    that store 0-100.
    """
    if fmt is not None:
        return fmt.format(value)
    if value_kind == "count":
        return _count_default_spec(value).format(value)
    spec = _KIND_DEFAULTS.get(value_kind, "{:g}")
    return spec.format(value)


def render_html(table: Table, *, standalone: bool = False) -> str:
    """Render a Table to an HTML string.

    H1 stub: returns an empty `<table class="proctab"></table>`. The
    column-header, body, caption/tfoot, default styling, and
    standalone-document wrapping land in H2-H6. The `Table._repr_html_`
    and `Table.to_html` hooks land in H7.
    """
    _ = (table, standalone)
    return '<table class="proctab"></table>'
