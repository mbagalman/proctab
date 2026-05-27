"""HTML renderer for proctab Tables.

v0.1: single default theme, two output modes (fragment / standalone).
See docs/HTML_RENDERER.md for the locked design memo.

Current state: H1 (format resolver) + H2 (column header rendering).
H3-H7 will add body rendering, caption/tfoot, default styling, the
standalone wrapper, and the `Table._repr_html_` / `Table.to_html`
method wiring.
"""

from __future__ import annotations

import html as _html

import numpy as np

from proctab.model import (
    Axis,
    Category,
    Node,
    SubtotalMarker,
    Table,
    TotalMarker,
    ValueKind,
)


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


def _nodes_at_depth(root: Node, depth: int) -> list[Node]:
    if root.depth == depth:
        return [root]
    if root.children is None:
        return []
    out: list[Node] = []
    for child in root.children:
        out.extend(_nodes_at_depth(child, depth))
    return out


def _col_header_label(node: Node) -> str:
    if node.label is not None:
        return node.label
    if not node.path:
        return ""
    el = node.path[-1]
    if isinstance(el, Category):
        return str(el.label if el.label is not None else el.value)
    if isinstance(el, TotalMarker):
        return "Total"
    if isinstance(el, SubtotalMarker):
        return f"{el.at_dim} Subtotal"
    return ""


def _col_header_class(node: Node) -> str:
    if node.role == "total":
        return "proctab-col-total"
    if node.role == "subtotal":
        return "proctab-col-subtotal"
    return "proctab-col-data"


def _corner_th(n_header_rows: int) -> str:
    rowspan = f' rowspan="{n_header_rows}"' if n_header_rows > 1 else ""
    return f'<th{rowspan} class="proctab-corner" aria-hidden="true"></th>'


def _col_th(node: Node, *, is_innermost: bool) -> str:
    text = _html.escape(_col_header_label(node))
    scope = "col" if is_innermost else "colgroup"
    colspan = f' colspan="{node.span}"' if node.span > 1 else ""
    cls = _col_header_class(node)
    return f'<th{colspan} scope="{scope}" class="{cls}">{text}</th>'


def _render_thead(col_axis: Axis) -> str:
    """Emit the `<thead>...</thead>` for a Table.

    One `<tr>` per col-axis dim depth. The top-left corner cell in the
    first `<tr>` spans all header rows. Interior nodes carry
    `scope="colgroup"`; innermost-depth leaves carry `scope="col"`.
    Per-node class encodes role (`proctab-col-data` /
    `-subtotal` / `-total`).
    """
    dims = col_axis.dims
    n_header_rows = max(len(dims), 1)

    rows: list[str] = []
    for d in range(1, len(dims) + 1):
        is_innermost = d == len(dims)
        cells: list[str] = []
        if d == 1:
            cells.append(_corner_th(n_header_rows))
        for node in _nodes_at_depth(col_axis.tree, d):
            cells.append(_col_th(node, is_innermost=is_innermost))
        body = "".join(f"      {c}\n" for c in cells)
        rows.append(f"    <tr>\n{body}    </tr>")

    if not rows:
        rows.append(f"    <tr>\n      {_corner_th(1)}\n    </tr>")

    inner = "\n".join(rows)
    return f"  <thead>\n{inner}\n  </thead>"


def render_html(table: Table, *, standalone: bool = False) -> str:
    """Render a Table to an HTML string.

    Current state: emits `<table class="proctab">` with a `<thead>` of
    column headers per H2; the `<tbody>`, `<caption>`, `<tfoot>`, and
    default styling land in H3-H6. `standalone=True` wrapping lands in H6.
    """
    _ = standalone  # H6 will branch on this; the body is the same for now.
    thead = _render_thead(table.col_axis)
    return f'<table class="proctab">\n{thead}\n</table>'
