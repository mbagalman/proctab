"""Long-format DataFrame export for `Table`.

Schema is locked in docs/TABLE_MODEL.md#dataframe-export:

  one column per row dim  → Category.value, or None for marker positions
  one column per col dim  → same
  _value                  → numeric cell value, or None when missing
  _missing_reason         → None (PRESENT) / "empty" / "not_applicable" /
                            "suppressed" / "null"
  _row_role               → "data" / "subtotal" / "total"
  _col_role               → "data" / "subtotal" / "total"
  _row_leaf_id            → stable int from row tree's leaf ordering
  _col_leaf_id            → stable int from col tree's leaf ordering

All fixed columns use a leading underscore so they don't silently
collide with user-supplied dimension names (e.g., a real-world
DataFrame may have a column literally named `value`). A user dim
whose name collides with one of the reserved underscore-prefixed
columns raises `ValueError` early — see `_check_no_reserved_dim_names`.

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

_RESERVED_EXPORT_COLUMNS = frozenset({
    "_value",
    "_missing_reason",
    "_row_role",
    "_col_role",
    "_row_leaf_id",
    "_col_leaf_id",
})
"""Fixed column names emitted by `_build_long_format_columns`. Any
`Table` whose row or col dims include one of these names would collide
at export time, so we reject early with a clear error."""


def _path_element_value(el: object) -> object:
    """Return the Category value, or None for Subtotal/Total markers."""
    if isinstance(el, Category):
        return el.value
    return None


def _check_no_reserved_dim_names(table: Table) -> None:
    dim_names = {d.name for d in table.row_axis.dims} | {
        d.name for d in table.col_axis.dims
    }
    collisions = sorted(dim_names & _RESERVED_EXPORT_COLUMNS)
    if collisions:
        raise ValueError(
            f"Table dimension name(s) collide with reserved DataFrame-"
            f"export column name(s): {collisions}. Reserved names are "
            f"{sorted(_RESERVED_EXPORT_COLUMNS)}. Rename the source "
            f"column(s) before constructing the Table (e.g., "
            f"`df.rename(columns={{'_value': 'value_'}})`)."
        )


def _build_long_format_columns(table: Table) -> dict[str, list]:
    """Build columnar long-format data for DataFrame export.

    Returns a dict mapping column name → list of cell-aligned values,
    one entry per (row leaf × col leaf) intersection in row-major order.
    """
    _check_no_reserved_dim_names(table)

    row_dims = table.row_axis.dims
    col_dims = table.col_axis.dims
    row_leaves = table.row_axis.leaves()
    col_leaves = table.col_axis.leaves()

    columns: dict[str, list] = {}
    for dim in row_dims:
        columns[dim.name] = []
    for dim in col_dims:
        columns[dim.name] = []
    columns["_value"] = []
    columns["_missing_reason"] = []
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
                columns["_value"].append(float(table.body[i, j]))
                columns["_missing_reason"].append(None)
            else:
                columns["_value"].append(None)
                columns["_missing_reason"].append(_MISSING_REASON_NAME[missing_code])

            columns["_row_role"].append(row_leaf.role)
            columns["_col_role"].append(col_leaf.role)
            columns["_row_leaf_id"].append(i)
            columns["_col_leaf_id"].append(j)

    return columns
