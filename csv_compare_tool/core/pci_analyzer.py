"""PCI analysis - frequency counting and reference lookup for drive test data.

Automatically detects:
  - LTE PCI column  : (1)(TopN)PCI  (and variants with spaces)
  - NR  PCI column  : (NR TopN) Beam Cell Id  (and variants)
  - Context columns : Zone, Sector, PCI Zone, 5G Sector, etc.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
import pandas as pd


def csv_short_name(source: str) -> str:
    """Extract the meaningful measurement suffix from a drive test CSV filename.

    'Scanner_Lower_Bowl_76.CSV.TopN_AWS - 3 DL_LTE_CH66586.csv'
    →  'TopN_AWS - 3 DL_LTE_CH66586'

    Falls back to the full stem when no '.CSV.' separator is present.
    """
    stem = Path(source).stem
    parts = re.split(r"\.CSV\.", stem, maxsplit=1, flags=re.IGNORECASE)
    return parts[1].strip() if len(parts) == 2 else stem


# ── Detection patterns ───────────────────────────────────────────────────────

_LTE_PATTERNS = [
    r"\(1\)\s*\(TopN\)\s*PCI",   # (1)(TopN)PCI
    r"\(1\).*TopN.*PCI",          # (1) ... TopN ... PCI
    r"TopN.*PCI",                 # TopN...PCI  (generic fallback)
]

_NR_PATTERNS = [
    r"\(NR\s*TopN\)\s*Beam\s*Cell",   # (NR TopN) Beam Cell...
    r"NR.*TopN.*Beam.*Cell",           # NR...TopN...Beam...Cell
    r"Beam.*Cell.*Id",                 # Beam Cell Id (generic NR fallback)
]

_CONTEXT_KEYWORDS = ["zone", "sector"]


def _find_col(df: pd.DataFrame, patterns: List[str]) -> Optional[str]:
    """Return first column in df that matches any regex pattern."""
    for pat in patterns:
        for col in df.columns:
            if re.search(pat, str(col), re.IGNORECASE):
                return col
    return None


def find_column(df: pd.DataFrame, name: str) -> Optional[str]:
    """Find column by exact name, then by whitespace-stripped case-insensitive match."""
    if not name:
        return None
    if name in df.columns:
        return name
    norm = re.sub(r"\s+", "", name).lower()
    for col in df.columns:
        if re.sub(r"\s+", "", str(col)).lower() == norm:
            return col
    return None


def detect_pci_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Return {'lte': column_name_or_None, 'nr': column_name_or_None}."""
    return {
        "lte": _find_col(df, _LTE_PATTERNS),
        "nr":  _find_col(df, _NR_PATTERNS),
    }


def auto_detect_pci_columns(df: pd.DataFrame) -> List[str]:
    """Return all PCI-related column names found (LTE first, then NR, then generic)."""
    seen: List[str] = []
    for col in [_find_col(df, _LTE_PATTERNS), _find_col(df, _NR_PATTERNS)]:
        if col and col not in seen:
            seen.append(col)
    for col in df.columns:
        if "pci" in str(col).lower() and col not in seen:
            seen.append(col)
    return seen


def detect_context_columns(df: pd.DataFrame, max_cols: int = 5) -> List[str]:
    """Return up to max_cols columns related to Zone or Sector."""
    found = []
    for col in df.columns:
        if len(found) >= max_cols:
            break
        if any(kw in str(col).lower() for kw in _CONTEXT_KEYWORDS):
            found.append(col)
    return found


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PCIResult:
    source: str
    sheet: str
    pci_col: str
    total_rows: int
    pci_counts: pd.Series           # index=PCI str, values=count, sorted desc
    in_ref_pcis: Set[str]           # PCI values found in reference
    unique_pcis: Set[str]           # PCI values NOT in reference
    context_cols: List[str] = field(default_factory=list)
    pci_context_agg: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # pci_context_agg: {pci_value -> {col_name -> "comma-joined unique values"}}

    @property
    def floor(self) -> str:
        """Immediate parent folder name — used as floor/zone label."""
        return Path(self.source).parent.name if self.source else ""

    @property
    def short_name(self) -> str:
        """Meaningful measurement suffix of the CSV filename (after '.CSV.' separator)."""
        return csv_short_name(self.source) if self.source else self.source

    @property
    def total_unique(self) -> int:
        return len(self.pci_counts)

    @property
    def in_ref_row_count(self) -> int:
        mask = self.pci_counts.index.isin(self.in_ref_pcis)
        return int(self.pci_counts[mask].sum())

    @property
    def unique_row_count(self) -> int:
        mask = self.pci_counts.index.isin(self.unique_pcis)
        return int(self.pci_counts[mask].sum())

    @property
    def pct_rows_in_ref(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return round(100.0 * self.in_ref_row_count / self.total_rows, 1)

    @property
    def summary(self) -> dict:
        return {
            "Floor": self.floor,
            "File": self.source,
            "Measurement": self.short_name,
            "PCI Column Used": self.pci_col,
            "Total Rows (with PCI)": self.total_rows,
            "Unique PCIs Found": self.total_unique,
            "PCIs in Reference": len(self.in_ref_pcis),
            "PCIs NOT in Reference": len(self.unique_pcis),
            "% Rows Matched": self.pct_rows_in_ref,
        }

    def detail_df(self) -> pd.DataFrame:
        """Per-PCI breakdown: PCI, Count, %, In Reference, + any context cols."""
        total = self.total_rows or 1
        rows = []
        for pci_val in self.pci_counts.index:
            count = int(self.pci_counts[pci_val])
            row: dict = {
                "PCI": pci_val,
                "Count": count,
                "% of Total": round(count / total * 100, 1),
                "In Reference": "Yes" if pci_val in self.in_ref_pcis else "No - UNIQUE",
            }
            ctx = self.pci_context_agg.get(pci_val, {})
            for col in self.context_cols:
                row[col] = ctx.get(col, "")
            rows.append(row)
        base_cols = ["PCI", "Count", "% of Total", "In Reference"] + list(self.context_cols)
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=base_cols)


# ── Analysis function ─────────────────────────────────────────────────────────

def analyze_pci(
    df: pd.DataFrame,
    pci_col: str,
    ref_pci_values: Set,
    *,
    source: str = "",
    sheet: str = "",
    context_cols: Optional[List[str]] = None,
) -> PCIResult:
    """Count PCI occurrences, cross-check against reference, aggregate context."""
    if pci_col not in df.columns:
        raise KeyError(
            f"PCI column '{pci_col}' not found. "
            f"Available: {list(df.columns)[:15]}"
        )

    raw = df[pci_col].dropna().astype(str).str.strip()
    raw = raw[~raw.isin(["nan", "", "None", "NaN"])]
    counts = raw.value_counts()

    norm_ref = {
        str(v).strip() for v in ref_pci_values
        if pd.notna(v) and str(v).strip() not in ("", "nan", "None")
    }
    in_ref = {p for p in counts.index if p in norm_ref}
    unique = {p for p in counts.index if p not in norm_ref}

    # Build per-PCI context aggregation (groupby for efficiency)
    ctx_cols = [c for c in (context_cols or []) if c in df.columns]
    pci_ctx_agg: Dict[str, Dict[str, str]] = {}
    if ctx_cols:
        def _join_unique(s: pd.Series) -> str:
            vals = sorted({str(v).strip() for v in s.dropna()
                           if str(v).strip() not in ("", "nan", "None")})
            return ", ".join(vals[:6])

        ctx_df = df.loc[raw.index, ctx_cols].copy()
        ctx_df["__pci__"] = raw.values
        try:
            grouped = ctx_df.groupby("__pci__", sort=False).agg(
                {col: _join_unique for col in ctx_cols}
            )
            pci_ctx_agg = grouped.to_dict(orient="index")
        except Exception:
            pci_ctx_agg = {}

    return PCIResult(
        source=source, sheet=sheet, pci_col=pci_col,
        total_rows=int(raw.shape[0]), pci_counts=counts,
        in_ref_pcis=in_ref, unique_pcis=unique,
        context_cols=ctx_cols, pci_context_agg=pci_ctx_agg,
    )
