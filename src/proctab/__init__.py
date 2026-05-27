"""proctab — executive-ready summary tables and crosstabs.

v0.0.1 data-model layer. See docs/TABLE_MODEL.md for the design memo
this implements.
"""

from proctab.freq import freq
from proctab.tabulate import tabulate
from proctab.model import (
    Axis,
    Category,
    Dimension,
    DimensionKind,
    Marker,
    MissingReason,
    Node,
    NodeRole,
    PathElement,
    SubtotalMarker,
    Table,
    TotalMarker,
    ValueKind,
)
from proctab.render.excel import render_excel
from proctab.render.html import render_html
from proctab.render.text import render_text

__all__ = [
    "Axis",
    "Category",
    "Dimension",
    "DimensionKind",
    "Marker",
    "MissingReason",
    "Node",
    "NodeRole",
    "PathElement",
    "SubtotalMarker",
    "Table",
    "TotalMarker",
    "ValueKind",
    "freq",
    "render_excel",
    "render_html",
    "render_text",
    "tabulate",
]
