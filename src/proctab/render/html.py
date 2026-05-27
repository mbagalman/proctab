"""HTML renderer for proctab Tables.

v0.1: single default theme, two output modes (fragment / standalone).
See docs/HTML_RENDERER.md for the locked design memo.

Current state: H1 (format resolver) + H2 (column headers) + H3 (body)
+ H4 (caption + tfoot). H5-H7 will add default styling, the standalone
wrapper, and the `Table._repr_html_` / `Table.to_html` method wiring.
"""

from __future__ import annotations

import html as _html
import math

import numpy as np

from proctab.model import (
    Axis,
    Category,
    MissingReason,
    Node,
    SubtotalMarker,
    Table,
    TotalMarker,
    ValueKind,
)


# ---------------------------------------------------------------------------
# H1 — Format resolver.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Shared tree-walking + label helpers.
# ---------------------------------------------------------------------------


def _nodes_at_depth(root: Node, depth: int) -> list[Node]:
    if root.depth == depth:
        return [root]
    if root.children is None:
        return []
    out: list[Node] = []
    for child in root.children:
        out.extend(_nodes_at_depth(child, depth))
    return out


def _walk_nonroot(node: Node):
    if node.depth > 0:
        yield node
    if node.children is not None:
        for child in node.children:
            yield from _walk_nonroot(child)


def _node_label(node: Node) -> str:
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


# ---------------------------------------------------------------------------
# H2 — Column header rendering.
# ---------------------------------------------------------------------------


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
    text = _html.escape(_node_label(node))
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


# ---------------------------------------------------------------------------
# H3 — Body rendering.
# ---------------------------------------------------------------------------


_ROLE_RANK = {"data": 0, "subtotal": 1, "total": 2}

_MISSING_SUFFIX: dict[int, str] = {
    int(MissingReason.EMPTY): "empty",
    int(MissingReason.NOT_APPLICABLE): "not-applicable",
    int(MissingReason.SUPPRESSED): "suppressed",
    int(MissingReason.NULL): "null",
}

_MISSING_TEXT: dict[int, str] = {
    int(MissingReason.EMPTY): "",
    int(MissingReason.NOT_APPLICABLE): "—",  # em dash
    int(MissingReason.SUPPRESSED): "***",
    int(MissingReason.NULL): "·",  # middle dot
}


def _cell_role(row_role: str, col_role: str) -> str:
    """Cell role per the memo: total > subtotal > data.

    "Any total-leaf cell is a total cell" — a cell sitting in either a
    total row or a total column carries the total role. Subtotal-anywhere
    similarly trumps data. Equal roles return that role.
    """
    if _ROLE_RANK[row_role] >= _ROLE_RANK[col_role]:
        return row_role
    return col_role


def _data_value_attr(value: object) -> str:
    """Format the `data-value` attribute for a finite-PRESENT cell.

    Returns the attribute fragment (` data-value="..."`) or `""` when
    the value is non-finite (NaN, +/-inf) — per the memo, non-finite
    PRESENT cells skip data-value entirely.
    """
    v = float(value)
    if not math.isfinite(v):
        return ""
    raw = format(v, ".17g")
    return f' data-value="{_html.escape(raw, quote=True)}"'


def _render_td(
    value: object,
    missing_code: int,
    fmt: str | None,
    value_kind: ValueKind,
    cell_role: str,
) -> str:
    classes = ["proctab-cell", f"proctab-{cell_role}"]

    if missing_code == int(MissingReason.PRESENT):
        text = _html.escape(_resolve_format(value, fmt, value_kind))
        dv = _data_value_attr(value)
        cls = " ".join(classes)
        return f'<td class="{cls}"{dv}>{text}</td>'

    suffix = _MISSING_SUFFIX[missing_code]
    text = _html.escape(_MISSING_TEXT[missing_code])
    classes.append(f"proctab-missing-{suffix}")
    cls = " ".join(classes)
    return f'<td class="{cls}">{text}</td>'


def _row_label_th(node: Node, *, scope: str) -> str:
    indent = max(node.depth - 1, 0)
    cls = f"proctab-row-label proctab-indent-{indent}"
    text = _html.escape(_node_label(node))
    return f'<th scope="{scope}" class="{cls}">{text}</th>'


def _render_leaf_row(
    row_leaf: Node,
    row_idx: int,
    col_leaves: list[Node],
    table: Table,
) -> str:
    cells: list[str] = [_row_label_th(row_leaf, scope="row")]
    for j, col_leaf in enumerate(col_leaves):
        cell_role = _cell_role(row_leaf.role, col_leaf.role)
        cells.append(
            _render_td(
                table.body[row_idx, j],
                int(table.missing[row_idx, j]),
                table.formats[j],
                table.value_kinds[j],
                cell_role,
            )
        )
    body = "".join(f"      {c}\n" for c in cells)
    return f'    <tr class="proctab-{row_leaf.role}">\n{body}    </tr>'


def _render_group_row(node: Node, n_col_leaves: int) -> str:
    label_th = _row_label_th(node, scope="rowgroup")
    if n_col_leaves > 0:
        pad = f'<td colspan="{n_col_leaves}" class="proctab-group-pad"></td>'
    else:
        pad = ""
    pad_line = f"      {pad}\n" if pad else ""
    return (
        f'    <tr class="proctab-group-header">\n'
        f"      {label_th}\n"
        f"{pad_line}"
        f"    </tr>"
    )


def _render_tbody(table: Table) -> str:
    col_leaves = table.col_axis.leaves()
    n_col_leaves = len(col_leaves)

    rows: list[str] = []
    leaf_idx = 0
    for node in _walk_nonroot(table.row_axis.tree):
        if node.children is None:
            rows.append(_render_leaf_row(node, leaf_idx, col_leaves, table))
            leaf_idx += 1
        else:
            rows.append(_render_group_row(node, n_col_leaves))

    if not rows:
        return "  <tbody></tbody>"
    inner = "\n".join(rows)
    return f"  <tbody>\n{inner}\n  </tbody>"


# ---------------------------------------------------------------------------
# H4 — Caption + tfoot.
# ---------------------------------------------------------------------------


def _render_caption(meta: dict | None) -> str:
    if not meta:
        return ""
    title = meta.get("title")
    if not title:
        return ""
    return (
        f'  <caption class="proctab-caption">'
        f"{_html.escape(str(title))}"
        f"</caption>"
    )


def _render_tfoot(meta: dict | None, n_total_cols: int) -> str:
    """Emit `<tfoot>` with source + footnote rows when meta supplies them.

    Order matches the locked schematic in docs/HTML_RENDERER.md: a single
    source row (prefixed "Source: ") followed by one footnote row per
    footnote. `<tfoot>` is omitted entirely when neither key is present.
    """
    if not meta:
        return ""
    source = meta.get("source")
    footnotes = meta.get("footnotes") or []
    if not source and not footnotes:
        return ""

    rows: list[str] = []
    if source:
        text = _html.escape(f"Source: {source}")
        rows.append(
            f'    <tr class="proctab-source">\n'
            f'      <td colspan="{n_total_cols}">{text}</td>\n'
            f"    </tr>"
        )
    for fn in footnotes:
        text = _html.escape(str(fn))
        rows.append(
            f'    <tr class="proctab-footnote">\n'
            f'      <td colspan="{n_total_cols}">{text}</td>\n'
            f"    </tr>"
        )
    inner = "\n".join(rows)
    return f"  <tfoot>\n{inner}\n  </tfoot>"


# ---------------------------------------------------------------------------
# Top-level entry point.
# ---------------------------------------------------------------------------


def render_html(table: Table, *, standalone: bool = False) -> str:
    """Render a Table to an HTML string.

    Current state: emits `<table class="proctab">` with optional
    `<caption>` (H4), `<thead>` (H2), `<tbody>` (H3), and optional
    `<tfoot>` (H4). Default styling lands in H5, the standalone wrapper
    in H6, and the `Table._repr_html_` / `Table.to_html` hooks in H7.
    """
    _ = standalone  # H6 will branch on this; the body is the same for now.
    n_total_cols = 1 + len(table.col_axis.leaves())
    caption = _render_caption(table.meta)
    thead = _render_thead(table.col_axis)
    tbody = _render_tbody(table)
    tfoot = _render_tfoot(table.meta, n_total_cols)

    parts: list[str] = ['<table class="proctab">']
    if caption:
        parts.append(caption)
    parts.append(thead)
    parts.append(tbody)
    if tfoot:
        parts.append(tfoot)
    parts.append("</table>")
    return "\n".join(parts)
