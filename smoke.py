"""Smoke test for the core engine - runs without GUI."""
import sys
import tempfile
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.loaders import load_sheet, list_sheets, get_columns, discover_files
from core.comparator import compare, CompareConfig, Mode
from core.exporter import export_results


def main():
    tmpdir = Path(tempfile.mkdtemp())
    print(f"Workspace: {tmpdir}")

    # Build a fake reference: planned cells
    ref = pd.DataFrame({
        "eNodeB": [1001, 1001, 1002, 1003],
        "Cell":   [1,    2,    1,    1],
        "PCI":    [12,   34,   56,   78],
        "RSRP":   [-95, -100, -90, -85],
    })
    ref_path = tmpdir / "reference.xlsx"
    ref.to_excel(ref_path, index=False)

    # Build two main files: live KPI exports (some matching, some not, some drift)
    main1 = pd.DataFrame({
        "eNodeB_ID": [1001, 1001, 1002, 9999],   # 9999 doesn't exist in ref
        "Cell_ID":   [1,    2,    1,    1],
        "PCI":       [12,   34,   56,   11],
        "RSRP":      [-94, -101, -110, -100],     # Cell (1002,1,56) drift: -90 vs -110
    })
    main2 = pd.DataFrame({
        "eNodeB_ID": [1003, 1003],
        "Cell_ID":   [1,    2],
        "PCI":       [78,   99],                  # second one not in ref
        "RSRP":      [-86,  -120],
    })
    f1 = tmpdir / "site_export_w1.csv"
    f2 = tmpdir / "site_export_w2.csv"
    main1.to_csv(f1, index=False)
    main2.to_csv(f2, index=False)

    # Test loaders
    print("\n[1] Loaders")
    print("  ref sheets:", list_sheets(ref_path))
    print("  ref cols:", get_columns(ref_path))
    print("  discovered:", [p.name for p in discover_files(tmpdir)])

    ref_df = load_sheet(ref_path)

    # Test EXISTS mode
    print("\n[2] EXISTS mode")
    cfg = CompareConfig(
        mode=Mode.EXISTS,
        keys_main=["eNodeB_ID", "Cell_ID", "PCI"],
        keys_ref=["eNodeB", "Cell", "PCI"],
    )
    r1 = compare(load_sheet(f1), ref_df, cfg, source=str(f1), sheet="Sheet1")
    print(f"  {f1.name}: matched={len(r1.matched)} unmatched={len(r1.unmatched)}")
    assert len(r1.matched) == 3 and len(r1.unmatched) == 1, "EXISTS mode wrong counts"

    # Test THRESHOLD mode
    print("\n[3] THRESHOLD mode (RSRP drift > 10 dB)")
    cfg_thr = CompareConfig(
        mode=Mode.THRESHOLD,
        keys_main=["eNodeB_ID", "Cell_ID", "PCI"],
        keys_ref=["eNodeB", "Cell", "PCI"],
        threshold_column_main="RSRP",
        threshold_column_ref="RSRP",
        threshold_value=10.0,
    )
    r_thr = compare(load_sheet(f1), ref_df, cfg_thr, source=str(f1))
    print(f"  breaches: {len(r_thr.diffs) if r_thr.diffs is not None else 0}")
    if r_thr.diffs is not None and not r_thr.diffs.empty:
        print(r_thr.diffs[["eNodeB_ID", "Cell_ID", "PCI", "__delta__"]].to_string(index=False))
    assert r_thr.diffs is not None and len(r_thr.diffs) == 1, "THRESHOLD wrong"

    # Test DIFF mode
    print("\n[4] DIFF mode (compare RSRP values)")
    cfg_diff = CompareConfig(
        mode=Mode.DIFF,
        keys_main=["eNodeB_ID", "Cell_ID", "PCI"],
        keys_ref=["eNodeB", "Cell", "PCI"],
        diff_columns=["RSRP"],
    )
    r_diff = compare(load_sheet(f1), ref_df, cfg_diff, source=str(f1))
    print(f"  diffs: {len(r_diff.diffs) if r_diff.diffs is not None else 0}")
    if r_diff.diffs is not None and not r_diff.diffs.empty:
        print(r_diff.diffs.to_string(index=False))

    # Test export
    print("\n[5] Export to XLSX")
    out_path = tmpdir / "report.xlsx"
    r2 = compare(load_sheet(f2), ref_df, cfg, source=str(f2))
    export_results([r1, r2, r_thr, r_diff], out_path)
    print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
    assert out_path.exists() and out_path.stat().st_size > 0

    # Verify the report can be opened
    sheets = list_sheets(out_path)
    print(f"  sheets in report: {sheets}")

    print("\nAll core checks passed.")


if __name__ == "__main__":
    main()
