"""Comparison strategies - the heart of the tool.

Modes:
    EXISTS    - "Is this row's key present in the reference?" (lookup)
    DIFF      - For matched rows, show columns whose values differ
    THRESHOLD - For matched rows, flag where |main - ref| > X (numeric)

All modes work on a *composite key* (one or more columns) so RF data
like (eNodeB, Cell, PCI) tuples are first-class.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import pandas as pd

from .normalizer import composite_key


class Mode(str, Enum):
    EXISTS = "exists"
    DIFF = "diff"
    THRESHOLD = "threshold"


@dataclass
class CompareConfig:
    mode: Mode = Mode.EXISTS
    keys_main: List[str] = field(default_factory=list)
    keys_ref: List[str] = field(default_factory=list)
    diff_columns: List[str] = field(default_factory=list)
    threshold_column_main: str = ""
    threshold_column_ref: str = ""
    threshold_value: float = 0.0
    case_insensitive: bool = True
    strip_whitespace: bool = True


@dataclass
class CompareResult:
    source: str
    sheet: str
    main_rows: int
    matched: pd.DataFrame
    unmatched: pd.DataFrame
    diffs: Optional[pd.DataFrame] = None

    @property
    def summary(self) -> dict:
        return {
            "source": self.source,
            "sheet": self.sheet,
            "total_main_rows": self.main_rows,
            "matched": len(self.matched),
            "unmatched": len(self.unmatched),
            "diffs_or_breaches": 0 if self.diffs is None else len(self.diffs),
        }


def _validate(cfg: CompareConfig, main_df: pd.DataFrame, ref_df: pd.DataFrame) -> None:
    if not cfg.keys_main or not cfg.keys_ref:
        raise ValueError("Provide at least one key column for both main and reference.")
    if len(cfg.keys_main) != len(cfg.keys_ref):
        raise ValueError("Main and reference key column counts must match.")
    for c in cfg.keys_main:
        if c not in main_df.columns:
            raise KeyError(f"Main key column not found: '{c}'. "
                           f"Available: {list(main_df.columns)[:10]}…")
    for c in cfg.keys_ref:
        if c not in ref_df.columns:
            raise KeyError(f"Reference key column not found: '{c}'. "
                           f"Available: {list(ref_df.columns)[:10]}…")


def compare(
    main_df: pd.DataFrame,
    ref_df: pd.DataFrame,
    cfg: CompareConfig,
    *,
    source: str = "",
    sheet: str = "",
) -> CompareResult:
    """Run a comparison and return matched/unmatched (and diffs if applicable)."""
    _validate(cfg, main_df, ref_df)

    norm_kwargs = dict(
        case_insensitive=cfg.case_insensitive,
        strip=cfg.strip_whitespace,
    )
    main_key = composite_key(main_df, cfg.keys_main, **norm_kwargs)
    ref_key = composite_key(ref_df, cfg.keys_ref, **norm_kwargs)
    ref_set = set(ref_key)

    matched_mask = main_key.isin(ref_set)
    matched = main_df[matched_mask].copy()
    unmatched = main_df[~matched_mask].copy()

    diffs: Optional[pd.DataFrame] = None

    if cfg.mode == Mode.DIFF and cfg.diff_columns and not matched.empty:
        diffs = _compute_diffs(main_df, ref_df, main_key, ref_key,
                               matched_mask, cfg)
    elif cfg.mode == Mode.THRESHOLD and not matched.empty:
        diffs = _compute_threshold(main_df, ref_df, main_key, ref_key,
                                   matched_mask, cfg)

    return CompareResult(
        source=source,
        sheet=sheet,
        main_rows=len(main_df),
        matched=matched,
        unmatched=unmatched,
        diffs=diffs,
    )


def _compute_diffs(main_df, ref_df, main_key, ref_key,
                   matched_mask, cfg: CompareConfig) -> pd.DataFrame:
    """For DIFF mode: find rows where matched-pair values differ."""
    main_with_key = main_df.copy()
    main_with_key["__k__"] = main_key.values
    main_subset = main_with_key[matched_mask.values]

    ref_with_key = ref_df.copy()
    ref_with_key["__k__"] = ref_key.values
    ref_with_key = ref_with_key.drop_duplicates("__k__")

    merged = main_subset.merge(
        ref_with_key, on="__k__", suffixes=("_main", "_ref"), how="left"
    )

    def resolve(col, side):
        """Find a column's actual name after pandas' merge suffixing."""
        suffixed = f"{col}_{side}"
        if suffixed in merged.columns:
            return suffixed
        if col in merged.columns:
            return col
        return None

    diff_records = []
    for col in cfg.diff_columns:
        col_main = resolve(col, "main")
        col_ref = resolve(col, "ref")
        if col_main is None or col_ref is None or col_main == col_ref:
            continue
        a = merged[col_main].astype(str).fillna("")
        b = merged[col_ref].astype(str).fillna("")
        changed = merged[a != b]
        if changed.empty:
            continue
        # Pull key columns (which may also have been suffixed)
        key_cols_resolved = [resolve(k, "main") or k for k in cfg.keys_main]
        out = changed[key_cols_resolved].copy()
        out.columns = cfg.keys_main  # restore clean names
        out["__column__"] = col
        out["main_value"] = changed[col_main].values
        out["ref_value"] = changed[col_ref].values
        diff_records.append(out)

    if not diff_records:
        return pd.DataFrame(columns=[*cfg.keys_main, "__column__", "main_value", "ref_value"])
    return pd.concat(diff_records, ignore_index=True)


def _compute_threshold(main_df, ref_df, main_key, ref_key,
                       matched_mask, cfg: CompareConfig) -> pd.DataFrame:
    """For THRESHOLD mode: flag rows where |main - ref| > threshold_value."""
    if not cfg.threshold_column_main or not cfg.threshold_column_ref:
        return pd.DataFrame()

    main_with_key = main_df.copy()
    main_with_key["__k__"] = main_key.values
    main_subset = main_with_key[matched_mask.values]

    ref_slim = ref_df[[cfg.threshold_column_ref]].copy()
    ref_slim["__k__"] = ref_key.values
    ref_slim = ref_slim.drop_duplicates("__k__")

    merged = main_subset.merge(ref_slim, on="__k__", how="left",
                               suffixes=("", "_ref"))

    main_col = cfg.threshold_column_main
    ref_col = cfg.threshold_column_ref
    # If columns share a name, pandas appended _ref to the right side
    ref_actual = ref_col if ref_col in merged.columns and ref_col != main_col else f"{ref_col}_ref"
    if ref_actual not in merged.columns:
        ref_actual = ref_col

    a = pd.to_numeric(merged[main_col], errors="coerce")
    b = pd.to_numeric(merged[ref_actual], errors="coerce")
    delta = (a - b).abs()
    breach = delta > cfg.threshold_value
    out = merged[breach].copy()
    out["__delta__"] = delta[breach].values
    return out.drop(columns=["__k__"], errors="ignore")
