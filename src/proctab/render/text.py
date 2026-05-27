"""Plain-text renderer for proctab Tables.

Functional, not polished. Used for REPL inspection, tests, and CI artifacts.
The HTML and Excel renderers are the headline outputs; this one exists to
prove the data model is renderable without engine-specific glue.
"""

from __future__ import annotations

from io import StringIO

from proctab.model import (
    Axis,
    Category,
    MissingReason,
    Node,
    SubtotalMarker,
    Table,
    TotalMarker,
)


def render_text(table: Table, *, col_width: int = 12) -> str:
    """Render a Table as plain text."""
    row_axis = table.row_axis
    col_axis = table.col_axis
    col_leaves = col_axis.leaves()
    n_cols = len(col_leaves)

    label_width = _row_label_width(row_axis)
    indent_pad = " " * label_width
    full_width = label_width + n_cols * col_width

    out = StringIO()

    title = table.meta.get("title")
    if title:
        out.write(f"{title}\n\n")

    for d in range(1, len(col_axis.dims) + 1):
        out.write(indent_pad + _format_col_header_level(col_axis, d, col_width) + "\n")
    out.write("─" * full_width + "\n")

    row_leaf_index = 0
    for node in _walk_nonroot(row_axis.tree):
        indent = "  " * (node.depth - 1)
        label = _node_label(node)

        if node.children is None:
            if node.role in ("subtotal", "total"):
                out.write("─" * full_width + "\n")
            row_label = (indent + label).ljust(label_width)
            cells_text = "".join(
                _format_cell(
                    table.body[row_leaf_index, j],
                    int(table.missing[row_leaf_index, j]),
                    table.formats[j],
                    col_width,
                )
                for j in range(n_cols)
            )
            out.write(row_label + cells_text + "\n")
            row_leaf_index += 1
        else:
            out.write(indent + label + "\n")

    footnotes = table.meta.get("footnotes") or []
    source = table.meta.get("source")
    if footnotes or source:
        out.write("\n")
        for note in footnotes:
            out.write(f"  {note}\n")
        if source:
            out.write(f"  Source: {source}\n")

    return out.getvalue()


def _walk_nonroot(node: Node):
    if node.depth > 0:
        yield node
    if node.children is not None:
        for child in node.children:
            yield from _walk_nonroot(child)


def _nodes_at_depth(root: Node, depth: int) -> list[Node]:
    if root.depth == depth:
        return [root]
    if root.children is None:
        return []
    out: list[Node] = []
    for child in root.children:
        out.extend(_nodes_at_depth(child, depth))
    return out


def _format_col_header_level(axis: Axis, depth: int, col_width: int) -> str:
    parts: list[str] = []
    for node in _nodes_at_depth(axis.tree, depth):
        label = _node_label(node)
        cell_width = node.span * col_width
        parts.append(label.center(cell_width))
    return "".join(parts)


def _row_label_width(row_axis: Axis, *, min_width: int = 16) -> int:
    max_w = min_width
    for node in _walk_nonroot(row_axis.tree):
        indent_len = 2 * (node.depth - 1)
        candidate = indent_len + len(_node_label(node)) + 2
        if candidate > max_w:
            max_w = candidate
    return max_w


def _node_label(node: Node) -> str:
    if node.label is not None:
        return node.label
    if not node.path:
        return ""
    return _path_element_label(node.path[-1])


def _path_element_label(element) -> str:
    if isinstance(element, Category):
        return str(element.label if element.label is not None else element.value)
    if isinstance(element, SubtotalMarker):
        return f"({element.at_dim} subtotal)"
    if isinstance(element, TotalMarker):
        return "(total)"
    return repr(element)


def _format_cell(value: float, missing_code: int, fmt: str | None, width: int) -> str:
    if missing_code != MissingReason.PRESENT:
        text = _missing_text(missing_code)
    elif fmt is None:
        text = f"{value:g}"
    else:
        text = fmt.format(value)
    return text.rjust(width)


def _missing_text(code: int) -> str:
    if code == MissingReason.EMPTY:
        return ""
    if code == MissingReason.NOT_APPLICABLE:
        return "—"
    if code == MissingReason.SUPPRESSED:
        return "***"
    if code == MissingReason.NULL:
        return "·"
    return "?"
