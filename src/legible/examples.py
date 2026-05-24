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
        Category("N", label="N"),
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
