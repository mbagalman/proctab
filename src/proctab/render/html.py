"""HTML renderer for proctab Tables.

v0.1: single default theme, two output modes (fragment / standalone).
See docs/HTML_RENDERER.md for the locked design memo.

Current state: H1 (format resolver) + H2 (column headers) + H3 (body)
+ H4 (caption + tfoot) + H5 (default theme). H6-H7 will add the
standalone document wrapper and the `Table._repr_html_` / `Table.to_html`
method wiring.
"""

from __future__ import annotations

import html as _html
import math
from typing import Callable, Iterable

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
# H5 — Default theme.
#
# Single source of truth for every CSS rule. Standalone mode (H6) reads it
# via `_build_css()`; fragment mode reads it per-element via
# `_inline_styles_for()`. The two modes render identically.
# ---------------------------------------------------------------------------


# Map of class name → CSS declarations.
# "proctab" (no dot) refers to the `<table class="proctab">` selector;
# every other key maps to the matching `.proctab-…` selector.
# Empty values mean "the class exists for structure/targeting but has
# no default visual styling in v0.1." Order is preserved so inline
# styles concatenate in a predictable cascade order.
_FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "Helvetica, Arial, sans-serif"
)

_STYLE_BY_CLASS: dict[str, str] = {
    "proctab": (
        "border-collapse: collapse; "
        f"font-family: {_FONT_STACK};"
    ),
    "proctab-caption": (
        "caption-side: top; "
        "text-align: left; "
        "font-weight: 600; "
        "padding: 0 0 8px 0;"
    ),
    # Column headers (all roles share base typography + border)
    "proctab-col-data": (
        "padding: 4px 8px; "
        "text-align: right; "
        "font-weight: 600; "
        "border-bottom: 1px solid #999;"
    ),
    "proctab-col-subtotal": (
        "padding: 4px 8px; "
        "text-align: right; "
        "font-weight: 600; "
        "font-style: italic; "
        "border-bottom: 1px solid #999;"
    ),
    "proctab-col-total": (
        "padding: 4px 8px; "
        "text-align: right; "
        "font-weight: 600; "
        "border-bottom: 1px solid #999; "
        "border-left: 2px solid #333;"
    ),
    # Top-left corner cell — purely structural.
    "proctab-corner": "",
    # Body cells (numeric)
    "proctab-cell": (
        "padding: 4px 8px; "
        "text-align: right; "
        "font-variant-numeric: tabular-nums; "
        "border-top: 1px solid #ddd;"
    ),
    # Row labels (leftmost <th> in each body row)
    "proctab-row-label": (
        "padding: 4px 8px; "
        "text-align: left; "
        "border-top: 1px solid #ddd;"
    ),
    # Indent steps for nested row hierarchies
    "proctab-indent-0": "",
    "proctab-indent-1": "padding-left: 16px;",
    "proctab-indent-2": "padding-left: 32px;",
    "proctab-indent-3": "padding-left: 48px;",
    # Group-header rows (interior row-tree nodes)
    "proctab-group-header": "font-weight: 600;",
    "proctab-group-pad": "",
    # Per-role styling (applied to both <tr> and the cells inside)
    "proctab-data": "",
    "proctab-subtotal": "font-style: italic;",
    "proctab-total": "font-weight: bold; border-top: 2px solid #333;",
    # Missing-cell variants — muted color so non-PRESENT cells fade back
    "proctab-missing-empty": "",
    "proctab-missing-null": "color: #999;",
    "proctab-missing-not-applicable": "color: #999;",
    "proctab-missing-suppressed": "color: #999;",
    # tfoot rows
    "proctab-source": (
        "padding: 8px; "
        "text-align: left; "
        "font-size: smaller; "
        "color: #555; "
        "border-top: 1px solid #999;"
    ),
    "proctab-footnote": (
        "padding: 8px; "
        "text-align: left; "
        "font-size: smaller; "
        "color: #555;"
    ),
}


StyleResolver = Callable[[Iterable[str]], str]


def _no_styles(_classes: Iterable[str]) -> str:
    """Standalone-mode resolver: never emit a `style=` attribute."""
    return ""


def _inline_styles_for(classes: Iterable[str]) -> str:
    """Fragment-mode resolver: build a ` style="..."` attribute fragment.

    Concatenates declarations from each class in `_STYLE_BY_CLASS` order
    so cascade is predictable: cell-base styles emit before role-specific
    styles, letting role styles override conflicting properties.
    """
    requested = set(classes)
    decls: list[str] = []
    for cls, decl in _STYLE_BY_CLASS.items():
        if cls in requested and decl:
            decls.append(decl)
    if not decls:
        return ""
    combined = " ".join(decls)
    return f' style="{_html.escape(combined, quote=True)}"'


def _build_css() -> str:
    """Default-theme CSS block content.

    Returned without surrounding `<style>` tags so H6 (standalone wrapper)
    can decide on indentation and `media`/`type` attributes. The rules
    use the same declarations the fragment-mode inline resolver emits, so
    the two output modes are visually identical.
    """
    rules: list[str] = []
    for cls, decl in _STYLE_BY_CLASS.items():
        if not decl:
            continue
        selector = "table.proctab" if cls == "proctab" else f".{cls}"
        rules.append(f"{selector} {{ {decl} }}")
    return "\n".join(rules)


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


def _corner_th(n_header_rows: int, *, style_for: StyleResolver) -> str:
    rowspan = f' rowspan="{n_header_rows}"' if n_header_rows > 1 else ""
    style = style_for(["proctab-corner"])
    return (
        f'<th{rowspan} class="proctab-corner" aria-hidden="true"{style}></th>'
    )


def _col_th(
    node: Node, *, is_innermost: bool, style_for: StyleResolver
) -> str:
    text = _html.escape(_node_label(node))
    scope = "col" if is_innermost else "colgroup"
    colspan = f' colspan="{node.span}"' if node.span > 1 else ""
    cls = _col_header_class(node)
    style = style_for([cls])
    return (
        f'<th{colspan} scope="{scope}" class="{cls}"{style}>{text}</th>'
    )


def _render_thead(col_axis: Axis, *, style_for: StyleResolver) -> str:
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
            cells.append(_corner_th(n_header_rows, style_for=style_for))
        for node in _nodes_at_depth(col_axis.tree, d):
            cells.append(
                _col_th(node, is_innermost=is_innermost, style_for=style_for)
            )
        body = "".join(f"      {c}\n" for c in cells)
        rows.append(f"    <tr>\n{body}    </tr>")

    if not rows:
        rows.append(
            f"    <tr>\n      {_corner_th(1, style_for=style_for)}\n    </tr>"
        )

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
    *,
    style_for: StyleResolver,
) -> str:
    classes = ["proctab-cell", f"proctab-{cell_role}"]

    if missing_code == int(MissingReason.PRESENT):
        text = _html.escape(_resolve_format(value, fmt, value_kind))
        dv = _data_value_attr(value)
        cls = " ".join(classes)
        style = style_for(classes)
        return f'<td class="{cls}"{dv}{style}>{text}</td>'

    suffix = _MISSING_SUFFIX[missing_code]
    text = _html.escape(_MISSING_TEXT[missing_code])
    classes.append(f"proctab-missing-{suffix}")
    cls = " ".join(classes)
    style = style_for(classes)
    return f'<td class="{cls}"{style}>{text}</td>'


def _row_label_th(node: Node, *, scope: str, style_for: StyleResolver) -> str:
    indent = max(node.depth - 1, 0)
    classes = ["proctab-row-label", f"proctab-indent-{indent}"]
    cls = " ".join(classes)
    text = _html.escape(_node_label(node))
    style = style_for(classes)
    return f'<th scope="{scope}" class="{cls}"{style}>{text}</th>'


def _render_leaf_row(
    row_leaf: Node,
    row_idx: int,
    col_leaves: list[Node],
    table: Table,
    *,
    style_for: StyleResolver,
) -> str:
    cells: list[str] = [
        _row_label_th(row_leaf, scope="row", style_for=style_for)
    ]
    for j, col_leaf in enumerate(col_leaves):
        cell_role = _cell_role(row_leaf.role, col_leaf.role)
        cells.append(
            _render_td(
                table.body[row_idx, j],
                int(table.missing[row_idx, j]),
                table.formats[j],
                table.value_kinds[j],
                cell_role,
                style_for=style_for,
            )
        )
    body = "".join(f"      {c}\n" for c in cells)
    row_cls = f"proctab-{row_leaf.role}"
    row_style = style_for([row_cls])
    return f'    <tr class="{row_cls}"{row_style}>\n{body}    </tr>'


def _render_group_row(
    node: Node, n_col_leaves: int, *, style_for: StyleResolver
) -> str:
    label_th = _row_label_th(node, scope="rowgroup", style_for=style_for)
    if n_col_leaves > 0:
        pad_style = style_for(["proctab-group-pad"])
        pad = (
            f'<td colspan="{n_col_leaves}" '
            f'class="proctab-group-pad"{pad_style}></td>'
        )
    else:
        pad = ""
    pad_line = f"      {pad}\n" if pad else ""
    row_style = style_for(["proctab-group-header"])
    return (
        f'    <tr class="proctab-group-header"{row_style}>\n'
        f"      {label_th}\n"
        f"{pad_line}"
        f"    </tr>"
    )


def _render_tbody(table: Table, *, style_for: StyleResolver) -> str:
    col_leaves = table.col_axis.leaves()
    n_col_leaves = len(col_leaves)

    rows: list[str] = []
    leaf_idx = 0
    for node in _walk_nonroot(table.row_axis.tree):
        if node.children is None:
            rows.append(
                _render_leaf_row(
                    node, leaf_idx, col_leaves, table, style_for=style_for
                )
            )
            leaf_idx += 1
        else:
            rows.append(
                _render_group_row(node, n_col_leaves, style_for=style_for)
            )

    if not rows:
        return "  <tbody></tbody>"
    inner = "\n".join(rows)
    return f"  <tbody>\n{inner}\n  </tbody>"


# ---------------------------------------------------------------------------
# H4 — Caption + tfoot.
# ---------------------------------------------------------------------------


def _render_caption(meta: dict | None, *, style_for: StyleResolver) -> str:
    if not meta:
        return ""
    title = meta.get("title")
    if not title:
        return ""
    style = style_for(["proctab-caption"])
    return (
        f'  <caption class="proctab-caption"{style}>'
        f"{_html.escape(str(title))}"
        f"</caption>"
    )


def _render_tfoot(
    meta: dict | None, n_total_cols: int, *, style_for: StyleResolver
) -> str:
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
        style = style_for(["proctab-source"])
        rows.append(
            f'    <tr class="proctab-source"{style}>\n'
            f'      <td colspan="{n_total_cols}">{text}</td>\n'
            f"    </tr>"
        )
    for fn in footnotes:
        text = _html.escape(str(fn))
        style = style_for(["proctab-footnote"])
        rows.append(
            f'    <tr class="proctab-footnote"{style}>\n'
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

    Fragment mode (`standalone=False`, default) emits `<table>` with
    inline `style="..."` attributes mirroring the standalone-mode CSS,
    so the table renders correctly when embedded in pages or notebooks
    without depending on an external stylesheet.

    Standalone mode emits the same `<table>` with class-only markup
    (no inline styles); the H6 wrapper supplies the CSS via an
    embedded `<style>` block.
    """
    style_for: StyleResolver = _no_styles if standalone else _inline_styles_for

    n_total_cols = 1 + len(table.col_axis.leaves())
    caption = _render_caption(table.meta, style_for=style_for)
    thead = _render_thead(table.col_axis, style_for=style_for)
    tbody = _render_tbody(table, style_for=style_for)
    tfoot = _render_tfoot(table.meta, n_total_cols, style_for=style_for)

    table_style = style_for(["proctab"])
    parts: list[str] = [f'<table class="proctab"{table_style}>']
    if caption:
        parts.append(caption)
    parts.append(thead)
    parts.append(tbody)
    if tfoot:
        parts.append(tfoot)
    parts.append("</table>")
    return "\n".join(parts)
