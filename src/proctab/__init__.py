"""proctab — executive-ready summary tables and crosstabs.

v0.0.1 data-model layer. See TABLE_MODEL.md in the project root for the
design memo this implements.
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
    "render_text",
    "tabulate",
]
