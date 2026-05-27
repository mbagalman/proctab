"""DataFrame engine adapter (pandas / polars) via narwhals.

Internal — public API in `proctab.freq` / `proctab.tabulate` accepts native
DataFrames and routes through `wrap()` to get an engine-agnostic
`narwhals.DataFrame` for downstream aggregation work.

Uses `narwhals.stable.v1` so the wrapper code is insulated from narwhals'
own version churn.
"""

from __future__ import annotations

from typing import Any

import narwhals.stable.v1 as nw


def wrap(data: Any, *, required_columns: tuple[str, ...] = ()) -> nw.DataFrame:
    """Wrap a native pandas or polars DataFrame in narwhals; validate columns.

    Eager only: LazyFrames are rejected in v0.1. Optionally checks that
    every name in `required_columns` exists in the wrapped DataFrame.

    Raises:
        TypeError: `data` is not a recognized eager DataFrame (e.g., a
            LazyFrame, Series, dict, list, ndarray).
        KeyError: any name in `required_columns` is missing from the
            wrapped DataFrame.
    """
    try:
        nw_df = nw.from_native(data, eager_only=True)
    except TypeError as exc:
        raise TypeError(
            f"freq()/tabulate() expects a pandas or polars (eager) "
            f"DataFrame; got {type(data).__name__}. "
            f"Underlying narwhals error: {exc}"
        ) from exc

    if required_columns:
        available = list(nw_df.columns)
        missing = [c for c in required_columns if c not in available]
        if missing:
            raise KeyError(
                f"Column(s) not found in DataFrame: {missing}. "
                f"Available columns: {available}."
            )

    return nw_df
