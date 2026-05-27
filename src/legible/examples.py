"""Hand-built Table fixtures for the worked examples in VISION.md.

These tables are constructed with literal values — no aggregation pipeline —
to stress-test the data model. If any of these is annoying to build, the
model needs revision.

Doubles as a reference for "what does a Table look like in code?"
"""

from __future__ import annotations

import numpy as np

from legible.model import (
    Axis,
    Category,
    Dimension,
    MissingReason,
    Node,
    SubtotalMarker,
    Table,
    TotalMarker,
)


def _leaf(path, role="data", label=None) -> Node:
    return Node(path=path, depth=len(path), span=1, role=role, label=label)


def _branch(path, children, role="data", label=None) -> Node:
    children = tuple(children)
    return Node(
        path=path,
        depth=len(path),
        span=sum(c.span for c in children),
        role=role,
        label=label,
        children=children,
    )


def _root(children) -> Node:
    children = tuple(children)
    return Node(
        path=(),
        depth=0,
        span=sum(c.span for c in children),
        role="data",
        children=children,
    )


def example_1_one_way_freq() -> Table:
    """`lg.freq(df, "region")` — one-way frequency table."""
    regions = [Category("West"), Category("East"),
               Category("South"), Category("North")]
    stats = [Category("N"), Category("Pct"),
             Category("CumN"), Category("CumPct", label="Cum%")]

    region_dim = Dimension(name="region", kind="category", categories=tuple(regions))
    stat_dim = Dimension(name="_stat", kind="stat", categories=tuple(stats))

    row_leaves = [_leaf((r,)) for r in regions] + [
        _leaf((TotalMarker(),), role="total", label="Total"),
    ]
    row_axis = Axis(dims=(region_dim,), tree=_root(row_leaves))

    col_axis = Axis(
        dims=(stat_dim,),
        tree=_root([_leaf((s,)) for s in stats]),
    )

    counts = np.array([45, 52, 28, 25], dtype=np.float64)
    total = counts.sum()
    cum = np.cumsum(counts)
    body = np.array([
        [counts[0], counts[0] / total * 100, cum[0], cum[0] / total * 100],
        [counts[1], counts[1] / total * 100, cum[1], cum[1] / total * 100],
        [counts[2], counts[2] / total * 100, cum[2], cum[2] / total * 100],
        [counts[3], counts[3] / total * 100, cum[3], cum[3] / total * 100],
        [total,     100.0,                   total,   100.0],
    ], dtype=np.float64)
    missing = np.zeros(body.shape, dtype=np.uint8)

    return Table(
        row_axis=row_axis,
        col_axis=col_axis,
        body=body,
        missing=missing,
        value_kinds=("count", "percent", "count", "percent"),
        formats=("{:.0f}", "{:.1f}%", "{:.0f}", "{:.1f}%"),
        meta={"title": "Region frequency"},
    )


def example_1b_two_way_freq() -> Table:
    """`lg.freq(df, ["region", "product_line"])` — two-way crosstab with margins."""
    regions = [Category("West"), Category("East"), Category("South")]
    products = [Category("Widget A"), Category("Widget B")]
    stats = [
        Category("N"),
        Category("RowPct", label="Row%"),
        Category("ColPct", label="Col%"),
        Category("TotPct", label="Tot%"),
    ]

    region_dim = Dimension(name="region", kind="category", categories=tuple(regions))
    product_dim = Dimension(name="product_line", kind="category", categories=tuple(products))
    stat_dim = Dimension(name="_stat", kind="stat", categories=tuple(stats))

    row_axis = Axis(
        dims=(region_dim,),
        tree=_root(
            [_leaf((r,)) for r in regions]
            + [_leaf((TotalMarker(),), role="total", label="Total")]
        ),
    )

    def stats_under(parent_path, leaf_role="data"):
        return [_leaf(parent_path + (s,), role=leaf_role) for s in stats]

    col_children = [_branch((p,), stats_under((p,))) for p in products]
    col_children.append(
        _branch((TotalMarker(),), stats_under((TotalMarker(),), leaf_role="total"),
                role="total", label="Total")
    )
    col_axis = Axis(dims=(product_dim, stat_dim), tree=_root(col_children))

    cell_counts = np.array([
        [20, 25],
        [30, 22],
        [15, 18],
    ], dtype=np.float64)
    row_totals = cell_counts.sum(axis=1)
    col_totals = cell_counts.sum(axis=0)
    grand_total = cell_counts.sum()

    n_data_rows = len(regions)
    body = np.zeros((n_data_rows + 1, 12), dtype=np.float64)
    for i in range(n_data_rows):
        for p_idx in range(2):
            base = p_idx * 4
            n = cell_counts[i, p_idx]
            body[i, base + 0] = n
            body[i, base + 1] = n / row_totals[i] * 100
            body[i, base + 2] = n / col_totals[p_idx] * 100
            body[i, base + 3] = n / grand_total * 100
        base = 8
        n = row_totals[i]
        body[i, base + 0] = n
        body[i, base + 1] = 100.0
        body[i, base + 2] = n / grand_total * 100
        body[i, base + 3] = n / grand_total * 100

    for p_idx in range(2):
        base = p_idx * 4
        n = col_totals[p_idx]
        body[-1, base + 0] = n
        body[-1, base + 1] = n / grand_total * 100
        body[-1, base + 2] = 100.0
        body[-1, base + 3] = n / grand_total * 100
    body[-1, 8] = grand_total
    body[-1, 9:12] = 100.0

    missing = np.zeros(body.shape, dtype=np.uint8)

    formats = ("{:.0f}", "{:.1f}%", "{:.1f}%", "{:.1f}%") * 3
    value_kinds = ("count", "percent", "percent", "percent") * 3

    return Table(
        row_axis=row_axis,
        col_axis=col_axis,
        body=body,
        missing=missing,
        value_kinds=value_kinds,
        formats=formats,
        meta={"title": "Region × Product Line"},
    )


def example_2_tabulate() -> Table:
    """Full tabulate: rows=[region, product] × cols=[quarter, _metric, _stat] with sparse leaves and subtotals."""
    regions = [Category("West"), Category("East")]
    products = [Category("Widget A"), Category("Widget B")]
    quarters = [Category("Q1"), Category("Q2"), Category("Q3"), Category("Q4")]
    metrics = [Category("revenue", label="Revenue"),
               Category("margin", label="Margin")]
    all_stats = [
        Category("sum", label="Sum"),
        Category("mean", label="Mean"),
        Category("weighted_mean", label="W.Mean"),
    ]

    region_dim = Dimension(name="region", kind="category", categories=tuple(regions))
    product_dim = Dimension(name="product", kind="category", categories=tuple(products))
    quarter_dim = Dimension(name="quarter", kind="category", categories=tuple(quarters))
    metric_dim = Dimension(name="_metric", kind="metric", categories=tuple(metrics))
    stat_dim = Dimension(name="_stat", kind="stat", categories=tuple(all_stats))

    row_children = []
    for r in regions:
        product_leaves = [_leaf((r, p)) for p in products]
        row_children.append(_branch((r,), product_leaves))
        row_children.append(
            _leaf((r, SubtotalMarker(at_dim="product")),
                  role="subtotal", label=f"{r.value} Subtotal")
        )
    row_children.append(
        _leaf((TotalMarker(), TotalMarker()), role="total", label="Grand Total")
    )
    row_axis = Axis(dims=(region_dim, product_dim), tree=_root(row_children))

    requested = [
        (metrics[0], all_stats[0]),
        (metrics[0], all_stats[1]),
        (metrics[1], all_stats[2]),
    ]
    by_metric: dict[Category, list[Category]] = {}
    for m, s in requested:
        by_metric.setdefault(m, []).append(s)

    col_children = []
    for q in quarters:
        metric_branches = []
        for m, stat_list in by_metric.items():
            stat_leaves = [_leaf((q, m, s)) for s in stat_list]
            metric_branches.append(_branch((q, m), stat_leaves))
        col_children.append(_branch((q,), metric_branches))
    col_axis = Axis(dims=(quarter_dim, metric_dim, stat_dim), tree=_root(col_children))

    n_rows = 7
    n_cols = 12
    revenue_q = np.array([
        [100, 120,  95, 130],
        [ 80, 110,  90, 115],
        [180, 230, 185, 245],
        [ 90, 100, 110, 125],
        [ 70,  85,  95, 100],
        [160, 185, 205, 225],
        [340, 415, 390, 470],
    ], dtype=np.float64)

    rng = np.random.default_rng(42)
    body = np.zeros((n_rows, n_cols), dtype=np.float64)
    for q_idx in range(4):
        base = q_idx * 3
        body[:, base + 0] = revenue_q[:, q_idx]
        body[:, base + 1] = revenue_q[:, q_idx] / 10.0
        body[:, base + 2] = 0.20 + 0.05 * rng.random(n_rows)

    missing = np.zeros(body.shape, dtype=np.uint8)
    missing[4, 11] = MissingReason.NOT_APPLICABLE
    body[4, 11] = 0.0

    formats = ("{:,.0f}", "{:,.1f}", "{:.1%}") * 4
    value_kinds = ("sum", "mean", "weighted_mean") * 4

    return Table(
        row_axis=row_axis,
        col_axis=col_axis,
        body=body,
        missing=missing,
        value_kinds=value_kinds,
        formats=formats,
        meta={"title": "Revenue and Margin by Region / Product × Quarter"},
    )


def example_5_customized() -> Table:
    """Power-user customization: region × quarter, currency, labels, footnote, source."""
    regions = [Category("West"), Category("East"),
               Category("South"), Category("North")]
    quarters = [Category("Q1"), Category("Q2"), Category("Q3"), Category("Q4")]

    region_dim = Dimension(
        name="region", kind="category", categories=tuple(regions), label="Sales Region"
    )
    quarter_dim = Dimension(name="quarter", kind="category", categories=tuple(quarters))

    row_axis = Axis(dims=(region_dim,), tree=_root([_leaf((r,)) for r in regions]))
    col_axis = Axis(dims=(quarter_dim,), tree=_root([_leaf((q,)) for q in quarters]))

    rng = np.random.default_rng(1)
    body = (rng.random((4, 4)) * 500_000 + 50_000).round()
    missing = np.zeros(body.shape, dtype=np.uint8)

    return Table(
        row_axis=row_axis,
        col_axis=col_axis,
        body=body,
        missing=missing,
        value_kinds=("currency",) * 4,
        formats=("${:,.0f}",) * 4,
        labels={"region": "Sales Region", "revenue": "Net Revenue"},
        meta={
            "title": "Net Revenue by Region",
            "source": "internal CRM, 2026-Q1",
            "footnotes": ["All figures USD. Excludes returns."],
        },
    )


# === T7 reference fixture (v0.1-clean tabulate) ============================


def example_2_tabulate_v01_source() -> dict:
    """Deterministic source data for `example_2_tabulate_v01`.

    Eight rows: 2 regions × 2 products × 2 quarters, exactly one record
    per (region, product, quarter) cell. Revenue and margin values are
    simple enough that every aggregation (sum / mean across any subset)
    can be verified by eye.
    """
    return {
        "region":  ["E", "E", "E", "E", "W", "W", "W", "W"],
        "product": ["A", "A", "B", "B", "A", "A", "B", "B"],
        "quarter": ["Q1", "Q2", "Q1", "Q2", "Q1", "Q2", "Q1", "Q2"],
        "revenue": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
        "margin":  [0.1,  0.2,  0.3,  0.4,  0.5,  0.6,  0.7,  0.8],
    }


def example_2_tabulate_v01() -> Table:
    """v0.1-clean version of `example_2_tabulate`: substitutes `mean`
    for `weighted_mean` on the margin metric (weighted is v0.2).

    Structurally identical to what `lg.tabulate(df, rows=["region",
    "product"], cols="quarter", values={"revenue": ["sum", "mean"],
    "margin": "mean"}, subtotals="region", totals=True)` should
    produce for the source DataFrame from `example_2_tabulate_v01_source()`.

    Every cell value is computed by direct numpy aggregation here,
    independently of the `lg.tabulate` pipeline — that's the point.
    T7's integration tests run both and assert the outputs match.
    """
    src = example_2_tabulate_v01_source()
    revenue = np.array(src["revenue"], dtype=np.float64)
    margin = np.array(src["margin"], dtype=np.float64)
    region = np.array(src["region"])
    product = np.array(src["product"])
    quarter = np.array(src["quarter"])

    # Categories — sorted alphabetical, matching lg.tabulate's observed-mode default
    region_cats = ("E", "W")
    product_cats = ("A", "B")
    quarter_cats = ("Q1", "Q2")

    region_dim = Dimension(
        name="region", kind="category",
        categories=tuple(Category(c) for c in region_cats),
    )
    product_dim = Dimension(
        name="product", kind="category",
        categories=tuple(Category(c) for c in product_cats),
    )
    quarter_dim = Dimension(
        name="quarter", kind="category",
        categories=tuple(Category(c) for c in quarter_cats),
    )
    metric_dim = Dimension(
        name="_metric", kind="metric",
        categories=(Category("revenue"), Category("margin")),
    )
    stat_dim = Dimension(
        name="_stat", kind="stat",
        categories=(Category("sum"), Category("mean")),
    )

    # Row tree (matches T5's _build_row_axis output for 2-dim + subtotals + totals)
    row_children = []
    for r in region_cats:
        r_cat = Category(r)
        product_leaves = tuple(
            Node(path=(r_cat, Category(p)), depth=2, span=1, role="data")
            for p in product_cats
        )
        row_children.append(Node(
            path=(r_cat,), depth=1,
            span=len(product_leaves),
            role="data",
            children=product_leaves,
        ))
        row_children.append(Node(
            path=(r_cat, SubtotalMarker(at_dim="product")),
            depth=2, span=1, role="subtotal",
            label=f"{r} Subtotal",
        ))
    row_children.append(Node(
        path=(TotalMarker(), TotalMarker()),
        depth=2, span=1, role="total",
        label="Grand Total",
    ))
    row_axis = Axis(
        dims=(region_dim, product_dim),
        tree=Node(
            path=(), depth=0,
            span=sum(c.span for c in row_children),
            role="data",
            children=tuple(row_children),
        ),
    )

    # Col tree (matches T5's _build_col_axis output)
    def _col_branch(outer_path, outer_role, label):
        rev_leaves = tuple(
            Node(path=outer_path + (Category("revenue"), Category(s)),
                 depth=len(outer_path) + 2, span=1, role=outer_role)
            for s in ("sum", "mean")
        )
        rev_branch = Node(
            path=outer_path + (Category("revenue"),),
            depth=len(outer_path) + 1, span=len(rev_leaves),
            role=outer_role,
            children=rev_leaves,
        )
        mar_leaf = Node(
            path=outer_path + (Category("margin"), Category("mean")),
            depth=len(outer_path) + 2, span=1, role=outer_role,
        )
        mar_branch = Node(
            path=outer_path + (Category("margin"),),
            depth=len(outer_path) + 1, span=1,
            role=outer_role,
            children=(mar_leaf,),
        )
        return Node(
            path=outer_path, depth=len(outer_path),
            span=rev_branch.span + mar_branch.span,
            role=outer_role,
            label=label,
            children=(rev_branch, mar_branch),
        )

    col_children = [
        _col_branch((Category(q),), "data", label=None) for q in quarter_cats
    ]
    col_children.append(
        _col_branch((TotalMarker(),), "total", label="Total")
    )
    col_axis = Axis(
        dims=(quarter_dim, metric_dim, stat_dim),
        tree=Node(
            path=(), depth=0,
            span=sum(c.span for c in col_children),
            role="data",
            children=tuple(col_children),
        ),
    )

    # Body computation — direct numpy aggregation per cell, ground truth
    body = np.zeros((7, 9), dtype=np.float64)
    missing = np.zeros((7, 9), dtype=np.uint8)

    def _stats_for_mask(mask):
        """Returns (revenue_sum, revenue_mean, margin_mean) for masked rows."""
        rev = revenue[mask]
        mar = margin[mask]
        return float(rev.sum()), float(rev.mean()), float(mar.mean())

    # Data + Total-col cells per (region, product) row
    for ri, r in enumerate(region_cats):
        for pi, p in enumerate(product_cats):
            row_idx = ri * 3 + pi  # row order: r0p0, r0p1, r0sub, r1p0, r1p1, r1sub, total
            for qi, q in enumerate(quarter_cats):
                base = qi * 3
                sv = _stats_for_mask(
                    (region == r) & (product == p) & (quarter == q)
                )
                body[row_idx, base + 0] = sv[0]
                body[row_idx, base + 1] = sv[1]
                body[row_idx, base + 2] = sv[2]
            # Total col for this row
            sv = _stats_for_mask((region == r) & (product == p))
            body[row_idx, 6] = sv[0]
            body[row_idx, 7] = sv[1]
            body[row_idx, 8] = sv[2]

        # Subtotal at region (row idx ri*3 + 2)
        sub_idx = ri * 3 + 2
        for qi, q in enumerate(quarter_cats):
            base = qi * 3
            sv = _stats_for_mask((region == r) & (quarter == q))
            body[sub_idx, base + 0] = sv[0]
            body[sub_idx, base + 1] = sv[1]
            body[sub_idx, base + 2] = sv[2]
        sv = _stats_for_mask(region == r)
        body[sub_idx, 6] = sv[0]
        body[sub_idx, 7] = sv[1]
        body[sub_idx, 8] = sv[2]

    # Grand total row (row idx 6)
    for qi, q in enumerate(quarter_cats):
        base = qi * 3
        sv = _stats_for_mask(quarter == q)
        body[6, base + 0] = sv[0]
        body[6, base + 1] = sv[1]
        body[6, base + 2] = sv[2]
    sv = _stats_for_mask(np.ones(8, dtype=bool))
    body[6, 6] = sv[0]
    body[6, 7] = sv[1]
    body[6, 8] = sv[2]

    # Per-col-leaf metadata (matches T5's STAT_DEFAULTS lookups)
    # Each col group: (revenue/sum, revenue/mean, margin/mean) → kinds/formats
    value_kinds: tuple = ("sum", "mean", "mean") * 3
    formats: tuple = ("{:,.0f}", "{:,.2f}", "{:,.2f}") * 3

    return Table(
        row_axis=row_axis,
        col_axis=col_axis,
        body=body,
        missing=missing,
        value_kinds=value_kinds,
        formats=formats,
    )
