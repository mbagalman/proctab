"""Long-format DataFrame export for `Table`.

Schema is locked in docs/TABLE_MODEL.md#dataframe-export:

  one column per row dim  → Category.value, or None for marker positions
  one column per col dim  → same
  value                   → numeric cell value, or None when missing
  missing_reason          → None (PRESENT) / "empty" / "not_applicable" /
                            "suppressed" / "null"
  _row_role               → "data" / "subtotal" / "total"
  _col_role               → "data" / "subtotal" / "total"
  _row_leaf_id            → stable int from row tree's leaf ordering
  _col_leaf_id            → stable int from col tree's leaf ordering

Internal — `Table.to_pandas()` and `Table.to_polars()` are the public
entry points; both build the same columnar dict here and hand it to the
engine constructor.
"""

from __future__ import annotations

from proctab.model import Category, MissingReason, Table


_MISSING_REASON_NAME: dict[int, str] = {
    int(MissingReason.EMPTY): "empty",
    int(MissingReason.NOT_APPLICABLE): "not_applicable",
    int(MissingReason.SUPPRESSED): "suppressed",
    int(MissingReason.NULL): "null",
}


def _path_element_value(el: object) -> object:
    """Return the Category value, or None for Subtotal/Total markers."""
    if isinstance(el, Category):
        return el.value
    return None


def _build_long_format_columns(table: Table) -> dict[str, list]:
    """Build columnar long-format data for DataFrame export.

    Returns a dict mapping column name → list of cell-aligned values,
    one entry per (row leaf × col leaf) intersection in row-major order.
    """
    row_dims = table.row_axis.dims
    col_dims = table.col_axis.dims
    row_leaves = table.row_axis.leaves()
    col_leaves = table.col_axis.leaves()

    columns: dict[str, list] = {}
    for dim in row_dims:
        columns[dim.name] = []
    for dim in col_dims:
        columns[dim.name] = []
    columns["value"] = []
    columns["missing_reason"] = []
    columns["_row_role"] = []
    columns["_col_role"] = []
    columns["_row_leaf_id"] = []
    columns["_col_leaf_id"] = []

    present_code = int(MissingReason.PRESENT)

    for i, row_leaf in enumerate(row_leaves):
        row_dim_values = [
            _path_element_value(row_leaf.path[k]) for k in range(len(row_dims))
        ]
        for j, col_leaf in enumerate(col_leaves):
            for k, dim in enumerate(row_dims):
                columns[dim.name].append(row_dim_values[k])
            for k, dim in enumerate(col_dims):
                columns[dim.name].append(_path_element_value(col_leaf.path[k]))

            missing_code = int(table.missing[i, j])
            if missing_code == present_code:
                columns["value"].append(float(table.body[i, j]))
                columns["missing_reason"].append(None)
            else:
                columns["value"].append(None)
                columns["missing_reason"].append(_MISSING_REASON_NAME[missing_code])

            columns["_row_role"].append(row_leaf.role)
            columns["_col_role"].append(col_leaf.role)
            columns["_row_leaf_id"].append(i)
            columns["_col_leaf_id"].append(j)

    return columns
