"""Command-line interface — the same engine, headless.

Examples:
    # Lookup mode: which rows in *.csv exist in reference.xlsx?
    python cli.py --main ./exports --ref reference.xlsx \\
        --keys-main eNodeB_ID,Cell_ID,PCI \\
        --keys-ref  eNodeB,Cell,PCI \\
        --out report.xlsx

    # Threshold mode: flag RSRP drift > 10 dB
    python cli.py --main today.csv --ref baseline.xlsx \\
        --keys-main eNodeB_ID,Cell_ID,PCI --keys-ref eNodeB,Cell,PCI \\
        --mode threshold --thr-main RSRP --thr-ref RSRP --thr 10 \\
        --out drift.xlsx
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
from typing import List

from core.loaders import load_sheet, list_sheets, discover_files
from core.comparator import compare, CompareConfig, Mode, CompareResult
from core.exporter import export_results

log = logging.getLogger("cli")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Compare CSV/Excel files against a reference.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--main", required=True, nargs="+",
                   help="Main file(s) or folder.")
    p.add_argument("--ref", required=True, help="Reference file.")
    p.add_argument("--ref-sheet", default=None,
                   help="Sheet name in reference (Excel only).")
    p.add_argument("--keys-main", required=True,
                   help="Comma-separated key columns in main files.")
    p.add_argument("--keys-ref", required=True,
                   help="Comma-separated key columns in reference.")
    p.add_argument("--mode", choices=[m.value for m in Mode], default=Mode.EXISTS.value)
    p.add_argument("--diff-cols", default="",
                   help="(diff mode) comma-separated columns to compare.")
    p.add_argument("--thr-main", default="", help="(threshold) numeric col in main.")
    p.add_argument("--thr-ref", default="", help="(threshold) numeric col in reference.")
    p.add_argument("--thr", type=float, default=0.0, help="Threshold |Δ| value.")
    p.add_argument("--case-sensitive", action="store_true",
                   help="Disable default case-insensitive matching.")
    p.add_argument("--out", required=True, help="Output XLSX path.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def expand_main(specs: List[str]) -> List[Path]:
    paths: List[Path] = []
    for s in specs:
        p = Path(s)
        if p.is_dir():
            paths.extend(discover_files(p))
        elif p.is_file():
            paths.append(p)
        else:
            log.warning("Skipping (not found): %s", s)
    # de-dupe, keep order
    seen = set()
    out = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    main_files = expand_main(args.main)
    if not main_files:
        log.error("No main files found.")
        return 2

    ref_path = Path(args.ref)
    if not ref_path.exists():
        log.error("Reference not found: %s", ref_path)
        return 2

    cfg = CompareConfig(
        mode=Mode(args.mode),
        keys_main=[k.strip() for k in args.keys_main.split(",") if k.strip()],
        keys_ref=[k.strip() for k in args.keys_ref.split(",") if k.strip()],
        diff_columns=[c.strip() for c in args.diff_cols.split(",") if c.strip()],
        threshold_column_main=args.thr_main,
        threshold_column_ref=args.thr_ref,
        threshold_value=args.thr,
        case_insensitive=not args.case_sensitive,
    )

    log.info("Loading reference: %s", ref_path)
    ref_df = load_sheet(ref_path, args.ref_sheet)

    results: List[CompareResult] = []
    for f in main_files:
        for sh in list_sheets(f):
            log.info("Processing %s [%s]", f.name, sh)
            try:
                df = load_sheet(f, sh)
                r = compare(df, ref_df, cfg, source=str(f), sheet=sh)
                results.append(r)
                log.info("  matched=%d unmatched=%d diffs=%d",
                         len(r.matched), len(r.unmatched),
                         0 if r.diffs is None else len(r.diffs))
            except Exception as e:
                log.exception("Failed on %s [%s]: %s", f, sh, e)

    if not results:
        log.error("Nothing was processed.")
        return 1

    out = export_results(results, args.out)
    log.info("Report written: %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
