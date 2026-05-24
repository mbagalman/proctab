"""Tests for the Legible data-model containers."""

from __future__ import annotations

import numpy as np
import pytest

from legible import (
    Axis,
    Category,
    Dimension,
    MissingReason,
    Node,
    SubtotalMarker,
    Table,
    TotalMarker,
)


def _trivial_axis(name: str = "x") -> Axis:
    cats = (Category("A"), Category("B"))
    dim = Dimension(name=name, kind="category", categories=cats)
    tree = Node(
        path=(),
        depth=0,
        span=2,
        role="data",
        children=(
            Node(path=(cats[0],), depth=1, span=1, role="data"),
            Node(path=(cats[1],), depth=1, span=1, role="data"),
        ),
    )
    return Axis(dims=(dim,), tree=tree)


class TestEnumsAndLiterals:
    def test_missing_reason_codes(self):
        assert MissingReason.PRESENT == 0
        assert MissingReason.EMPTY == 1
        assert MissingReason.NOT_APPLICABLE == 2
        assert MissingReason.SUPPRESSED == 3
        assert MissingReason.NULL == 4


class TestFrozen:
    def test_category_is_frozen(self):
        c = Category("West")
        with pytest.raises(Exception):
            c.value = "East"  # type: ignore[misc]

    def test_dimension_is_frozen(self):
        d = Dimension(name="region", kind="category", categories=(Category("W"),))
        with pytest.raises(Exception):
            d.observed = False  # type: ignore[misc]


class TestNodeTree:
    def test_leaves_traversal_order(self):
        leaf1 = Node(path=(Category("A"),), depth=1, span=1, role="data")
        leaf2 = Node(path=(Category("B"),), depth=1, span=1, role="data")
        root = Node(
            path=(), depth=0, span=2, role="data",
            children=(leaf1, leaf2),
        )
        assert root.leaves() == [leaf1, leaf2]

    def test_is_leaf(self):
        leaf = Node(path=(Category("A"),), depth=1, span=1, role="data")
        assert leaf.is_leaf

        root = Node(path=(), depth=0, span=1, role="data", children=(leaf,))
        assert not root.is_leaf

    def test_nested_leaves_preorder(self):
        a_widget = Node(path=(Category("West"), Category("Widget A")),
                        depth=2, span=1, role="data")
        b_widget = Node(path=(Category("West"), Category("Widget B")),
                        depth=2, span=1, role="data")
        west = Node(path=(Category("West"),), depth=1, span=2, role="data",
                    children=(a_widget, b_widget))
        east_leaf = Node(path=(Category("East"), Category("Widget A")),
                         depth=2, span=1, role="data")
        east = Node(path=(Category("East"),), depth=1, span=1, role="data",
                    children=(east_leaf,))
        root = Node(path=(), depth=0, span=3, role="data",
                    children=(west, east))
        assert root.leaves() == [a_widget, b_widget, east_leaf]


class TestAxisValidate:
    def test_validate_passes_on_well_formed_axis(self):
        axis = _trivial_axis()
        axis.validate()

    def test_validate_fails_on_path_length_mismatch(self):
        cats = (Category("A"),)
        dim1 = Dimension(name="x", kind="category", categories=cats)
        dim2 = Dimension(name="y", kind="category", categories=cats)
        bad_leaf = Node(path=(cats[0],), depth=1, span=1, role="data")
        tree = Node(path=(), depth=0, span=1, role="data", children=(bad_leaf,))
        axis = Axis(dims=(dim1, dim2), tree=tree)
        with pytest.raises(ValueError, match="path length"):
            axis.validate()

    def test_validate_fails_on_unknown_category(self):
        known = Category("A")
        unknown = Category("Z")
        dim = Dimension(name="x", kind="category", categories=(known,))
        bad_leaf = Node(path=(unknown,), depth=1, span=1, role="data")
        tree = Node(path=(), depth=0, span=1, role="data", children=(bad_leaf,))
        axis = Axis(dims=(dim,), tree=tree)
        with pytest.raises(ValueError, match="not in dim"):
            axis.validate()

    def test_validate_allows_markers_in_any_position(self):
        cats = (Category("A"),)
        dim1 = Dimension(name="region", kind="category", categories=cats)
        dim2 = Dimension(name="product", kind="category", categories=(Category("X"),))
        subtotal_leaf = Node(
            path=(cats[0], SubtotalMarker(at_dim="product")),
            depth=2, span=1, role="subtotal",
        )
        total_leaf = Node(
            path=(TotalMarker(), TotalMarker()),
            depth=2, span=1, role="total",
        )
        tree = Node(
            path=(), depth=0, span=2, role="data",
            children=(subtotal_leaf, total_leaf),
        )
        axis = Axis(dims=(dim1, dim2), tree=tree)
        axis.validate()

    def _two_dim_axis_with_leaf(self, leaf: Node) -> Axis:
        dim1 = Dimension(name="region", kind="category",
                         categories=(Category("West"),))
        dim2 = Dimension(name="product", kind="category",
                         categories=(Category("Widget A"),))
        tree = Node(path=(), depth=0, span=1, role="data", children=(leaf,))
        return Axis(dims=(dim1, dim2), tree=tree)

    def test_validate_fails_on_subtotal_marker_wrong_dim(self):
        bad_leaf = Node(
            path=(Category("West"), SubtotalMarker(at_dim="region")),
            depth=2, span=1, role="subtotal",
        )
        with pytest.raises(ValueError, match="at_dim"):
            self._two_dim_axis_with_leaf(bad_leaf).validate()

    def test_validate_fails_on_data_role_with_total_marker(self):
        bad_leaf = Node(
            path=(Category("West"), TotalMarker()),
            depth=2, span=1, role="data",
        )
        with pytest.raises(ValueError, match="role='data' but path contains marker"):
            self._two_dim_axis_with_leaf(bad_leaf).validate()

    def test_validate_fails_on_data_role_with_subtotal_marker(self):
        bad_leaf = Node(
            path=(Category("West"), SubtotalMarker(at_dim="product")),
            depth=2, span=1, role="data",
        )
        with pytest.raises(ValueError, match="role='data' but path contains marker"):
            self._two_dim_axis_with_leaf(bad_leaf).validate()

    def test_validate_fails_on_subtotal_role_without_marker(self):
        bad_leaf = Node(
            path=(Category("West"), Category("Widget A")),
            depth=2, span=1, role="subtotal",
        )
        with pytest.raises(ValueError, match="role='subtotal' but path has no SubtotalMarker"):
            self._two_dim_axis_with_leaf(bad_leaf).validate()

    def test_validate_fails_on_total_role_without_marker(self):
        bad_leaf = Node(
            path=(Category("West"), Category("Widget A")),
            depth=2, span=1, role="total",
        )
        with pytest.raises(ValueError, match="role='total' but path has no TotalMarker"):
            self._two_dim_axis_with_leaf(bad_leaf).validate()

    def test_validate_fails_on_mixed_subtotal_and_total_markers(self):
        bad_leaf = Node(
            path=(TotalMarker(), SubtotalMarker(at_dim="product")),
            depth=2, span=1, role="total",
        )
        with pytest.raises(ValueError, match="mixes SubtotalMarker and TotalMarker"):
            self._two_dim_axis_with_leaf(bad_leaf).validate()

    def test_validate_allows_total_role_with_partial_marker_path(self):
        """A leaf under a Total branch with a Category at deeper positions is valid."""
        # (TotalMarker, Category) -- e.g. "N stat under the Total column"
        cat_n = Category("N")
        dim1 = Dimension(name="product", kind="category",
                         categories=(Category("Widget A"),))
        dim2 = Dimension(name="_stat", kind="stat", categories=(cat_n,))
        leaf = Node(
            path=(TotalMarker(), cat_n),
            depth=2, span=1, role="total",
        )
        tree = Node(path=(), depth=0, span=1, role="data", children=(leaf,))
        Axis(dims=(dim1, dim2), tree=tree).validate()


class TestAxisValidateHardening:
    """Full-tree invariants: spans, depths, malformed branch paths."""

    # --- span checks ---

    def test_leaf_span_not_one_raises(self):
        cat = Category("A")
        dim = Dimension(name="x", kind="category", categories=(cat,))
        bad_leaf = Node(path=(cat,), depth=1, span=2, role="data")
        tree = Node(path=(), depth=0, span=2, role="data", children=(bad_leaf,))
        with pytest.raises(ValueError, match="span 2 != 1"):
            Axis(dims=(dim,), tree=tree).validate()

    def test_branch_span_not_sum_of_children_raises(self):
        cat_a = Category("A")
        cat_b = Category("B")
        dim = Dimension(name="x", kind="category", categories=(cat_a, cat_b))
        leaf_a = Node(path=(cat_a,), depth=1, span=1, role="data")
        leaf_b = Node(path=(cat_b,), depth=1, span=1, role="data")
        bad_root = Node(path=(), depth=0, span=5, role="data",
                        children=(leaf_a, leaf_b))
        with pytest.raises(ValueError, match="span 5 != sum of children spans 2"):
            Axis(dims=(dim,), tree=bad_root).validate()

    # --- depth checks ---

    def test_root_depth_inconsistent_with_path_raises(self):
        cat = Category("A")
        dim = Dimension(name="x", kind="category", categories=(cat,))
        leaf = Node(path=(cat,), depth=1, span=1, role="data")
        bad_root = Node(path=(), depth=99, span=1, role="data",
                        children=(leaf,))
        with pytest.raises(ValueError, match=r"len\(path\)=0 != depth=99"):
            Axis(dims=(dim,), tree=bad_root).validate()

    def test_leaf_depth_inconsistent_with_path_raises(self):
        cat = Category("A")
        dim = Dimension(name="x", kind="category", categories=(cat,))
        bad_leaf = Node(path=(cat,), depth=5, span=1, role="data")
        tree = Node(path=(), depth=0, span=1, role="data", children=(bad_leaf,))
        with pytest.raises(ValueError, match=r"len\(path\)=1 != depth=5"):
            Axis(dims=(dim,), tree=tree).validate()

    def test_path_length_not_matching_depth_raises(self):
        cat = Category("A")
        dim = Dimension(name="x", kind="category", categories=(cat,))
        bad_leaf = Node(path=(), depth=1, span=1, role="data")
        tree = Node(path=(), depth=0, span=1, role="data", children=(bad_leaf,))
        with pytest.raises(ValueError, match=r"len\(path\)=0 != depth=1"):
            Axis(dims=(dim,), tree=tree).validate()

    # --- branch path checks ---

    def test_branch_path_with_unknown_category_raises(self):
        known = Category("A")
        unknown = Category("Z")
        dim1 = Dimension(name="region", kind="category", categories=(known,))
        dim2 = Dimension(name="product", kind="category",
                         categories=(Category("X"),))
        leaf = Node(path=(unknown, Category("X")),
                    depth=2, span=1, role="data")
        bad_branch = Node(path=(unknown,), depth=1, span=1, role="data",
                          children=(leaf,))
        tree = Node(path=(), depth=0, span=1, role="data",
                    children=(bad_branch,))
        with pytest.raises(ValueError, match="not in dim"):
            Axis(dims=(dim1, dim2), tree=tree).validate()

    def test_branch_subtotal_marker_wrong_dim_raises(self):
        cat_west = Category("West")
        dim1 = Dimension(name="region", kind="category", categories=(cat_west,))
        dim2 = Dimension(name="product", kind="category",
                         categories=(Category("X"),))
        leaf = Node(path=(cat_west, SubtotalMarker(at_dim="product")),
                    depth=2, span=1, role="subtotal")
        bad_branch = Node(path=(SubtotalMarker(at_dim="not_region"),),
                          depth=1, span=1, role="subtotal",
                          children=(leaf,))
        tree = Node(path=(), depth=0, span=1, role="data",
                    children=(bad_branch,))
        with pytest.raises(ValueError, match="at_dim"):
            Axis(dims=(dim1, dim2), tree=tree).validate()

    def test_branch_role_total_without_marker_raises(self):
        cat = Category("A")
        dim1 = Dimension(name="x", kind="category", categories=(cat,))
        dim2 = Dimension(name="y", kind="category",
                         categories=(Category("Y"),))
        leaf = Node(path=(cat, Category("Y")), depth=2, span=1, role="data")
        bad_branch = Node(path=(cat,), depth=1, span=1, role="total",
                          children=(leaf,))
        tree = Node(path=(), depth=0, span=1, role="data",
                    children=(bad_branch,))
        with pytest.raises(ValueError, match="role='total' but path has no TotalMarker"):
            Axis(dims=(dim1, dim2), tree=tree).validate()

    def test_branch_role_data_with_total_marker_raises(self):
        dim1 = Dimension(name="x", kind="category",
                         categories=(Category("A"),))
        dim2 = Dimension(name="y", kind="category",
                         categories=(Category("Y"),))
        leaf = Node(path=(TotalMarker(), Category("Y")),
                    depth=2, span=1, role="total")
        bad_branch = Node(path=(TotalMarker(),), depth=1, span=1, role="data",
                          children=(leaf,))
        tree = Node(path=(), depth=0, span=1, role="data",
                    children=(bad_branch,))
        with pytest.raises(ValueError, match="role='data' but path contains marker"):
            Axis(dims=(dim1, dim2), tree=tree).validate()

    # --- recursion ---

    def test_node_depth_exceeds_axis_dim_count_raises_valueerror_not_indexerror(self):
        """A node whose depth exceeds the axis's dim count must raise
        ValueError, never IndexError. Regression test for the path-indexing
        bug where _validate_path() would crash before the leaf-level
        n_dims check could fire."""
        cat_a = Category("A")
        cat_b = Category("B")
        dim = Dimension(name="x", kind="category", categories=(cat_a,))
        # leaf with path of length 2 in a 1-dim axis
        bad_leaf = Node(path=(cat_a, cat_b), depth=2, span=1, role="data")
        tree = Node(path=(), depth=0, span=1, role="data", children=(bad_leaf,))
        with pytest.raises(ValueError, match="exceeds axis dim count"):
            Axis(dims=(dim,), tree=tree).validate()

    def test_validation_recurses_to_deep_bad_node(self):
        cat_a = Category("A")
        cat_b = Category("B")
        cat_x = Category("X")
        dim1 = Dimension(name="r", kind="category", categories=(cat_a, cat_b))
        dim2 = Dimension(name="p", kind="category", categories=(cat_x,))
        leaf_ax = Node(path=(cat_a, cat_x), depth=2, span=1, role="data")
        leaf_bx = Node(path=(cat_b, cat_x), depth=2, span=99, role="data")
        branch_a = Node(path=(cat_a,), depth=1, span=1, role="data",
                        children=(leaf_ax,))
        branch_b = Node(path=(cat_b,), depth=1, span=99, role="data",
                        children=(leaf_bx,))
        tree = Node(path=(), depth=0, span=100, role="data",
                    children=(branch_a, branch_b))
        with pytest.raises(ValueError, match="span 99 != 1"):
            Axis(dims=(dim1, dim2), tree=tree).validate()


class TestTableShapeInvariant:
    def _kwargs(self, body, missing, value_kinds=("count", "count"),
                formats=(None, None)) -> dict:
        return {
            "row_axis": _trivial_axis("row"),
            "col_axis": _trivial_axis("col"),
            "body": body,
            "missing": missing,
            "value_kinds": value_kinds,
            "formats": formats,
        }

    def test_construct_well_formed_table(self):
        body = np.zeros((2, 2), dtype=np.float64)
        missing = np.zeros((2, 2), dtype=np.uint8)
        Table(**self._kwargs(body, missing))

    def test_body_shape_mismatch_raises(self):
        body = np.zeros((3, 2), dtype=np.float64)
        missing = np.zeros((3, 2), dtype=np.uint8)
        with pytest.raises(ValueError, match="body shape"):
            Table(**self._kwargs(body, missing))

    def test_missing_shape_mismatch_raises(self):
        body = np.zeros((2, 2), dtype=np.float64)
        missing = np.zeros((2, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="missing shape"):
            Table(**self._kwargs(body, missing))

    def test_value_kinds_length_mismatch_raises(self):
        body = np.zeros((2, 2), dtype=np.float64)
        missing = np.zeros((2, 2), dtype=np.uint8)
        with pytest.raises(ValueError, match="value_kinds"):
            Table(**self._kwargs(body, missing, value_kinds=("count",)))

    def test_formats_length_mismatch_raises(self):
        body = np.zeros((2, 2), dtype=np.float64)
        missing = np.zeros((2, 2), dtype=np.uint8)
        with pytest.raises(ValueError, match="formats"):
            Table(**self._kwargs(body, missing, formats=(None,)))
