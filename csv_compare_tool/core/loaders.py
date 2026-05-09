"""File loading - pure functions, no GUI dependency."""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Union
import pandas as pd
import openpyxl

SUPPORTED_EXTS = {".csv", ".xlsx", ".xls", ".tsv"}


def list_sheets(path: Union[str, Path]) -> List[str]:
    """Return sheet names for Excel; ['Sheet1'] sentinel for CSV/TSV."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()
    return ["Sheet1"]


def get_columns(path: Union[str, Path], sheet: Optional[str] = None) -> List[str]:
    """Read just the header row to populate dropdowns fast."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p, nrows=0).columns.tolist()
    if ext == ".tsv":
        return pd.read_csv(p, sep="\t", nrows=0).columns.tolist()
    if ext in {".xlsx", ".xls"}:
        return pd.read_excel(p, sheet_name=sheet or 0, nrows=0).columns.tolist()
    raise ValueError(f"Unsupported file type: {ext}")


def load_sheet(path: Union[str, Path], sheet: Optional[str] = None) -> pd.DataFrame:
    """Load a single sheet/file fully into a DataFrame."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    if ext == ".tsv":
        return pd.read_csv(p, sep="\t")
    if ext in {".xlsx", ".xls"}:
        # sheet=None would load all; we want just one
        return pd.read_excel(p, sheet_name=sheet if sheet is not None else 0)
    raise ValueError(f"Unsupported file type: {ext}")


def discover_files(folder: Union[str, Path], recursive: bool = False) -> List[Path]:
    """Find all supported files in a folder.

    recursive=True walks all subfolders (useful for floor-based drive test layouts
    where each subfolder is a floor/zone containing multiple CSVs).
    """
    p = Path(folder)
    if not p.is_dir():
        return []
    iterator = p.rglob("*") if recursive else p.iterdir()
    return sorted(
        f for f in iterator
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
    )
