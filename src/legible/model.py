"""Pure data containers for the Legible table model.

See ../../TABLE_MODEL.md for the design rationale. This module defines the
in-memory shape of a `Table` and the types it composes; it does NOT perform
any aggregation, rendering, or DataFrame I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Literal, Union

import numpy as np
import numpy.typing as npt


class MissingReason(IntEnum):
    PRESENT = 0
    EMPTY = 1
    NOT_APPLICABLE = 2
    SUPPRESSED = 3
    NULL = 4


ValueKind = Literal[
    "raw",
    "count",
    "currency",
    "percent",
    "ratio",
    "mean",
    "weighted_mean",
    "median",
    "sum",
]


@dataclass(frozen=True)
class Category:
    value: Any
    label: str | None = None


@dataclass(frozen=True)
class SubtotalMarker:
    at_dim: str


@dataclass(frozen=True)
class TotalMarker:
    pass


Marker = Union[SubtotalMarker, TotalMarker]
PathElement = Union[Category, SubtotalMarker, TotalMarker]


DimensionKind = Literal["category", "metric", "stat"]


@dataclass(frozen=True)
class Dimension:
    name: str
    kind: DimensionKind
    categories: tuple[Category, ...]
    observed: bool = True
    label: str | None = None


NodeRole = Literal["data", "subtotal", "total"]


@dataclass(frozen=True)
class Node:
    path: tuple[PathElement, ...]
    depth: int
    span: int
    role: NodeRole
    children: tuple["Node", ...] | None = None
    label: str | None = None

    @property
    def is_leaf(self) -> bool:
        return self.children is None

    def leaves(self) -> list["Node"]:
        if self.children is None:
            return [self]
        out: list[Node] = []
        for child in self.children:
            out.extend(child.leaves())
        return out


@dataclass(frozen=True)
class Axis:
    dims: tuple[Dimension, ...]
    tree: Node

    def leaves(self) -> list[Node]:
        return self.tree.leaves()

    def validate(self) -> None:
        """Enforce TABLE_MODEL.md structural invariants on the entire axis tree.

        Checks performed on every node:

        - `len(path) == depth` (the `depth` field is semantic — the dim
          level this node lives at — not tree position. Subtotal and total
          leaves can legitimately sit at a tree position shallower than
          their `depth`; e.g., a "West Subtotal" leaf may be a direct
          child of root while having depth 2.)
        - `Category` path elements belong to the dim at their position.
        - `SubtotalMarker.at_dim` matches the dim name at its position.
        - No path mixes `SubtotalMarker` and `TotalMarker`.
        - Role/path consistency: `data` → no markers; `subtotal` → has
          SubtotalMarker; `total` → has TotalMarker. (Skipped for the
          path-less root.)

        Additional checks per node kind:

        - Leaves: `span == 1`; `len(path) == len(self.dims)`.
        - Interior nodes: `span == sum(child.span for child in children)`.

        Not auto-run — call from tests or after hand-constructing an Axis.
        """
        self._validate_subtree(self.tree)

    def _validate_subtree(self, node: Node) -> None:
        node_id = self._describe(node)

        if len(node.path) != node.depth:
            raise ValueError(
                f"node {node_id}: len(path)={len(node.path)} != "
                f"depth={node.depth}"
            )

        n_dims = len(self.dims)
        if node.depth > n_dims:
            raise ValueError(
                f"node {node_id}: depth {node.depth} exceeds axis dim "
                f"count {n_dims}"
            )

        has_subtotal, has_total = self._validate_path(node, node_id)

        if node.depth > 0:
            if node.role == "data" and (has_subtotal or has_total):
                raise ValueError(
                    f"node {node_id}: role='data' but path contains "
                    f"marker(s); role should be 'subtotal' or 'total'"
                )
            if node.role == "subtotal" and not has_subtotal:
                raise ValueError(
                    f"node {node_id}: role='subtotal' but path has no "
                    f"SubtotalMarker"
                )
            if node.role == "total" and not has_total:
                raise ValueError(
                    f"node {node_id}: role='total' but path has no "
                    f"TotalMarker"
                )

        if node.children is None:
            if node.span != 1:
                raise ValueError(
                    f"leaf {node_id}: span {node.span} != 1"
                )
            n_dims = len(self.dims)
            if len(node.path) != n_dims:
                raise ValueError(
                    f"leaf {node_id}: path length {len(node.path)} != "
                    f"axis dim count {n_dims}"
                )
        else:
            expected_span = sum(c.span for c in node.children)
            if node.span != expected_span:
                raise ValueError(
                    f"node {node_id}: span {node.span} != sum of children "
                    f"spans {expected_span}"
                )
            for child in node.children:
                self._validate_subtree(child)

    def _describe(self, node: Node) -> str:
        if node is self.tree:
            return "<root>"
        if node.label:
            return node.label
        return f"path={node.path!r}"

    def _validate_path(self, node: Node, node_id: str) -> tuple[bool, bool]:
        has_subtotal = False
        has_total = False
        for i, element in enumerate(node.path):
            if isinstance(element, Category):
                if element not in self.dims[i].categories:
                    raise ValueError(
                        f"node {node_id} position {i}: category "
                        f"{element!r} not in dim {self.dims[i].name!r}"
                    )
            elif isinstance(element, SubtotalMarker):
                has_subtotal = True
                if element.at_dim != self.dims[i].name:
                    raise ValueError(
                        f"node {node_id} position {i}: SubtotalMarker has "
                        f"at_dim={element.at_dim!r} but dim at that "
                        f"position is {self.dims[i].name!r}"
                    )
            elif isinstance(element, TotalMarker):
                has_total = True
            else:
                raise ValueError(
                    f"node {node_id} position {i}: unrecognized path "
                    f"element type {type(element).__name__}"
                )

        if has_subtotal and has_total:
            raise ValueError(
                f"node {node_id}: path mixes SubtotalMarker and "
                f"TotalMarker; not supported in v0.1"
            )
        return has_subtotal, has_total


@dataclass
class Table:
    """Result of `freq()` / `tabulate()`. Treat as immutable — modify via `with_*()` methods."""

    row_axis: Axis
    col_axis: Axis
    body: npt.NDArray[np.float64]
    missing: npt.NDArray[np.uint8]
    value_kinds: tuple[ValueKind, ...]
    formats: tuple[str | None, ...]
    labels: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    _spec: Any = None

    def __post_init__(self) -> None:
        n_rows = len(self.row_axis.leaves())
        n_cols = len(self.col_axis.leaves())
        if self.body.shape != (n_rows, n_cols):
            raise ValueError(
                f"body shape {self.body.shape} doesn't match axis leaves "
                f"({n_rows} rows x {n_cols} cols)"
            )
        if self.missing.shape != self.body.shape:
            raise ValueError(
                f"missing shape {self.missing.shape} != body shape {self.body.shape}"
            )
        if len(self.value_kinds) != n_cols:
            raise ValueError(
                f"value_kinds length {len(self.value_kinds)} != {n_cols} col leaves"
            )
        if len(self.formats) != n_cols:
            raise ValueError(
                f"formats length {len(self.formats)} != {n_cols} col leaves"
            )

    def to_text(self, **kwargs: Any) -> str:
        """Plain-text render. Convenience wrapper around `legible.render.text.render_text`."""
        from legible.render.text import render_text
        return render_text(self, **kwargs)
