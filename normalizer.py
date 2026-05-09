"""Data normalization helpers."""
from __future__ import annotations
from typing import List
import pandas as pd


def normalize_series(
    s: pd.Series,
    *,
    case_insensitive: bool = True,
    strip: bool = True,
) -> pd.Series:
    """Cast to str, strip whitespace, optional case-fold, NaN-like → <NA>."""
    out = s.astype(str)
    if strip:
        out = out.str.strip()
    if case_insensitive:
        out = out.str.casefold()
    out = out.replace({"nan": pd.NA, "": pd.NA, "none": pd.NA, "<na>": pd.NA})
    return out


def composite_key(
    df: pd.DataFrame,
    cols: List[str],
    *,
    case_insensitive: bool = True,
    strip: bool = True,
    sep: str = "|",
    na_token: str = "\u2205",  # ∅
) -> pd.Series:
    """Build a single composite key from multiple columns."""
    if not cols:
        raise ValueError("composite_key requires at least one column")
    parts = [
        normalize_series(df[c], case_insensitive=case_insensitive, strip=strip)
        .fillna(na_token)
        .astype(str)
        for c in cols
    ]
    key = parts[0]
    for p in parts[1:]:
        key = key + sep + p
    return key
